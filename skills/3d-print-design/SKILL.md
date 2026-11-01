---
name: 3d-print-design
description: Design FDM 3D-printable parts end to end - sketch with dimensions, Python generator (manifold3d/trimesh), support-free check, minimal single-feature test print, and a ready-to-print Bambu Studio 3MF project with plates, filaments and print time. Use whenever the user wants a printable part, mount, joint, bracket, adapter or test piece designed, fixed or prepared for printing.
---

# 3D print design

Turn "I need a part that does X" into a project the user only opens in Bambu Studio and prints. The user judges by looking, so show pictures at every step, not walls of text.

Scripts are in `scripts/` next to this file. Python 3.12+ with `pip install manifold3d trimesh numpy matplotlib`.

## First time: printer and filaments

Ask once and suggest the user writes the answer into their CLAUDE.md:
- Printer and bed size (the default template is a Bambu Lab P1S, 256 × 256 mm).
- Filaments they always have (e.g. black/white PLA and PETG). Design only from those unless asked.

## Workflow

1. **Ask only what this step needs.** Get the measurements that decide the fit (pipe diameter, screw size, wall thickness). Never size a functional fit from a dimension estimated from a photo: ask for a measurement or put it in a test first.
2. **Proposal with a sketch.** Every design idea comes with a simple sketch right away: a cross-section or side view with labelled parts and key dimensions (matplotlib PNG or inline SVG). Offer 2-3 variants when the approach is not obvious and let the user pick.
3. **3D preview** for anything that is assembled from several parts: use the `3d-preview` skill.
4. **Generator.** Write `model/generate.py`: parameters at the top in mm, one function per part, parts built with manifold3d and exported with trimesh. Export every part already oriented for printing (z = 0 is the bed).
   - `assert len(part.decompose()) == 1` for every assembled part, so a parameter change that splits it fails at once.
   - Avoid coplanar touching faces in unions: they leave duplicate vertices and the STL stops being watertight. After every `CrossSection.offset(..., Round)` on dense outlines call `.simplify(0.01)`.
   - Print the volume and size of each part.
5. **Printcheck every STL** (never judge printability by eye):
   ```
   python scripts/printcheck.py part.stl
   python scripts/printcheck.py body_pla.stl detail_petg.stl   # several files = one multi-material object
   ```
   Deliver nothing until it says `RESULT: OK without supports`. Take `MATERIAL` warnings seriously: PETG and PLA do not bond. `PIECES` means a part fell apart; use `--multi-piece` only for files that hold several parts on purpose. `--png out.png` draws where the problems are.
6. **Minimal test first.** Before the full part, print only the uncertain feature: one pocket for one magnet, one pin in one hole, one slot. Thinnest walls around it, same orientation as the final part, a few minutes and a fraction of a cm³. Never a whole part or a big cut-out as a "test", never a row of variants. Ask the user how it fits, change one parameter, repeat.
7. **3MF project** with `scripts/bambu3mf.py` (details in its docstring):
   ```python
   sys.path.insert(0, "<skill dir>/scripts")
   from bambu3mf import write_3mf
   write_3mf("part.3mf", [[("Test pin", test_mesh, 1)], [("Bracket", bracket_mesh, 1)]],
             plate_names=["1 Test pin - black PETG", "2 Bracket - black PETG"],
             info={"Title": "...", "Designer": "...", "Description": "what it is, how it prints, how it assembles"},
             filaments=[("Generic PETG", "#1A1A1A")])
   ```
   - One list = one plate. Test pieces on their own plate first.
   - Names short plain English ASCII. `<>:/\|?*"` (above all the colon) make Bambu Studio reject the whole project.
   - Per-part settings as a 4th item, e.g. `{"wall_loops": "3"}` or `{"sparse_infill_density": "100%"}`.
   - Another printer: `template="saved_project.3mf"` (see `scripts/templates/README.md`).
8. **Slice** to get real time and grams (Windows): `python scripts/bambu_slice.py part.3mf`. Never run `bambu-studio.exe --slice` directly: a failed allocation pops an "Out of Memory" dialog over every window and the process crashes; the wrapper contains it on a hidden desktop. On macOS/Linux call the Bambu Studio CLI yourself. Report time and grams per plate.
9. **Hand over**: the 3MF path, what is on each plate, time and grams, the print orientation and why. Opening it in the GUI and printing is the user's job.

## Design rules

**Material and time**
- One filament per part. When two materials are needed, split into separate parts that snap, slide or pin together. If the user asks for colour changes anyway, keep it to one layer-based change per plate and state the swap count (printcheck reports it).
- Smallest and lightest part that does the job.
- Tall thin parts are slow because of the layer count, not the volume. To save time, cut height (shorter, split, print lying down), not grams. Confirm with the slicer.
- Long straight rods: buy a tube (cable conduit, PPR pipe) and print only the joints.

**Orientation and supports**
- Decide the orientation of every part: no supports, accurate functional surfaces (holes and pockets vertical, contact face on the bed), strength along the load.
- Chamfers instead of overhangs, overhangs ≤ 45°, short bridges.
- A hole in a bridge sags: start the hole one layer above the bridge (sacrificial layer) and drill it out.

**Shapes**
- Rings, frames, struts and rods as a flat band lying on the bed (e.g. 10 × 5 mm with chamfered top edges). The outline can curve in plan view, only the cross-section is flat. Round only when the function needs it (sliding into a tube, rotating, visible organic shape).
- Joints: round pin in a round hole. Vertical axis when printed = no overhang. Horizontal hole = teardrop (45° roof), which also stops rotation. A plain round pin needs anti-rotation (a flat or a second pin). Keep joints small.
- A part that goes through a hole: make it drop in from above, with a narrow neck through the hole and a wider top resting on the edge. Put the stop on the side the part would fall away from, so gravity holds it without glue.
- Prefer a small adapter over reprinting a part that already exists.

**Fits (P1S, 0.4 nozzle, 0.20 mm layers, tested)**
- Two flat bands pushed into each other: slot = band thickness + 0.1 mm (snug, OK in PETG). +0.3 mm was clearly loose.
- Squeeze-in snap of a closed rib into a closed spine: worked at ~1.2-1.7 % bending strain in PETG (PETG takes ~4 %, PLA is borderline). Strain grows with band width and squeeze and falls with rib radius squared, so estimate it for every new size instead of copying numbers.
- Flat arrow snaps in the plane of the part do not hold sideways. Do not use them.
- Every uncertain fit goes into a minimal test before the full part.

**Other people's models**
- When mating to a downloaded 3MF/STL, read the real vertices or a slice outline: corners, side length, rotation. Never infer shape or size from the bounding box (a 10 × 10 box was a square rotated 45° with a 7.07 mm side).
- If a measurement disagrees with what the user sees, trust the user and re-check the raw geometry.

**Process**
- MVP first: the next step is the simplest thing that assembles and works. Enclosures and perfect fits come later; mention them in one line.
- After every visible change, show it (render, sketch or preview) before asking anything.
