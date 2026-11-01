"""Support-free printability check (FDM), layer by layer like a slicer.

Usage:
    python printcheck.py part.stl                        # one part
    python printcheck.py frame_petg.stl frame_pla.stl    # several files = one object (AMS), same coordinates
    options: --layer 0.2 --angle 45 --max-bridge 30 --png out.png

The STL must already be oriented the way it lies on the bed (Z up, bed at z=0).

Reports:
  SUPPORTS  - area with nothing under it: floating in the air (even a tiny island or a thin ridge),
              an overhang anchored on one side only, or a bridge longer than --max-bridge
  BRIDGE    - span anchored on both sides (up to --max-bridge), prints without supports
  HOLE IN BRIDGE - bridge with a hole in the middle: the hole walls hang in the air and the bridge
              around it sags. Fix: sacrificial layer (start the hole one layer above the bridge, drill it later)
  MATERIAL  - several files only: a layer sits on another material (e.g. PETG does not bond to PLA)
  OFF BED   - a part that does not touch the bed at all
  PIECES    - the part falls apart into separate pieces (something touches nothing, e.g. a detached thumb).
              Pieces closer than 0.05 mm count as joined; with several STLs (AMS) all are judged together.
              When an STL has several pieces on purpose (a whole plate in one file), add --multi-piece.
Exit code 1 = something needs fixing (SUPPORTS, HOLE IN BRIDGE, OFF BED or PIECES).
"""
import argparse
import math
import sys
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import CrossSection, JoinType, Manifold, Mesh

MIN_AREA = 1.0      # mm², ignore smaller leftovers
OPEN_R = 0.3        # filters out thin slivers from sloped walls


def load(path):
    t = trimesh.load(path, force="mesh")
    t.merge_vertices()
    m = Manifold(Mesh(vert_properties=np.asarray(t.vertices, dtype=np.float32),
                      tri_verts=np.asarray(t.faces, dtype=np.uint32)))
    if m.status().name != "NoError":
        sys.exit(f"{path}: mesh is not closed ({m.status().name})")
    return m


def opened(cs, r=OPEN_R):
    return cs.offset(-r, JoinType.Round).offset(r, JoinType.Round)


def width(cs):
    # Width = 2 × largest inscribed radius (binary search by erosion).
    lo, hi = 0.0, 200.0
    for _ in range(14):
        mid = (lo + hi) / 2
        if cs.offset(-mid, JoinType.Round).area() > 1e-6:
            lo = mid
        else:
            hi = mid
    return 2 * lo


def span(comp, anchor):
    # Bridge length ≈ 2 × the largest distance of any point of the area from the nearest anchor.
    lo, hi = 0.0, 300.0
    for _ in range(14):
        mid = (lo + hi) / 2
        if (comp - anchor.offset(mid, JoinType.Round)).area() > 1e-3:
            lo = mid
        else:
            hi = mid
    return 2 * hi


def perimeter(cs):
    total = 0.0
    for poly in cs.to_polygons():
        p = np.asarray(poly)
        total += np.linalg.norm(np.roll(p, -1, axis=0) - p, axis=1).sum()
    return total


def outer_anchored(comp, prev_all, step):
    # A bridge must be anchored on its OUTER outline: either in two separate stretches or along most
    # of the perimeter. Anchored only on an inner outline (a hole) = a ring sticking out = one-sided overhang.
    for poly in comp.to_polygons():
        p = np.asarray(poly)
        signed = 0.5 * np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1])
        if signed <= 0:
            continue
        filled = CrossSection([poly])
        band = (filled.offset(0.6, JoinType.Round) - filled) ^ prev_all
        if band.area() < 0.05:
            return False
        contact = band.area() / (0.6 - step)
        frac = contact / perimeter(CrossSection([poly]))
        if len(band.decompose()) < 2 and frac < 0.6:
            return False
    return True


def holes_in_bridge(comp, cs):
    # A hole inside a bridge: its walls print into the air and the bridge around it sags
    # (verified on a frame pocket with a nail hole). Fix: a sacrificial layer over the hole.
    # Inner outline of the unsupported area that is empty in the part (not a post holding the bridge up).
    area = 0.0
    for poly in comp.to_polygons():
        p = np.asarray(poly)
        signed = 0.5 * np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1])
        if signed < 0:
            area += (CrossSection([poly[::-1]]) - cs).area()
    return area


def ridge(comp, near):
    # Ridge: touches support only at its ends, not along its length (that would just be a steeper overhang, e.g. a hole ceiling)
    touch = (comp.offset(0.1, JoinType.Round) ^ near).area() / 0.1
    return touch < 0.25 * perimeter(comp)


