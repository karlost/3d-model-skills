"""Runs printcheck on shapes with a known result. Run it after every change to printcheck.py."""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import CrossSection, Manifold

C = Manifold.cube
CASES = {
    "overhang_20mm": (C([10, 10, 10]) + C([30, 10, 3]).translate([0, 0, 10]), 1),
    "bridge_20mm": (C([5, 10, 10]) + C([5, 10, 10]).translate([25, 0, 0]) + C([30, 10, 3]).translate([0, 0, 10]), 0),
    "bridge_55mm": (C([5, 10, 10]) + C([5, 10, 10]).translate([60, 0, 0]) + C([65, 10, 3]).translate([0, 0, 10]), 1),
    "chamfer_45": (CrossSection([[(0, 0), (10, 0), (20, 10), (0, 10)]]).extrude(10)
                   .rotate([90, 0, 0]).translate([0, 10, 0]), 0),
    "horizontal_hole_8": (C([20, 10, 20]) - Manifold.cylinder(12, 4, circular_segments=48)
                          .rotate([90, 0, 0]).translate([10, 11, 10]), 0),
    "floating": (C([10, 10, 5]).translate([0, 0, 3]), 1),
    "ledge_3mm": (C([10, 30, 10]) + C([13, 30, 2]).translate([0, 0, 10]), 1),
    # A ring sticking out of a cylinder, anchored only on the inside (like a filter flange).
    "ring_outward": (Manifold.cylinder(3, 10, circular_segments=64)
                     + (Manifold.cylinder(1, 13, circular_segments=64) - Manifold.cylinder(1, 9.9, circular_segments=64)).translate([0, 0, 2]), 1),
    # Pocket ceiling with a through hole in the middle: the hole walls hang in the air and it sags in reality
    # (frame pocket with a nail hole). With a 0.2 mm sacrificial layer over the hole it is a clean bridge.
    "ceiling_with_hole": (C([20, 20, 5]).translate([-10, -10, 0])
                          - Manifold.cylinder(3, 6, circular_segments=64).translate([0, 0, -0.01])
                          - Manifold.cylinder(6, 1.5, circular_segments=32).translate([0, 0, -0.5]), 1),
    "sacrificial_layer": (C([20, 20, 5]).translate([-10, -10, 0])
                          - Manifold.cylinder(3, 6, circular_segments=64).translate([0, 0, -0.01])
                          - Manifold.cylinder(2, 1.5, circular_segments=32).translate([0, 0, 3.2]), 0),
    # A bridge held up by a post in the middle: the inner outline is support, not a hole.
    "bridge_with_post": (C([5, 20, 10]) + C([5, 20, 10]).translate([25, 0, 0])
                         + C([4, 4, 10]).translate([13, 8, 0]) + C([30, 20, 3]).translate([0, 0, 10]), 0),
    "side_pocket": (C([40, 34, 12]) - C([36, 26.4, 6.4]).translate([-1, 3.8, 3]), 0),
    # A cone pointing down next to a post: starts as a tiny island in the air (slicer: "floating").
    "tip_down": (C([10, 10, 10]) + Manifold.cylinder(4, 0.01, 4, circular_segments=32).translate([14, 5, 6]), 1),
    # A diamond-shaped bone between two joints, bottom edge 0.3 mm above the bed: a long thin bridge.
    "ridge_above_bed": (C([10, 10, 6]) + C([10, 10, 6]).translate([50, 0, 0])
                        + CrossSection([[(0, 0.3), (2.7, 3), (0, 5.7), (-2.7, 3)]]).extrude(60)
                        .rotate([90, 0, 0]).rotate([0, 0, 90]).translate([0, 5, 0]), 1),
    # A thumb torn off the palm: both pieces lie on the bed, it prints, but the part falls apart.
    "two_pieces": (C([20, 10, 4]) + C([10, 4, 4]).translate([0, 12, 0]), 1),
    # Pieces that only touch along a face are one part.
    "touching_pieces": (C([20, 10, 4]) + C([10, 4, 4]).translate([0, 10, 0]), 0),
}


def main():
    tool = Path(__file__).with_name("printcheck.py")
    failed = 0
    with tempfile.TemporaryDirectory() as d:
        for name, (m, expected) in CASES.items():
            me = m.to_mesh()
            path = Path(d) / f"{name}.stl"
            trimesh.Trimesh(np.asarray(me.vert_properties)[:, :3], np.asarray(me.tri_verts)).export(path)
            rc = subprocess.run([sys.executable, str(tool), str(path)], capture_output=True).returncode
            ok = rc == expected
            failed += not ok
            print(f"{'OK  ' if ok else 'FAIL'} {name}: expected {expected}, got {rc}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
