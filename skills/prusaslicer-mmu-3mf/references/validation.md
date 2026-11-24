# Validation contract

## Evidence levels

| Evidence | What it establishes |
|---|---|
| `audit_3mf.py` | Static ZIP/XML/config consistency and requested counts/settings |
| Mesh and Boolean checks | Closure, winding, dimensions, inclusion, overlaps and reconstruction |
| Native target-version load/save | That exact reader accepted the project and writer serialized it |
| Target-version slicing | Generated toolpaths with the tested configuration |
| Visible GUI state | What the user can see in that application/window |
| Physical print/use | Actual sound, strength, fit, support removal and function |

Report only observed levels. The static helper always marks slicer import, slicing, manifoldness, geometry overlap and physical printing as unverified; these need separate evidence.

## Before the slicer

- Compare the actual part meshes with the intended CAD/reference: all coordinates, bounding boxes, volumes and the union, not only triangle count.
- Check watertightness and consistent winding per printable mesh, positive volumes, no unintended material overlap, and reconstruction of the reference body.
- Confirm the chosen print face. Inspect the first layers, functional cavities and unsupported roofs in that pose. A logo-side change can be made by moving the inlays while retaining body orientation.
- Keep colored parts registered to their substrate. Never arrange individual colors independently or drop each thin inlay to the bed.
- Check nozzle/layer/material-slot values explicitly. Do not infer them from a filename or preset display name.
- For several products on one plate, verify spacing, bed bounds and actual wipe-tower clearance.

Static audit example (substitute requested values):

```sh
python3 scripts/audit_3mf.py candidate.3mf --target-major 3 --objects 2 --parts 6 --slots 5 --nozzle 0.25 --layer 0.10 > audit.json
```

Exit 0 means the selected static assertions passed. Warnings need interpretation. Known alpha12 legacy enum hazards are errors when targeting 3.x and warnings when targeting 2.x or when no target was supplied. Geometry-only 3MF is distinct from a project with embedded printer/material/print settings.

For painted models, preserve segmentation and inspect the actual painted toolpaths. The helper reports painting but does not validate it. Multi-bed/multi-configuration projects need each bed/configuration checked separately; the helper's nozzle/layer expectations are intended for uniform shared-profile jobs.

## Native target-version commands

Resolve the user's installed binary; run its current `--help` and `--version`. Read the selected archive schema. Defaults and flags can differ between 2.x and 3.x. Keep tests in a task-local working directory and use an isolated `--datadir` so production presets are preserved.

Example after setting `task_prusaslicer` to the verified full binary path:

```sh
"$task_prusaslicer" --datadir "$task_slicer_data" --dont-arrange --export-3mf --output roundtrip.3mf candidate.3mf
"$task_prusaslicer" --datadir "$task_slicer_data" --export-gcode --output diagnostic.gcode candidate.3mf
```

Use separate invocations/output paths for separate export actions. Alpha12 rejects repeated `--output` in one command. A successful `--save` option does not establish that an expected auxiliary config file was written; check file existence and inspect the actual embedded JSON/INI. Use `subprocess.run` or an equivalent wrapper to preserve the slicer's real return code. A shell command ending with `tail` can hide a preceding abort code.

Check completion before inspecting G-code: require exit 0 and a complete newly generated file. Partial output from a crashed process is not validation. Compare native roundtrip resource graphs, transforms, object/volume/material counts, profile settings and shared color placement with the original candidate.

Slice the project without external `--load` to prove embedded settings were used. Recheck the delivered file's hash against the successfully sliced input if copying/renaming it afterward. Any post-validation geometry/settings change requires a new relevant test. Adding/replacing a thumbnail also needs package-integrity checks.

## G-code and printability

Verify requested nozzle checks, layer heights/counts and material tools, excluding wipe tower and custom G-code from model color evidence. Pure unretractions (`G1 E...` without XY movement) are not colored model paths. Include G2/G3 arcs when measuring coverage.

At each object's actual logo layer, check all letters, dots, fine strokes and hydraulic openings. An opener with a bottom logo and a taller whistle with a top logo will use colors at different heights; do not require one universal colored-layer interval.

Inspect intended orientation in the GUI when accessible. Preserve warnings such as long bridges and make support-removal limitations explicit. Use exact geometry renders for previews. If GUI attachment fails, say the checks were CLI-based.

## Final package

Keep OPC entries/content-type declarations and relationship IDs unique; verify relationship targets, resource references, triangle indices, finite coordinates and build transforms. Do not duplicate thumbnails/PNG declarations on repeated packaging passes.

Provide the requested artifact count. If the user asks for one combined 3MF, deliver one project containing the separate objects with their registered color parts. Supply STL/INI backups only as requested or clearly labeled supplementary material. Never replace an edited project with a stale file just because it has the expected filename.
