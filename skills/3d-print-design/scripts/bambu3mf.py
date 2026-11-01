"""Writes a Bambu Studio 3MF project: several plates, parts already placed.

    from bambu3mf import write_3mf
    write_3mf("project.3mf", [
        [("frame", mesh_frame)],                      # plate 1
        [("holder", mesh_holder), ("cap", mesh)],     # plate 2
    ], plate_names=["Frame - PETG", "Holder - PETG"],
       info={"Title": "...", "Designer": "...", "Description": "..."},
       filaments=[("Generic PETG", "#E0F0FF80"), ("Generic PLA", "#C12E1E")])

A part can also be a triple (name, mesh, filament), where filament is a 1-based index into `filaments`,
or a quadruple (name, mesh, filament, {"wall_loops": "3"}): print settings for that part only
(right click on the object in the GUI), keys and values as in project_settings.config.
Multi-colour object: instead of a mesh, a list [(name, mesh, filament), ...] in shared coordinates,
e.g. ("sign", [("base", m1, 1), ("text", m2, 2)]). It is saved as one object with parts.

info goes to the Project tab in Bambu Studio (keys as in its export: Title, Designer,
Description, License, Copyright, Origin).

Meshes are trimesh.Trimesh already oriented for printing (z=0 is the bed). They are placed side by
side in the middle of the plate. Filaments are Bambu Studio system presets by name; without `filaments`
the project keeps one slot of Bambu PLA Basic. A filament can also be a triple (name, colour, preset changes),
e.g. {"filament_scarf_seam_type": "external"}: Bambu Studio 2 takes the scarf seam from the filament only.
process = project-wide process changes, e.g. {"enable_prime_tower": "0"} or
{"flush_volumes_matrix": [...]} (n×n, row = from filament, column = to filament).

template = printer, process and plate type of the project. Default: templates/p1s_project_settings.config
(P1S 0.4 nozzle, 0.20mm Standard, Textured PEI). Another printer: in Bambu Studio make a project with
ONE filament and system presets only, save it as .3mf and pass its path. The bed size is read from it.

Filament presets are read from the Bambu Studio install. Set BAMBU_STUDIO_PROFILES to its
resources/profiles/BBL/filament folder if it is not found.
"""
import datetime
import json
import math
import os
import zipfile
from xml.sax.saxutils import escape

from pathlib import Path

import numpy as np
import trimesh

PLATE_GAP = 1 / 5           # Bambu Studio arranges plates in a grid with a 20 % gap
SPACING = 8.0
# Without project_settings.config Bambu Studio reports "invalid config", loads the geometry only
# and drops the plates. The template comes from a project saved in the GUI with system presets only
# (different_settings_to_system empty).
TEMPLATE = Path(__file__).with_name("templates") / "p1s_project_settings.config"
PROFILE_DIRS = [
    os.environ.get("BAMBU_STUDIO_PROFILES", ""),
    "C:/Program Files/Bambu Studio/resources/profiles/BBL/filament",
    "/Applications/BambuStudio.app/Contents/Resources/profiles/BBL/filament",
]
PRESET_META = {"name", "inherits", "from", "setting_id", "instantiation", "type", "description",
               "filament_id", "compatible_printers", "compatible_printers_condition"}


def _profiles():
    for d in PROFILE_DIRS:
        if d and Path(d).is_dir():
            return Path(d)
    raise FileNotFoundError("Bambu Studio filament presets not found. Set BAMBU_STUDIO_PROFILES "
                            "to <Bambu Studio>/resources/profiles/BBL/filament.")


def _resolve_preset(name):
    # System presets inherit via "inherits"; the project needs the merged values, otherwise
    # PETG would get the temperatures of the default template (PLA).
    index = {}
    for f in _profiles().rglob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if "name" in d:
            index[d["name"]] = d

    def chain(n):
        d = index[n]
        out = dict(chain(d["inherits"])) if d.get("inherits") else {}
        out.update(d)
        return out
    return chain(name)


def _load_template(path):
    path = Path(path)
    if path.suffix.lower() == ".3mf":
        with zipfile.ZipFile(path) as z:
            return json.loads(z.read("Metadata/project_settings.config").decode("utf-8"))
    return json.loads(path.read_text(encoding="utf-8"))


def _bed(cfg):
    pts = [tuple(map(float, p.split("x"))) for p in cfg["printable_area"]]
    return max(x for x, _ in pts), max(y for _, y in pts)


def _project_settings(cfg, filaments, process=None):
    if filaments:
        _apply_filaments(cfg, filaments)
    if process:
        # After the filaments, they would otherwise overwrite e.g. flush_volumes_matrix.
        cfg.update(process)
        diff = cfg["different_settings_to_system"]
        diff[0] = ";".join(sorted({*filter(None, diff[0].split(";")), *process}))
    return json.dumps(cfg, indent=4)


