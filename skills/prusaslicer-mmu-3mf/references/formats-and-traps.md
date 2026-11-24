# Formats and failure-specific procedures

Read only the sections relevant to the target version. These details were verified against installed PrusaSlicer 2.9.6 and 3.0.0-alpha12 in November 2026; rediscover current behavior when the binary changes.

## Official sources

- [Prusa MMU model preparation](https://help.prusa3d.com/guide/creating-mmu-models-export-model-from-fusion-360_105680)
- [Prusa multipart import and material assignment](https://help.prusa3d.com/guide/g-code-preparation-for-mmu2s_87688)
- [3.0 alpha12 import matrix](https://github.com/prusa3d/PrusaSlicer/blob/version_3.0.0-alpha12/doc/3mf-import-matrix.md)
- [2.9.6 3MF reader/writer](https://github.com/prusa3d/PrusaSlicer/blob/version_2.9.6/src/libslic3r/Format/3mf.cpp)
- [3.0 alpha12 legacy configuration converter](https://github.com/prusa3d/PrusaSlicer/blob/version_3.0.0-alpha12/src/slic3r-shared/src/Slic3r/Biz/Config/ConfigLegacy.cpp)
- [3.0 alpha12 legacy hardware resolver](https://github.com/prusa3d/PrusaSlicer/blob/version_3.0.0-alpha12/src/slic3r-shared/src/Slic3r/Biz/Preset/IO/PresetMetadataLegacyLoader.cpp)

An MMU-ready model is normally a multipart object with common coordinates. Import separate STL parts together as one object and assign their material slots; save the configured project through PrusaSlicer.

## 2.x legacy project

A typical native archive has:

- `3D/3dmodel.model`: geometry, object resources, build transforms.
- `Metadata/Slic3r_PE_model.config`: object metadata, volumes, inclusive triangle ranges `firstid`/`lastid`, per-volume `extruder`, source offsets and matrices.
- `Metadata/Slic3r_PE.config`: complete print configuration in legacy commented INI form.
- OPC content types and relationships, optional thumbnail/wipe-tower metadata.

Color `pid`/RGB values in standard 3MF are not a substitute for the Prusa volume `extruder` metadata. A geometry export can omit the full print configuration. Inspect what was actually saved.

### Raw legacy geometry and placement

When creating a raw legacy archive with multipart ranges but without native per-volume matrices/source offsets, start with an identity build transform. Load it in 2.x and let native export create the correct volume metadata and placement, for example using `--center X,Y --export-3mf`.

A nonidentity build translation on a hand-authored archive without matching volume metadata previously moved only the white body, leaving the colored inlays behind. This caused wipe-tower conflicts and a crash. The remedy is consistent coordinates and a native roundtrip, followed by verification of the UNION and placement of all volumes. Testing each part's volume alone misses displacement.

Once native placement exists, slice that project without recentering it again. When an exporter omits settings, legacy configuration embedding must follow the target writer's format; reslice without an external `--load` to prove the project is self-contained. Every legacy INI entry is prefixed `; `; treat the generated header as a comment too.

## 3.x native project

In alpha12, a native project contains `Metadata/PrusaSlicer3_project.json`, with:

- `objects`: references to the model object and its volume resources; each model volume has `type: ModelPart` and `volume_settings.extruder`.
- `config_containers`: one or more configuration groups; a shared-plate project normally has one group with one bed.
- Each group has `configuration` (printer/print/toolprint/filament/project settings) and `preset.hw_config` (hardware, physical tool and feeder/material slots).

The model resource graph used by the native writer is:

```
build item + placement -> physical object -> color-volume wrappers -> mesh resources
```

A physical object references all of its color volumes. Multiple physical objects each have a build item. Slot 1/2/3 means white/blue/yellow only when the project's filament map says so; color choices are task-specific.

A native MMU3 hardware configuration can have `tools["0"]` as one print head with a feeder of `slot_count: 5`; material-address entries such as `"0.0"` through `"0.4"` are not five physical nozzles.

### Combining models

Use the target application's native combining workflow where practical. For programmatic preparation from a verified native template:

1. Keep the desired printer/print/material configuration, then add each physical product as its own resource graph and object metadata entry.
2. Give every resource a unique ID. Update component references, JSON object/volume IDs and build references together.
3. Keep per-part vertices and transforms in a common coordinate system. Place the physical object once with its build transform; keep both bodies on the bed and clear of each other and the wipe tower.
4. Use one shared configuration group/bed when the user asks for one plate.
5. Export through the target binary with `--dont-arrange` if preserving reviewed placement. Check the resulting native archive rather than assuming the intermediate JSON/schema was sufficient.

Do not relabel a 2.x INI archive as a 3.x project by changing `Application`. Use a real target-version save. Native 3.x settings are not a drop-in legacy INI profile, and 2.9.6 slicing does not validate the 3.x loader.

## Reproduced alpha12 legacy conversion crashes

These are version-specific findings, not a claim that every legacy file is invalid.

| Observed location | Evidence and response |
|---|---|
| `EnumWrapper::set_index` / `fill_config_box_from_legacy` | Five MMU slots with one `cooling_slowdown_logic` enum entry caused out-of-range access. The converter used `values[filament_id]`. Expanding this SAME enum value to five entries removed this failure. Other singleton vectors may deliberately broadcast; inspect their definitions rather than blindly duplicating arbitrary configuration fields. |
| `HwConfig.cpp` / `suggest_name`, `tool == nullptr` | Resolving a legacy CORE One MMU3 custom 0.25 mm setup failed when no selectable matching hardware tool was found. Adding enum entries alone did not resolve this second failure. |
| `spdlog` opening `shared_runtime/log.txt` | Startup failed before import because a hardcoded runtime log was outside the writable sandbox, even with `--datadir`. Obtain the necessary access. This is different evidence from a model/parser crash. |

For the custom 0.25 MMU legacy conversion, the existing official 0.25 tool was made selectable ONLY in an isolated copy of the vendor data by enabling `supports_mmu_025_nozzle` for COREONE. After conversion, native export was verified with that isolated vendor restored to stock. User-installed presets were unchanged. Do not repeat this workaround for other hardware without checking the current resolver and the requested configuration.

Place vendor backups outside the scanned preset directory or use a non-YAML suffix. A backup named `vendor.unmodified.yaml` was interpreted as another preset file, rejected, and caused fallback to stock resources.

## Geometry and face orientation

When the request is to put a logo on the bed-facing side, preserve the functional body's chosen print pose when feasible and move the inlay volumes to the opposite face. Restore the old inlay cavities from the reference body before cutting the new ones. Orient the logo to read correctly from its new outside face.

For a normalized rectangular body spanning Y=0..H and Z=0..T, a rigid 180-degree rotation of only the color volumes about X followed by translation `(0,H,T)` moves a top inlay to the underside and keeps its outside-face reading orientation. Verify inclusion, depth, wall thickness and exact union against the unchanged body; this recipe is not a universal transform for arbitrary parts.

Rotating an entire functional part changes cavity roofs, overhangs and print-bed contact. A closed mesh or a successful slice does not certify a bridge, support removal or mechanical function. If a design tradeoff remains, show its concrete consequences and clarify the choice.

Float32 export can collapse seam triangles. Remove only demonstrated zero-area degeneracies (e.g. `nondegenerate_faces(height=0)`), then reimport and check closure, winding and geometric differences. Broad simplification or welding can alter functional gaps.