TOUCH = 0.05       # mm, bodies closer than this touch


def loose_pieces(parts):
    """Groups the bodies of all parts into clusters that touch each other. Returns [(names, cm³, centre), ...]."""
    bodies = [(n, b) for n, m in parts for b in m.decompose()]
    root = list(range(len(bodies)))

    def find(i):
        while root[i] != i:
            root[i] = root[root[i]]
            i = root[i]
        return i

    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            if find(i) != find(j) and bodies[i][1].min_gap(bodies[j][1], 2 * TOUCH) < TOUCH:
                root[find(i)] = find(j)
    groups = {}
    for i, (n, b) in enumerate(bodies):
        groups.setdefault(find(i), []).append((n, b))
    out = []
    for g in groups.values():
        bb = np.array([b.bounding_box() for _, b in g])
        c = ((bb[:, 0].min() + bb[:, 3].max()) / 2, (bb[:, 1].min() + bb[:, 4].max()) / 2, (bb[:, 2].min() + bb[:, 5].max()) / 2)
        out.append((sorted({n for n, _ in g}), sum(b.volume() for _, b in g) / 1000, c))
    return sorted(out, key=lambda g: -g[1])


def bbox_center(cs):
    b = cs.bounds()
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def check(paths, layer, angle, max_bridge):
    parts = [(Path(p).stem, load(p)) for p in paths]
    zmax = max(m.bounding_box()[5] for _, m in parts)
    step = layer * math.tan(math.radians(angle))
    issues = []

    for name, m in parts:
        if m.bounding_box()[2] > 0.05 and len(parts) == 1:
            issues.append(("OFF BED", name, 0.0, m.bounding_box()[2], 0.0, (0.0, 0.0), 0.0))

    n_layers = int(zmax / layer)
    prev = {name: CrossSection() for name, _ in parts}
    for i in range(n_layers):
        z = (i + 0.5) * layer
        cur = {name: m.slice(z) for name, m in parts}
        if i == 0:
            prev = cur
            continue
        prev_all = CrossSection()
        for cs in prev.values():
            prev_all = prev_all + cs
        support = prev_all.offset(step, JoinType.Round)

        for name, cs in cur.items():
            if cs.area() < 1e-6:
                continue
            # An island that starts in the air (a tip pointing down), even while it is still tiny.
            for comp in cs.decompose():
                if comp.area() > 1e-3 and (comp ^ prev_all).area() < 1e-4:
                    issues.append(("SUPPORTS", name, z, z, comp.area(), bbox_center(comp), 0.0))
            over = opened(cs - support)
            # A thin ridge in the air (e.g. the bottom edge of a lying bone just above the bed): opening
            # drops it, but more than two overhang steps away from support it is a bridge or a floating part.
            near = prev_all.offset(2 * step, JoinType.Round)
            thin = [c for c in (cs - near - over.offset(0.05, JoinType.Round)).decompose()
                    if c.area() >= MIN_AREA and ridge(c, near)]
            for comp in list(over.decompose()) + thin:
                a = comp.area()
                if a < MIN_AREA:
                    continue
                anchor = comp.offset(0.6, JoinType.Round) ^ prev_all.offset(0.01)
                if anchor.area() < 0.05:
                    kind, L = "SUPPORTS", 0.0          # floating in the air
                else:
                    L = span(comp, anchor)
                    kind = "BRIDGE" if outer_anchored(comp, prev_all, step) and L <= max_bridge else "SUPPORTS"
                    if kind == "BRIDGE" and holes_in_bridge(comp, cs) >= MIN_AREA:
                        kind = "HOLE IN BRIDGE"
                issues.append((kind, name, z, z, a, bbox_center(comp), L))

            if len(parts) > 1:
                own = prev[name].offset(step, JoinType.Round)
                foreign = CrossSection()
                for other, ocs in prev.items():
                    if other != name:
                        foreign = foreign + ocs
                on_other = opened((cs - own) ^ foreign)
                if on_other.area() >= MIN_AREA:
                    issues.append(("MATERIAL", name, z, z, on_other.area(),
                                   bbox_center(on_other), width(on_other)))
        prev = cur
    return parts, issues


