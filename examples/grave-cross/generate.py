"""Parametric model: a graveyard cross stuck in a lump of lava, with small bones around it.

Parts:
  Cross   - white PLA, flat cross with trefoil arm ends, chamfered top-face edges and engraved TEXT.
            A spike at the bottom goes into the lava. Prints lying on its back (bed face down).
  Bone N  - white PLA, half bones with a flat bottom, lying half sunk around the cross (one per BONES length).

Print coordinates: z up (thickness), y along the cross (y=0 lava surface, spike below), x across, sizes in mm.
The names in CAPS below are the names on sketch.png and in preview.html: ask for a change by name.
Run:     python generate.py
Output:  grave-cross.3mf, sketch.png, meshes.js (for preview.html), stl/*.stl, printcheck.png
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import CrossSection, FillRule, JoinType, Manifold, OpType
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath

# ---------- PARAMETERS (mm) ----------
BEAM = 22.0                       # width of the beam and the arms
THICK = 9.0                       # cross thickness = print height
CHAMFER = 2.0                     # 45° chamfer of the top-face edges
STEP = 0.2                        # chamfer in layer-height steps, the printer makes it that way anyway
TOP = 195.0                       # lava surface to the tip of the top lobe
ARM_Y = 133.0                     # lava surface to the arm axis
SPAN = 130.0                      # arm end to arm end
LOBE_R = 9.0                      # trefoil end: middle circle
SIDE_R = 6.5                      # trefoil end: the two side circles
SPIKE_LEN = 45.0                  # spike into the lava, below the lava surface
SPIKE_ROOT = 12.0                 # spike width at the cross
SPIKE_TIP = 2.0                   # spike width at the tip
TEXT = "R.I.P."
TEXT_H = 11.0                     # cap height of the letters
TEXT_DEPTH = 1.0                  # engraving depth

BONES = [75.0, 66.0, 58.0, 50.0, 44.0, 38.0]      # one bone per length
BONE_R = 0.065                    # shaft radius as a fraction of the bone length
BONE_KNOB = 0.10                  # knob radius as a fraction of the bone length

OUT = Path(__file__).parent
SCRIPTS = Path(__file__).resolve().parents[2] / "skills/3d-print-design/scripts"
sys.path.insert(0, str(SCRIPTS))


def circle(c, r):
    return CrossSection.circle(r, 96).translate(c)


def rect(x0, y0, x1, y1):
    return CrossSection.square([x1 - x0, y1 - y0]).translate([x0, y0])


def trefoil_centres(end, d):
    """Centres of the trefoil circles. end = outermost point, d = arm direction outwards."""
    end, d = np.asarray(end, float), np.asarray(d, float)
    n = np.array([-d[1], d[0]])
    c = end - d * LOBE_R
    side = c - d * 7.0
    return c, side + n * BEAM / 2, side - n * BEAM / 2


def trefoil(end, d):
    c, s1, s2 = trefoil_centres(end, d)
    return circle(c, LOBE_R) + circle(s1, SIDE_R) + circle(s2, SIDE_R)


def outline():
    h = BEAM / 2
    return (rect(-h, 0, h, TOP - LOBE_R) + rect(-SPAN / 2 + LOBE_R, ARM_Y - h, SPAN / 2 - LOBE_R, ARM_Y + h)
            + trefoil((0, TOP), (0, 1)) + trefoil((-SPAN / 2, ARM_Y), (-1, 0)) + trefoil((SPAN / 2, ARM_Y), (1, 0))
            + CrossSection([[(-SPIKE_ROOT / 2, 0.5), (-SPIKE_TIP / 2, -SPIKE_LEN),
                             (SPIKE_TIP / 2, -SPIKE_LEN), (SPIKE_ROOT / 2, 0.5)]]))


def text_outline():
    prop = FontProperties(family="DejaVu Sans", weight="bold")
    cap = TextPath((0, 0), "H", size=10, prop=prop).get_extents().height / 10
    tp = TextPath((0, 0), TEXT, size=TEXT_H / cap, prop=prop)
    cs = CrossSection([p[:-1].tolist() for p in tp.to_polygons()], FillRule.EvenOdd)
    x0, y0, x1, y1 = cs.bounds()
    return cs.translate([-(x0 + x1) / 2, ARM_Y - (y0 + y1) / 2])


def build_cross():
    shape = outline()
    slabs = [Manifold.extrude(shape, THICK - CHAMFER + 0.01)]
    for i in range(round(CHAMFER / STEP)):
        z = THICK - CHAMFER + i * STEP
        slabs.append(Manifold.extrude(shape.offset(-(i + 1) * STEP, JoinType.Miter), STEP + 0.01).translate([0, 0, z]))
    body = Manifold.batch_boolean(slabs, OpType.Add)
    body -= Manifold.extrude(text_outline(), TEXT_DEPTH + 1).translate([0, 0, THICK - TEXT_DEPTH])
    assert len(body.decompose()) == 1
    return body


def build_bone(length):
    """Half bone with a flat bottom: a shaft (lying cylinder) and two knobs at each end."""
    r, knob = BONE_R * length, BONE_KNOB * length
    L = length / 2 - knob
    m = Manifold.cylinder(2 * L, r, r, 48).rotate([0, 90, 0]).translate([-L, 0, 0])
    for sx in (-1, 1):
        for sy in (-1, 1):
            m += Manifold.sphere(knob, 48).translate([sx * L, sy * knob * 0.55, 0])
    m ^= Manifold.cube([400, 400, 100]).translate([-200, -200, 0])
    assert len(m.decompose()) == 1
    return m


def to_trimesh(m):
    mesh = m.to_mesh()
    t = trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3],
                        faces=np.asarray(mesh.tri_verts), process=False)
    if not t.is_watertight:
        t.update_faces(t.nondegenerate_faces())
        t.remove_unreferenced_vertices()
        t.merge_vertices()
    assert t.is_watertight, "mesh is not watertight"
    return t


def params():
    return {k: v for k, v in globals().items() if k.isupper() and k not in ("OUT", "SCRIPTS", "STEP")}


def draw_sketch(path, bone):
    from sketch import dim, line, name, panel, radius, save, shape, sheet, value
    fig, ax = sheet("Grave cross - names and sizes (mm)", [["front", "section"], ["front", "bone"]],
                    subtitle="Names in CAPS are the parameters at the top of generate.py. "
                             "Ask for a change by name, e.g. \"SPAN 110\" or \"TEXT BOO\".",
                    width_ratios=[1.3, 1], height_ratios=[1, 1.25])

    f = ax["front"]
    panel(f, "Cross - front view (top face)")
    shape(f, outline().to_polygons())
    shape(f, text_outline().to_polygons(), fill="#8d887e", lw=0.4, z=2)
    x = SPAN / 2
    line(f, (-x - 30, 0), (x + 30, 0))
    line(f, (-x - 4, ARM_Y), (x + 4, ARM_Y), "-.", lw=0.7)
    line(f, (0, TOP), (x + 22, TOP), ":")
    line(f, (SPIKE_TIP / 2, -SPIKE_LEN), (x + 22, -SPIKE_LEN), ":")
    line(f, (-x - 4, ARM_Y), (-x - 22, ARM_Y), ":")
    for s in (-1, 1):
        line(f, (s * x, ARM_Y + 4), (s * x, TOP + 16), ":")
    dim(f, (x + 14, 0), (x + 14, TOP), f"TOP = {TOP:g}", off=-4)
    dim(f, (x + 14, -SPIKE_LEN), (x + 14, 0), f"SPIKE_LEN = {SPIKE_LEN:g}", off=-4)
    dim(f, (-x - 14, 0), (-x - 14, ARM_Y), f"ARM_Y = {ARM_Y:g}", off=4)
    dim(f, (-x, TOP + 8), (x, TOP + 8), f"SPAN = {SPAN:g}", off=4)
    dim(f, (-BEAM / 2, 45), (BEAM / 2, 45), f"BEAM = {BEAM:g}", off=0, shift=36)
    c, s1, _ = trefoil_centres((0, TOP), (0, 1))
    radius(f, c, LOBE_R, 35, f"LOBE_R = {LOBE_R:g}", text_at=(30, TOP - 14))
    radius(f, s1, SIDE_R, 215, f"SIDE_R = {SIDE_R:g}", text_at=(-30, TOP - 30))
    value(f, (-TEXT_H * 1.4, ARM_Y - TEXT_H / 3), f"TEXT = \"{TEXT}\"\nTEXT_H = {TEXT_H:g}\nTEXT_DEPTH = {TEXT_DEPTH:g}",
          (-BEAM / 2 - 8, ARM_Y - 40))
    value(f, (SPIKE_ROOT / 2, -2), f"SPIKE_ROOT = {SPIKE_ROOT:g}", (-x + 10, -14))
    value(f, (-SPIKE_TIP / 2, -SPIKE_LEN + 1), f"SPIKE_TIP = {SPIKE_TIP:g}", (-x + 10, -38))
    name(f, (0, TOP - LOBE_R * 0.4), "top lobe", (-x - 18, TOP + 2))
    name(f, (-x + 4, ARM_Y + 4), "arm end (trefoil)", (-x - 18, ARM_Y + 30))
    name(f, (x - 30, ARM_Y - BEAM / 2 + 3), "arm", (x - 4, ARM_Y - 40))
    name(f, (-BEAM / 2 + 3, 22), "beam", (-x + 10, 22))
    name(f, (-SPIKE_ROOT / 4, -15), "spike", (-x + 10, -26))
    name(f, (x + 26, 0), "lava surface", (x + 26, 12))
    for s in (-1, 1):
        f.text(s * (BEAM / 2 + 9), 68, "A", fontsize=12, fontweight="bold", ha="center", va="center", color="#555")
    line(f, (-BEAM / 2 - 6, 68), (BEAM / 2 + 6, 68), "-.", color="#555")
    f.set_xlim(-x - 60, x + 60)
    f.set_ylim(-SPIKE_LEN - 10, TOP + 22)

    s = ax["section"]
    panel(s, "Section A-A (through the beam)")
    b, t, ch = BEAM / 2, THICK, CHAMFER
    shape(s, [[(-b, 0), (b, 0), (b, t - ch), (b - ch, t), (-b + ch, t), (-b, t - ch)]])
    shape(s, [[(-b - 4, -1.2), (b + 4, -1.2), (b + 4, 0), (-b - 4, 0)]], fill="#c9c4b8", lw=0.6)
    dim(s, (-b, 0), (b, 0), f"BEAM = {BEAM:g}", off=-4.5)
    dim(s, (b, 0), (b, t), f"THICK = {THICK:g}", off=-4, upright=True)
    value(s, (b - ch / 2, t - ch / 2), f"CHAMFER = {CHAMFER:g} (45°)", (b + 4, t + 4))
    name(s, (-b / 2, t), "top face (front, you see it)", (-b - 3, t + 4))
    name(s, (-b + 2, 0.5), "bed face (back, flat)", (-b - 6, 3.5))
    name(s, (-b - 2, -0.6), "print bed", (-b - 6, -3.5))
    s.set_xlim(-b - 30, b + 32)
    s.set_ylim(-9, t + 7)

    k = ax["bone"]
    panel(k, f"Bone 1 ... Bone {len(BONES)} - top and side view (Bone 1 shown)")
    length = BONES[0]
    knob = BONE_KNOB * length
    gap = -3.6 * knob
    shape(k, bone.project().to_polygons())
    shape(k, bone.rotate([-90, 0, 0]).project().translate([0, gap]).to_polygons())
    line(k, (-length / 2 - 6, gap), (length / 2 + 6, gap))
    dim(k, (-length / 2, knob * 1.6), (length / 2, knob * 1.6), f"BONES[0] = {length:g}", off=3)
    radius(k, (0, 0), BONE_R * length, -90, f"BONE_R = {BONE_R:g} × length", text_at=(10, -knob * 2.1))
    radius(k, (length / 2 - knob, knob * 0.55), knob, 40, f"BONE_KNOB = {BONE_KNOB:g} × length",
           text_at=(length / 2 + 3, knob * 1.3))
    value(k, (-length / 2, knob * 1.6 + 3), "BONES = [" + ", ".join(f"{v:g}" for v in BONES) + "]",
          (-length / 2 - 4, knob * 3.4))
    name(k, (-length / 2 + knob * 0.5, knob * 0.9), "knob", (-length / 2 - 6, knob * 0.9))
    name(k, (-length / 5, -BONE_R * length * 0.6), "shaft", (-length / 2 - 6, -knob * 1.6))
    name(k, (-length / 4, gap), "flat bottom = bed face", (-length / 2 - 6, gap - 5))
    k.set_xlim(-length / 2 - 34, length / 2 + 40)
    k.set_ylim(gap - 9, knob * 4)

    save(fig, path)


def export_preview(meshes):
    # A plain <script src> instead of fetch(): fetch() of a local file fails when preview.html is opened from disk.
    data = {"params": params(), "parts": {
        n: {"v": np.round(t.vertices, 2).ravel().tolist(), "f": t.faces.ravel().tolist(),
            "size": np.round(t.extents, 1).tolist()} for n, t in meshes.items()}}
    (OUT / "meshes.js").write_text("window.MODEL = " + json.dumps(data, separators=(",", ":")) + ";\n")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    stl = OUT / "stl"
    stl.mkdir(exist_ok=True)
    parts = {"cross": build_cross()}
    for i, length in enumerate(BONES, 1):
        parts[f"bone{i}"] = build_bone(length)
    meshes = {}
    for n, m in parts.items():
        t = to_trimesh(m)
        t.export(stl / f"{n}.stl")
        meshes[n] = t
        print(f"{n}: {t.volume / 1000:.1f} cm³, {np.round(t.extents, 1).tolist()} mm")

    draw_sketch(OUT / "sketch.png", parts["bone1"])
    export_preview(meshes)

    bones = [n for n in meshes if n.startswith("bone")]
    from bambu3mf import write_3mf
    info = {
        "Title": "Graveyard cross in lava with bones",
        "Designer": "3d-model-skills example",
        "Description": (
            f"Flat graveyard cross with trefoil arm ends and engraved {TEXT}. A spike at the bottom goes into "
            f"a lump of lava. Prints lying on its back. The second plate holds {len(BONES)} small half bones with "
            "a flat bottom that lie half sunk around the cross. All white PLA, no supports."),
    }
    write_3mf(OUT / "grave-cross.3mf",
              [[("Cross", meshes["cross"], 1)], [(f"Bone {n[4:]}", meshes[n], 1) for n in bones]],
              plate_names=["1 Cross - white PLA", "2 Bones - white PLA"], info=info,
              filaments=[("Generic PLA", "#F4F1EA")])

    printcheck = SCRIPTS / "printcheck.py"
    subprocess.run([sys.executable, str(printcheck), str(stl / "cross.stl"), "--png", str(OUT / "printcheck.png")], check=False)
    for n in bones:
        subprocess.run([sys.executable, str(printcheck), str(stl / f"{n}.stl")], check=False)


if __name__ == "__main__":
    main()