def _apply_filaments(cfg, filaments):
    names = [f[0] for f in filaments]
    overrides = [f[2] if len(f) > 2 else {} for f in filaments]
    presets = [{**_resolve_preset(name), **changes} for name, changes in zip(names, overrides)]
    n = len(filaments)
    for key, val in cfg.items():
        # Filament keys are a 1-item list in a single-filament template.
        if key in PRESET_META or not isinstance(val, list) or len(val) != 1:
            continue
        if all(key in p for p in presets):
            col = [p[key] if isinstance(p[key], list) else [p[key]] for p in presets]
            if all(len(c) == 1 for c in col):
                cfg[key] = [c[0] for c in col]
    for key in ("default_filament_colour", "enable_overhang_bridge_fan", "enable_pressure_advance",
                "overhang_threshold_participating_cooling", "pressure_advance"):
        if isinstance(cfg.get(key), list) and len(cfg[key]) == 1:
            cfg[key] = cfg[key] * n
    cfg["filament_settings_id"] = names
    cfg["filament_colour"] = [f[1] for f in filaments]
    cfg["filament_ids"] = [p["filament_id"] for p in presets]
    cfg["flush_volumes_matrix"] = [str(0 if i == j else 280) for i in range(n) for j in range(n)]
    cfg["flush_volumes_vector"] = cfg["flush_volumes_vector"][:1] * (2 * n)
    diff = cfg["different_settings_to_system"]
    cfg["different_settings_to_system"] = [diff[0], *[";".join(sorted(changes)) for changes in overrides], diff[-1]]
    # Same shape (process, filaments, printer). With 1 filament in this list and more filaments
    # in the project, the 2.08 CLI crashes with an "Out of Memory" dialog (the GUI does not), verified 2026-10-17.
    group = cfg["inherits_group"]
    cfg["inherits_group"] = [group[0], *[""] * n, group[-1]]


def _plate_origin(i, n, bed):
    cols = math.ceil(math.sqrt(n))
    col, row = i % cols, i // cols
    return col * bed[0] * (1 + PLATE_GAP), -row * bed[1] * (1 + PLATE_GAP)


def _layout(meshes, bed):
    # Simple row packing; returns the offset (dx, dy) of each part from the plate centre.
    rows, row, row_w, row_h = [], [], 0.0, 0.0
    for m in meshes:
        w, h = m.extents[0], m.extents[1]
        if row and row_w + SPACING + w > bed[0] - 10:
            rows.append((row, row_w, row_h)); row, row_w, row_h = [], 0.0, 0.0
        row.append(m); row_w += (SPACING if len(row) > 1 else 0) + w; row_h = max(row_h, h)
    if row:
        rows.append((row, row_w, row_h))
    total_h = sum(r[2] for r in rows) + SPACING * (len(rows) - 1)
    if total_h > bed[1] - 10 or max(r[1] for r in rows) > bed[0] - 10:
        raise ValueError("the parts do not fit on one plate")
    offsets, y = [], total_h / 2
    for row, row_w, row_h in rows:
        x = -row_w / 2
        for m in row:
            cx = x + m.extents[0] / 2
            cy = y - row_h / 2
            offsets.append((cx, cy))
            x += m.extents[0] + SPACING
        y -= row_h + SPACING
    return offsets


NS = ('xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
      'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
      'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p"')
HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n'
REL_3D = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"


def _mesh_xml(m):
    v = "".join(f'<vertex x="{a:.6f}" y="{b:.6f}" z="{c:.6f}"/>' for a, b, c in m.vertices)
    t = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in m.faces)
    return f"<mesh><vertices>{v}</vertices><triangles>{t}</triangles></mesh>"


def _uuid(kind, n):
    return f"{kind:04x}{n:04x}-61cb-4c03-9d28-80fed5dfa1dc"


def _info_xml(info):
    today = datetime.date.today().isoformat()
    meta = {"CreationDate": today, "ModificationDate": today, **info}
    return "".join(f'<metadata name="{k}">{escape(str(v))}</metadata>' for k, v in meta.items())