def count_swaps(parts, layer):
    # Each file = one filament. A layer starts with the filament the previous layer ended with
    # (Bambu Studio orders it the same way), so a layer with 2 materials = 1 swap.
    zmax = max(m.bounding_box()[5] for _, m in parts)
    current, swaps, mixed = None, 0, 0
    for i in range(int(zmax / layer)):
        z = (i + 0.5) * layer
        present = [n for n, m in parts if m.slice(z).area() > 1e-6]
        if len(present) > 1:
            mixed += 1
        if current is None or current in present:
            swaps += max(len(present) - 1, 0)
            if current in present:
                present.remove(current)
                present.insert(0, current)
        elif current is not None:
            swaps += len(present)
        current = present[-1] if present else current
    return swaps, mixed, int(zmax / layer)


def merge(issues, layer):
    # Merges the same problem in consecutive layers at a similar spot.
    out = []
    for kind, name, z0, z1, a, c, w in issues:
        for g in out:
            if (g["kind"] == kind and g["name"] == name and z0 - g["z1"] <= layer * 1.5
                    and math.dist(g["c"], c) < 10):
                g["z1"] = z1; g["area"] += a; g["w"] = max(g["w"], w); g["c"] = c
                break
        else:
            out.append(dict(kind=kind, name=name, z0=z0, z1=z1, area=a, c=c, w=w))
    return out


def render(parts, groups, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 8))
    for name, m in parts:
        proj = m.project()
        for poly in proj.to_polygons():
            p = np.asarray(poly)
            ax.fill(p[:, 0], p[:, 1], color="#ddd", alpha=0.6)
    colors = {"SUPPORTS": "#d62828", "HOLE IN BRIDGE": "#9d0208", "BRIDGE": "#2a9d8f", "MATERIAL": "#f4a261", "OFF BED": "#6a0dad"}
    for g in groups:
        ax.plot(*g["c"], "o", color=colors[g["kind"]], ms=6 if g["kind"] in ("SUPPORTS", "HOLE IN BRIDGE") else 4)
    for k, c in colors.items():
        ax.plot([], [], "o", color=c, label=k)
    ax.legend(loc="upper right")
    ax.set_aspect("equal")
    ax.set_title("Top view: where to look")
    plt.savefig(path, dpi=100)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("stl", nargs="+")
    ap.add_argument("--layer", type=float, default=0.2)
    ap.add_argument("--angle", type=float, default=45.0, help="max. overhang from vertical")
    ap.add_argument("--max-bridge", type=float, default=30.0)
    ap.add_argument("--png")
    ap.add_argument("--multi-piece", action="store_true", help="the STL has several separate pieces on purpose")
    a = ap.parse_args()

    parts, issues = check(a.stl, a.layer, a.angle, a.max_bridge)
    groups = merge(issues, a.layer)
    bad = [g for g in groups if g["kind"] in ("SUPPORTS", "HOLE IN BRIDGE", "OFF BED")]
    pieces = loose_pieces(parts)

    print(f"== {', '.join(n for n, _ in parts)}  (layer {a.layer}, overhang {a.angle}°, bridge ≤ {a.max_bridge} mm)")
    for g in groups:
        if g["kind"] == "OFF BED":
            print(f"  OFF BED: {g['name']} starts at {g['z1']:.1f} mm")
    for kind in ("SUPPORTS", "HOLE IN BRIDGE", "MATERIAL", "BRIDGE"):
        gs = [g for g in groups if g["kind"] == kind]
        if not gs:
            continue
        print(f"  {kind}: {len(gs)}×")
        for g in sorted(gs, key=lambda g: -g["area"])[:12]:
            print(f"    {g['name']}: z {g['z0']:.1f}–{g['z1']:.1f} mm, area {g['area']:.0f} mm², "
                  f"length {g['w']:.1f} mm, at x={g['c'][0]:.0f} y={g['c'][1]:.0f}")
    if len(pieces) > 1:
        print(f"  PIECES: the part falls apart into {len(pieces)} separate pieces{' (allowed by --multi-piece)' if a.multi_piece else ''}")
        for names, v, c in pieces[:12]:
            print(f"    {', '.join(names)}: {v:.2f} cm³, centre x={c[0]:.0f} y={c[1]:.0f} z={c[2]:.0f}")
        if not a.multi_piece:
            bad.append({"kind": "PIECES"})
    mat = [g for g in groups if g["kind"] == "MATERIAL"]
    verdict = "OK without supports" if not bad else "NEEDS FIXING"
    if mat:
        verdict += f" | WARNING: {sum(g['area'] for g in mat):.0f} mm² sits on another material (will not bond)"
    if len(parts) > 1:
        swaps, mixed, total = count_swaps(parts, a.layer)
        print(f"  FILAMENT SWAPS: {swaps}× ({mixed} of {total} layers contain several materials)")
    print("  RESULT:", verdict)
    if a.png:
        render(parts, groups, a.png)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
