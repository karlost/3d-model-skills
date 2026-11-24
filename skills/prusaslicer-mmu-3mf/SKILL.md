---
name: prusaslicer-mmu-3mf
description: Use when creating, combining, repairing, or validating 3MF projects for PrusaSlicer and MMU/MMU3, especially recessed color inlays, several objects on one plate, misplaced colors, legacy 2.x projects, or crashes loading a 3MF in 3.x. Also applies when changing which face carries a logo. Excludes unrelated Bambu/Orca profile authoring.
---

# PrusaSlicer MMU 3MF

Produce a project for the user's actual PrusaSlicer version, printer, nozzle and material slots. A successful ZIP parse or a test in a different slicer version is insufficient evidence for delivery.

## Start from the intended result

Identify the exact installed binary/version and the requested models, colors, print face and plate arrangement. Preserve existing geometry and settings that the task does not change. Discover current paths; installed app names can be ambiguous on macOS.

- Each physical product is a separate object. Its color volumes share coordinates and explicit material assignments. Several products may share one plate and one configuration.
- MMU3 normally has one physical nozzle and five filament slots. Model part `extruder` values are 1-based material assignments; displayed RGB colors alone do not assign MMU filaments.
- Keep color inlays flush and inside the substrate. Check union reconstruction, mutual volume overlap, wall thickness and glyph legibility.
- For a logo requested on the bed side, first check whether moving the inlays to the other face fulfills the request while preserving body orientation. Inspect functional cavities and overhangs in the final print pose. Changes to supports or assembly are separate design choices.

## Select the version-specific path

Read [formats-and-traps.md](references/formats-and-traps.md) for creation, conversion, combining, or a load crash.

| Target | Required project settings |
|---|---|
| PrusaSlicer 2.x | Legacy `Slic3r_PE.config` plus model/volume metadata |
| PrusaSlicer 3.x | Native `PrusaSlicer3_project.json` matching that release |

Use native save/export in the target version for the final artifact. For programmatic preparation, use a verified template from that same version, preserve the shared coordinate system, then load and save it through that binary. Preserve painted-triangle data when present; the volume-only recipe does not replace painting.

Run the read-only helper with the user's actual requested values:

```sh
python3 scripts/audit_3mf.py project.3mf --target-major 3 --objects 2 --parts 6 --slots 5 --nozzle 0.25 --layer 0.10
```

These numbers are an example. Run `--help` for optional assertions. Exit 0 means static checks passed; import, slicing and printability remain unverified.

## Verify and deliver

Follow [validation.md](references/validation.md). Reopen and slice the exact final project in the target version using its embedded settings and an isolated data directory. Require successful process exit and complete output. Check part placement, material assignments, requested nozzle/layer, actual colored toolpaths, print pose, cavities and wipe-tower clearance. Compare meshes and settings after native roundtrip.

If startup is blocked by filesystem permissions, resolve the necessary access; a test in 2.x does not establish 3.x compatibility. Keep installed user presets unchanged unless the task authorizes changing them.

Deliver the requested file count with direct links. State the version tested and whether evidence came from CLI or GUI. Retain relevant bridge/support warnings and physical-print limitations. A render is a geometry preview, not a photograph.
