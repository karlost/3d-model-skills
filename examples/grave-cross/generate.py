"""Parametric model: a graveyard cross stuck in a lump of lava, with small bones around it.

Parts:
  cross  - white PLA, flat cross with trefoil arm ends, chamfered front edges and engraved R.I.P.
           A spike at the bottom goes into the lava. Prints lying on its back.
  bone*  - white PLA, half bones with a flat bottom, lying half sunk around the cross (6 sizes).

Print coordinates: z up (thickness), y along the cross (y=0 lava surface, spike below), x across, sizes in mm.
Run:     python generate.py
Output:  grave-cross.3mf, stl/*.stl, printcheck.png
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import CrossSection, FillRule, JoinType, Manifold, OpType
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath

# ---------- PARAMETERS (mm) ----------
BEAM = 22.0                       # beam width
THICK = 9.0                       # cross thickness = print height
CHAMFER = 2.0                     # 45° chamfer of the front edge
STEP = 0.2                        # chamfer in layer-height steps, the printer makes it that way anyway
TOP = 195.0                       # above the lava, to the end of the top trefoil
CROSS_Y = 133.0                   # axis of the cross arm
SPAN = 130.0                      # arm span to the trefoil ends
LOBE = (9.0, 6.5)                 # trefoil: radius of the middle and side circles
SPIKE = (45.0, 12.0, 2.0)         # spike into the lava: length, width at the cross, tip width
TEXT, TEXT_H, TEXT_DEPTH = "R.I.P.", 11.0, 1.0   # cap height of the letters

BONES = [75.0, 66.0, 58.0, 50.0, 44.0, 38.0]      # small bone lengths
BONE_R, BONE_KNOB = 0.065, 0.10                   # shaft and knob radius as a fraction of the length

OUT = Path(__file__).parent
SCRIPTS = Path(__file__).resolve().parents[2] / "skills/3d-print-design/scripts"


def circle(c, r):
    return CrossSection.circle(r, 96).translate(c)


def rect(x0, y0, x1, y1):
    return CrossSection.square([x1 - x0, y1 - y0]).translate([x0, y0])


def trefoil(end, d):
    """Trefoil arm end. end = outermost point, d = arm direction outwards."""
    R, r = LOBE
    end, d = np.asarray(end, float), np.asarray(d, float)
    n = np.array([-d[1], d[0]])
    c = end - d * R
    side = c - d * 7.0
    return circle(c, R) + circle(side + n * BEAM / 2, r) + circle(side - n * BEAM / 2, r)


def outline():
    R, h = LOBE[0], BEAM / 2
    length, root, tip = SPIKE
    return (rect(-h, 0, h, TOP - R) + rect(-SPAN / 2 + R, CROSS_Y - h, SPAN / 2 - R, CROSS_Y + h)
            + trefoil((0, TOP), (0, 1)) + trefoil((-SPAN / 2, CROSS_Y), (-1, 0)) + trefoil((SPAN / 2, CROSS_Y), (1, 0))
            + CrossSection([[(-root / 2, 0.5), (-tip / 2, -length), (tip / 2, -length), (root / 2, 0.5)]]))


def text_outline():
    prop = FontProperties(family="DejaVu Sans", weight="bold")
    cap = TextPath((0, 0), "H", size=10, prop=prop).get_extents().height / 10
    tp = TextPath((0, 0), TEXT, size=TEXT_H / cap, prop=prop)
    cs = CrossSection([p[:-1].tolist() for p in tp.to_polygons()], FillRule.EvenOdd)
    x0, y0, x1, y1 = cs.bounds()
    return cs.translate([-(x0 + x1) / 2, CROSS_Y - (y0 + y1) / 2])


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


def build_bone(length, r, knob):
    """Half bone with a flat bottom: a shaft (lying cylinder) and two knobs at each end."""
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


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    stl = OUT / "stl"
    stl.mkdir(exist_ok=True)
    parts = {"cross": build_cross()}
    for i, length in enumerate(BONES, 1):
        parts[f"bone{i}"] = build_bone(length, BONE_R * length, BONE_KNOB * length)
    meshes = {}
    for n, m in parts.items():
        t = to_trimesh(m)
        t.export(stl / f"{n}.stl")
        meshes[n] = t
        print(f"{n}: {t.volume / 1000:.1f} cm³, {np.round(t.extents, 1).tolist()} mm")

    bones = [n for n in meshes if n.startswith("bone")]
    sys.path.insert(0, str(SCRIPTS))
    from bambu3mf import write_3mf
    info = {
        "Title": "Graveyard cross in lava with bones",
        "Designer": "3d-model-skills example",
        "Description": (
            "Flat graveyard cross with trefoil arm ends and engraved R.I.P. A spike at the bottom goes into "
            "a lump of lava. Prints lying on its back. The second plate holds 6 small half bones with a flat "
            "bottom that lie half sunk around the cross. All white PLA, no supports."),
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
