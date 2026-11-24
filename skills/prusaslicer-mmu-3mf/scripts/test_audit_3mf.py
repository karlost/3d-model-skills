"""Portable structural tests; fixtures exercise the auditor, not slicer presets."""
import copy,json,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
from xml.etree import ElementTree as E
SCRIPT=Path(__file__).with_name('audit_3mf.py')
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
V=[(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1)]
F=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
def fixtures():
 root=E.Element('model',{'unit':'millimeter','xmlns':NS});E.SubElement(root,'metadata',{'name':'Application'}).text='PrusaSlicer-3.0.0-alpha12'
 res=E.SubElement(root,'resources');objects=[]
 for n in range(2):
  base=n*7
  for i in range(3):
   obj=E.SubElement(res,'object',{'id':str(base+i+1)});mesh=E.SubElement(obj,'mesh');vs=E.SubElement(mesh,'vertices');fs=E.SubElement(mesh,'triangles')
   for x,y,z in V:E.SubElement(vs,'vertex',{'x':str(x+i),'y':str(y),'z':str(z)})
   for a,b,c in F:E.SubElement(fs,'triangle',{'v1':str(a),'v2':str(b),'v3':str(c)})
   obj=E.SubElement(res,'object',{'id':str(base+i+4)});cs=E.SubElement(obj,'components');E.SubElement(cs,'component',{'objectid':str(base+i+1)})
  obj=E.SubElement(res,'object',{'id':str(base+7),'name':'Part '+str(n)});cs=E.SubElement(obj,'components')
  for i in range(3):E.SubElement(cs,'component',{'objectid':str(base+i+4)})
  objects.append({'id':base+7,'volumes':[{'id':base+i+4,'type':'ModelPart','volume_settings':{'extruder':i+1}} for i in range(3)],'object_settings':{'extruder':0}})
 build=E.SubElement(root,'build')
 for n in range(2):E.SubElement(build,'item',{'objectid':str(n*7+7),'transform':f'1 0 0 0 1 0 0 0 1 10 {10+5*n} 0'})
 cfg={'objects':objects,'project':{'id':'','version':1},'config_containers':[{'beds':[{}],'configuration':{'print_settings':{'layer_height':.1},'filament_settings':{'filament_colour':['#FFFFFF','#001122','#FFFF00','#888888','#888888']}},'preset':{'hw_config':{'tools':{'0':{'features':{'nozzle_diameter':.25},'feeder':{'slot_count':5,'base_model':'MMU3'}}}}}}]}
 files={'3D/3dmodel.model':E.tostring(root),'Metadata/PrusaSlicer3_project.json':json.dumps(cfg).encode(),'[Content_Types].xml':b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/><Default Extension="json" ContentType="application/json"/></Types>','_rels/.rels':b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rel1" Target="/3D/3dmodel.model" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'}
 return files
