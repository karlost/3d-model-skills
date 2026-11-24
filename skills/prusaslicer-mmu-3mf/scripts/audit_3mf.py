#!/usr/bin/env python3
"""Read-only ZIP/XML/config audit for PrusaSlicer 2.x/3.x; Python stdlib only.

Exit 0: requested static checks passed. Exit 2: errors. This never launches
PrusaSlicer and cannot establish slicing, support removal or printability.
"""
import argparse,json,math,posixpath,re,sys,zipfile
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as E
NS={'m':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}

def audit(path,args):
 r={'file':str(path),'format':'unknown','producer':None,'object_count':0,'model_part_count':0,'parts':[],'nozzle_mm':[],'layer_mm':None,'material_slots':None,'errors':[],'warnings':[],'slicer_import_verified':False,'slicing_verified':False,'physical_print_verified':False,'geometry_overlap_verified':False,'mesh_manifold_verified':False}
 def issue(code,message,error=True):r['errors' if error else 'warnings'].append({'code':code,'message':message})
 try:
  with zipfile.ZipFile(path) as z:
   names=z.namelist()
   if len(names)!=len(set(names)):issue('duplicate-zip-entry','Repeated ZIP member names.')
   bad=z.testzip()
   if bad:issue('zip-crc','CRC failure: '+bad)
   for required in ['[Content_Types].xml','_rels/.rels','3D/3dmodel.model']:
    if required not in names:issue('missing-package-part',required)
   if r['errors']:return r
   ct=E.fromstring(z.read('[Content_Types].xml'));seen=set()
   for q in ct:
    key=(q.tag.rsplit('}',1)[-1],q.attrib.get('Extension',q.attrib.get('PartName')))
    if key in seen:issue('duplicate-content-type',str(key))
    seen.add(key)
   rels=E.fromstring(z.read('_rels/.rels'));seen=set()
   for q in rels:
    ident=q.attrib.get('Id')
    if ident in seen:issue('duplicate-relationship-id',str(ident))
    seen.add(ident)
    if q.attrib.get('TargetMode')=='External':continue
    target=posixpath.normpath(unquote(q.attrib.get('Target','')).lstrip('/'))
    if target not in names:issue('missing-relationship-target',target)
   root=E.fromstring(z.read('3D/3dmodel.model'))
   r['producer']=next((m.text for m in root.findall('m:metadata',NS) if m.attrib.get('name')=='Application'),None)
   if root.attrib.get('unit','millimeter')!='millimeter':issue('model-units','Model units are not millimeter; verify scaling.',False)
   resource_list=root.findall('m:resources/m:object',NS);resources={}
   for obj in resource_list:
    oid=int(obj.attrib['id'])
    if oid in resources:issue('duplicate-resource-id',str(oid))
    resources[oid]=obj
   for oid,obj in resources.items():
    mesh=obj.find('m:mesh',NS)
    if mesh is not None:
     vv=mesh.findall('m:vertices/m:vertex',NS)
     if not vv:issue('empty-mesh',f'Object {oid} has no vertices.')
     for v in vv:
      if not all(math.isfinite(float(v.attrib[k])) for k in ['x','y','z']):issue('nonfinite-vertex',f'Object {oid}.');break
     for t in mesh.findall('m:triangles/m:triangle',NS):
      if not all(0<=int(t.attrib[k])<len(vv) for k in ['v1','v2','v3']):issue('triangle-index',f'Object {oid}.');break
      if any('segmentation' in k.lower() for k in t.attrib):r['painted_triangles_present']=True
   visited=set();active=set()
   def visit(oid):
    if oid in active:issue('component-cycle',str(oid));return
    if oid in visited:return
    if oid not in resources:issue('missing-object-reference',str(oid));return
    active.add(oid)
    for q in resources[oid].findall('m:components/m:component',NS):visit(int(q.attrib['objectid']))
    active.remove(oid);visited.add(oid)
   for oid in resources:visit(oid)
   items=root.findall('m:build/m:item',NS);r['object_count']=len(items)
   r['build_items']=[dict(q.attrib) for q in items]
   if not items:issue('empty-build','No printable build items.')
   for q in items:
    if int(q.attrib['objectid']) not in resources:issue('missing-build-object',q.attrib['objectid'])
    if 'transform' in q.attrib:
     vals=[float(v) for v in q.attrib['transform'].split()]
     if len(vals)!=12 or not all(math.isfinite(v) for v in vals):issue('invalid-transform','Build transform must contain 12 finite numbers.')
   if 'Metadata/PrusaSlicer3_project.json' in names:
    r['format']='prusa3';meta=json.loads(z.read('Metadata/PrusaSlicer3_project.json'))
    containers=meta.get('config_containers',[]);r['config_container_count']=len(containers)
    r['bed_count']=sum(len(c.get('beds',[])) for c in containers)
    slot_counts=[];layers=[]
    for c in containers:
     cfg=c.get('configuration',{});hw=c.get('preset',{}).get('hw_config',{})
     if 'layer_height' in cfg.get('print_settings',{}):layers.append(float(cfg['print_settings']['layer_height']))
     for tool in hw.get('tools',{}).values():
      if 'nozzle_diameter' in tool.get('features',{}):r['nozzle_mm'].append(float(tool['features']['nozzle_diameter']))
      if 'slot_count' in tool.get('feeder',{}):slot_counts.append(int(tool['feeder']['slot_count']))
    r['material_slots']=max(slot_counts) if slot_counts else None
    r['layer_mm']=layers[0] if layers else None
    if len(set(layers))>1:issue('multiple-layer-profiles','Inspect each configuration container separately.',False)
    for obj in meta.get('objects',[]):
     if int(obj['id']) not in resources:issue('missing-metadata-object',str(obj['id']))
     default=obj.get('object_settings',{}).get('extruder',0)
     for vol in obj.get('volumes',[]):
      if int(vol['id']) not in resources:issue('missing-metadata-volume',str(vol['id']))
      if vol.get('type','ModelPart')!='ModelPart':continue
      ex=int(vol.get('volume_settings',{}).get('extruder',default) or default)
      r['parts'].append({'object':obj['id'],'volume':vol['id'],'extruder':ex})
   elif 'Metadata/Slic3r_PE.config' in names:
    r['format']='prusa-legacy';cfg={}
    for line in z.read('Metadata/Slic3r_PE.config').decode('utf-8-sig').splitlines():
     line=re.sub(r'^\s*;\s?','',line)
     match=re.match(r'^([a-zA-Z0-9_]+)\s*=\s*(.*)$',line)
     if match:cfg[match[1]]=match[2]
    r['nozzle_mm']=[float(q) for q in cfg.get('nozzle_diameter','').split(',') if q.strip()]
    r['layer_mm']=float(cfg['layer_height']) if 'layer_height' in cfg else None
    r['material_slots']=max(len(r['nozzle_mm']),len(cfg.get('filament_colour','').split(';')))
    cool=cfg.get('cooling_slowdown_logic')
    if cool and r['material_slots']>1 and len(cool.split(','))<r['material_slots']:
     issue('legacy-cooling-vector','cooling_slowdown_logic has fewer entries than material slots; PS 3.0.0-alpha12 legacy conversion can index past this vector. Native target-version conversion/testing is required.',args.target_major==3)
    if 'Metadata/Slic3r_PE_model.config' in names:
     model=E.fromstring(z.read('Metadata/Slic3r_PE_model.config'))
     for obj in model.findall('object'):
      for vol in obj.findall('volume'):
       values={q.attrib['key']:q.attrib['value'] for q in vol.findall('metadata')}
       if values.get('volume_type','ModelPart')!='ModelPart':continue
       r['parts'].append({'object':int(obj.attrib['id']),'triangle_range':[int(vol.attrib['firstid']),int(vol.attrib['lastid'])],'extruder':int(values.get('extruder','0'))})
    else:issue('no-volume-metadata','No Prusa volume metadata; material assignment needs inspection.',False)
   else:
    r['format']='geometry-only';issue('no-project-settings','Geometry-only 3MF: no Prusa project print settings.',False)
   r['model_part_count']=len(r['parts'])
   for p in r['parts']:
    ex=p['extruder']
    if ex<0 or (r['material_slots'] is not None and ex>r['material_slots']):issue('extruder-range',str(p))
    elif ex==0:issue('default-extruder','Part inherits an unresolved default; verify its material or painting.',False)
   if args.target_major is not None:
    expected='prusa3' if args.target_major==3 else 'prusa-legacy'
    if r['format']!=expected:issue('target-format-mismatch',f'Target PrusaSlicer {args.target_major}.x project requires {expected}; detected {r["format"]}. This is a delivery-format mismatch, not proof that the ZIP itself is invalid.')
   for key,expected in [('object_count',args.objects),('model_part_count',args.parts),('material_slots',args.slots)]:
    if expected is not None and r[key]!=expected:issue(key+'-mismatch',f'Expected {expected}, detected {r[key]}.')
   if args.nozzle is not None and (not r['nozzle_mm'] or any(abs(q-args.nozzle)>1e-6 for q in r['nozzle_mm'])):issue('nozzle-mismatch',f'Expected {args.nozzle}, detected {r["nozzle_mm"]}.')
   if args.layer is not None and (r['layer_mm'] is None or abs(r['layer_mm']-args.layer)>1e-6):issue('layer-mismatch',f'Expected {args.layer}, detected {r["layer_mm"]}.')
   if r.get('painted_triangles_present'):issue('painted-model','Preserve and verify painting separately; volume extruders alone do not describe all materials.',False)
 except (OSError,zipfile.BadZipFile,E.ParseError,ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError) as exc:
  issue('unreadable-or-malformed',str(exc))
 return r

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('project',type=Path);p.add_argument('--target-major',type=int,choices=[2,3]);p.add_argument('--objects',type=int);p.add_argument('--parts',type=int);p.add_argument('--slots',type=int);p.add_argument('--nozzle',type=float);p.add_argument('--layer',type=float)
 args=p.parse_args();r=audit(args.project,args);r['status']='errors' if r['errors'] else 'static-checks-passed'
 print(json.dumps(r,ensure_ascii=False,indent=2));return 2 if r['errors'] else 0
if __name__=='__main__':sys.exit(main())