def write_3mf(path, plates, plate_names=None, info=None, filaments=None, process=None, template=TEMPLATE):
    # The structure matches the 3MF that Bambu Studio 2.x exports (--export-3mf): each part has
    # its own file in 3D/Objects and a wrapper object with a component. A flat 3MF without this
    # structure makes Bambu Studio crash.
    # Bambu Studio 2.x rejects the whole project ("Invalid name") when a plate or part name contains
    # any of these characters (verified 2026-10-30 with a colon in a plate name).
    names = list(plate_names or []) + [p[0] for plate in plates for p in plate]
    names += [c[0] for plate in plates for p in plate if isinstance(p[1], list) for c in p[1]]
    bad = [s for s in names if set(s) & set('<>:/\\|?*"')]
    assert not bad, f'Bambu Studio does not allow <>:/\\|?*" in names: {bad}'
    cfg = _load_template(template)
    bed = _bed(cfg)
    files, wrappers, items, settings, plate_xml, rels = {}, [], [], [], [], []
    n, next_id = 0, 0
    for pi, plate in enumerate(plates):
        ox, oy = _plate_origin(pi, len(plates), bed)
        meshes = []
        for name, m, *extra in plate:
            fil = extra[0] if extra else 1
            comps = m if isinstance(m, list) else [(name, m, fil)]
            comps = [(cn, cm.copy(), cf) for cn, cm, cf in comps]
            whole = trimesh.util.concatenate([cm for _, cm, _ in comps])
            shift = -np.array([*whole.bounds.mean(axis=0)[:2], whole.bounds[0][2]])
            for _, cm, _ in comps:
                cm.apply_translation(shift)
            whole.apply_translation(shift)
            meshes.append((name, comps, whole, fil, extra[1] if len(extra) > 1 else {}))
        offsets = _layout([w for _, _, w, _, _ in meshes], bed)
        instances = []
        for (name, comps, _, fil, overrides), (dx, dy) in zip(meshes, offsets):
            n += 1
            mesh_ids = list(range(next_id + 1, next_id + 1 + len(comps)))
            obj_id = next_id + len(comps) + 1
            next_id = obj_id
            fname = f"3D/Objects/object_{n}.model"
            files[fname] = (f'{HEAD}<model unit="millimeter" xml:lang="en-US" {NS}>'
                            '<metadata name="BambuStudio:3mfVersion">1</metadata><resources>'
                            + "".join(f'<object id="{mid}" p:UUID="{_uuid(1, mid)}" type="model">{_mesh_xml(cm)}</object>'
                                      for mid, (_, cm, _) in zip(mesh_ids, comps)) +
                            '</resources><build/></model>')
            rels.append(f'<Relationship Target="/{fname}" Id="rel-{n}" Type="{REL_3D}"/>')
            wrappers.append(
                f'<object id="{obj_id}" p:UUID="{_uuid(2, n)}" type="model"><components>'
                + "".join(f'<component p:path="/{fname}" objectid="{mid}" p:UUID="{_uuid(3, mid)}" '
                          'transform="1 0 0 0 1 0 0 0 1 0 0 0"/>' for mid in mesh_ids) +
                '</components></object>')
            tx, ty = ox + bed[0] / 2 + dx, oy + bed[1] / 2 + dy
            items.append(f'<item objectid="{obj_id}" p:UUID="{_uuid(4, n)}" '
                         f'transform="1 0 0 0 1 0 0 0 1 {tx:.3f} {ty:.3f} 0" printable="1"/>')
            nm = escape(name)
            settings.append(
                f'<object id="{obj_id}"><metadata key="name" value="{nm}"/>'
                f'<metadata key="extruder" value="{comps[0][2]}"/>'
                + "".join(f'<metadata key="{escape(k)}" value="{escape(str(v))}"/>' for k, v in overrides.items())
                + "".join(f'<part id="{mid}" subtype="normal_part"><metadata key="name" value="{escape(cn)}"/>'
                          '<metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>'
                          f'<metadata key="extruder" value="{cf}"/></part>'
                          for mid, (cn, _, cf) in zip(mesh_ids, comps)) +
                '</object>')
            instances.append(
                f'<model_instance><metadata key="object_id" value="{obj_id}"/>'
                f'<metadata key="instance_id" value="0"/></model_instance>')
        plate_xml.append(
            f'<plate><metadata key="plater_id" value="{pi + 1}"/><metadata key="plater_name" value="{escape(plate_names[pi] if plate_names else "", {'"': "&quot;"})}"/>'
            f'<metadata key="locked" value="false"/>{"".join(instances)}</plate>')

    model = (f'{HEAD}<model unit="millimeter" xml:lang="en-US" {NS}>'
             '<metadata name="Application">BambuStudio-02.08.02.61</metadata>'
             f'{_info_xml(info or {})}'
             '<metadata name="BambuStudio:3mfVersion">1</metadata>'
             f'<resources>{"".join(wrappers)}</resources>'
             f'<build p:UUID="2c7c17d8-22b5-4d84-8835-1976022ea369">{"".join(items)}</build></model>')
    config = f'{HEAD}<config>{"".join(settings)}{"".join(plate_xml)}<assemble></assemble></config>'
    content_types = (f'{HEAD}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
                     '<Default Extension="png" ContentType="image/png"/></Types>')
    root_rels = (f'{HEAD}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 f'<Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="{REL_3D}"/></Relationships>')
    model_rels = (f'{HEAD}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                  f'{"".join(rels)}</Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("3D/3dmodel.model", model)
        z.writestr("3D/_rels/3dmodel.model.rels", model_rels)
        for fname, data in files.items():
            z.writestr(fname, data)
        z.writestr("Metadata/model_settings.config", config)
        z.writestr("Metadata/project_settings.config", _project_settings(cfg, filaments, process))