class AuditTests(unittest.TestCase):
 def run_audit(self,files,*args):
  self.assertTrue(SCRIPT.is_file(),'Missing audit_3mf.py: the reusable audit capability is not implemented yet')
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'model.3mf'
   with zipfile.ZipFile(p,'w') as z:
    for n,d in files.items():z.writestr(n,d)
   r=subprocess.run([sys.executable,str(SCRIPT),str(p),*args],capture_output=True,text=True)
   self.assertIn(r.returncode,[0,2],r.stderr)
   return r.returncode,json.loads(r.stdout)
 def test_native_two_objects_six_parts_and_requested_settings(self):
  rc,d=self.run_audit(fixtures(),'--target-major','3','--objects','2','--parts','6','--slots','5','--nozzle','.25','--layer','.1');self.assertEqual(rc,0,d);self.assertEqual(d['format'],'prusa3');self.assertEqual(d['object_count'],2);self.assertEqual(d['model_part_count'],6)
 def test_wrong_nozzle_is_rejected(self):
  rc,d=self.run_audit(fixtures(),'--nozzle','.4');self.assertEqual(rc,2);self.assertIn('nozzle-mismatch',[q['code'] for q in d['errors']])
 def test_bad_triangle_index_is_rejected(self):
  f=fixtures();f['3D/3dmodel.model']=f['3D/3dmodel.model'].replace(b'v1="0"',b'v1="999"',1);rc,d=self.run_audit(f);self.assertEqual(rc,2);self.assertIn('triangle-index',[q['code'] for q in d['errors']])
 def test_component_cycle_is_rejected(self):
  f=fixtures();f['3D/3dmodel.model']=f['3D/3dmodel.model'].replace(b'objectid="1"',b'objectid="7"',1);rc,d=self.run_audit(f);self.assertEqual(rc,2);self.assertIn('component-cycle',[q['code'] for q in d['errors']])
 def test_slot_outside_mmu_is_rejected(self):
  f=fixtures();d=json.loads(f['Metadata/PrusaSlicer3_project.json']);d['objects'][0]['volumes'][0]['volume_settings']['extruder']=6;f['Metadata/PrusaSlicer3_project.json']=json.dumps(d).encode();rc,d=self.run_audit(f);self.assertEqual(rc,2);self.assertIn('extruder-range',[q['code'] for q in d['errors']])
 def test_legacy_single_cooling_value_is_identified_for_five_slots(self):
  f=fixtures();f.pop('Metadata/PrusaSlicer3_project.json');f['Metadata/Slic3r_PE.config']=b'; nozzle_diameter = 0.25,0.25,0.25,0.25,0.25\n; cooling_slowdown_logic = uniform_cooling\n; single_extruder_multi_material = 1\n; layer_height = 0.1\n';rc,d=self.run_audit(f,'--target-major','3');self.assertEqual(rc,2);self.assertIn('legacy-cooling-vector',[q['code'] for q in d['errors']]);self.assertIn('target-format-mismatch',[q['code'] for q in d['errors']])
 def test_legacy_with_expanded_cooling_does_not_get_same_vector_error(self):
  f=fixtures();f.pop('Metadata/PrusaSlicer3_project.json');f['Metadata/Slic3r_PE.config']=b'; nozzle_diameter = 0.25,0.25,0.25,0.25,0.25\n; cooling_slowdown_logic = uniform_cooling,uniform_cooling,uniform_cooling,uniform_cooling,uniform_cooling\n; layer_height = 0.1\n';rc,d=self.run_audit(f);self.assertNotIn('legacy-cooling-vector',[q['code'] for q in d['errors']])
 def test_short_legacy_vector_is_warning_for_target_2(self):
  f=fixtures();f.pop('Metadata/PrusaSlicer3_project.json');f['Metadata/Slic3r_PE.config']=b'; nozzle_diameter = 0.25,0.25,0.25,0.25,0.25\n; cooling_slowdown_logic = uniform_cooling\n';rc,d=self.run_audit(f,'--target-major','2');self.assertEqual(rc,0,d);self.assertIn('legacy-cooling-vector',[q['code'] for q in d['warnings']])
 def test_malformed_native_metadata_returns_json_error(self):
  f=fixtures();f['Metadata/PrusaSlicer3_project.json']=json.dumps({'config_containers':['bad'],'objects':[]}).encode();rc,d=self.run_audit(f);self.assertEqual(rc,2);self.assertIn('unreadable-or-malformed',[q['code'] for q in d['errors']])
 def test_duplicate_content_type_is_rejected(self):
  f=fixtures();f['[Content_Types].xml']=f['[Content_Types].xml'].replace(b'</Types>',b'<Default Extension="model" ContentType="x"/></Types>');rc,d=self.run_audit(f);self.assertEqual(rc,2);self.assertIn('duplicate-content-type',[q['code'] for q in d['errors']])
 def test_static_pass_does_not_claim_slicer_or_print_verification(self):
  rc,d=self.run_audit(fixtures());self.assertEqual(rc,0,d);self.assertFalse(d['slicer_import_verified']);self.assertFalse(d['slicing_verified']);self.assertFalse(d['physical_print_verified'])
if __name__=='__main__':unittest.main()
