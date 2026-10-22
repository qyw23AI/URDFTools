"""Real M00 revision to named STEP and URDF/ROS integration."""
import json
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from urdftools.modeling.core import apply_project
from urdftools.modeling.assembly import AssemblyError, export_revision_assembly
from urdftools.cad.wizard import inspect_conversion_draft, default_configuration
from urdftools.cad.exporter import write_package_zip

def recipe(width=30):
    return {'schema_version': 1, 'parts': [
        {'name':'Base','material':'user declared','density_kg_m3':2700,
         'profile':{'kind':'rectangle','width_mm':20,'height_mm':10},
         'operation':{'kind':'extrude','distance_mm':5},'placement_mm':[0,0,0]},
        {'name':'Arm','material':'user declared','density_kg_m3':7800,
         'profile':{'kind':'rectangle','width_mm':width,'height_mm':4},
         'operation':{'kind':'extrude','distance_mm':4},'placement_mm':[50,0,0]}]}

class ModelingPipelineTests(unittest.TestCase):
    def test_two_link_revision_to_urdf(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            first=apply_project(root/'project',recipe(),expected_revision=0)
            step=root/'model.step'
            assembly=export_revision_assembly(first['package'],step)
            self.assertEqual(assembly['parts'],['Base','Arm'])
            draft=inspect_conversion_draft(step)
            self.assertEqual({part['name'] for part in draft['parts']},{'Base','Arm'})
            arm=next(part for part in draft['parts'] if part['name']=='Arm')
            self.assertGreater(arm['center_m'][0],0.045)
            config=default_configuration(draft)
            self.assertEqual(len(config['joints']),1)
            config['joints'][0].update({'type':'revolute','axis':[0,0,1],
                'origin_m':[0.05,0,0],'limits':[-1,1],'effort':8,'velocity':3,'confirmed':True})
            package=write_package_zip(step,config,{'Base':2700,'Arm':7800},root/'robot.zip')
            self.assertEqual(package['path'],str(root/'robot.zip'))
            self.assertGreater((root/'robot.zip').stat().st_size,1000)
            validated=subprocess.run([str(ROOT/'.tools/sim-venv/bin/python'),
                str(ROOT/'scripts/validate_cad_package.py'),str(root/'robot.zip')],
                capture_output=True,text=True,check=True)
            validation=json.loads(validated.stdout)
            self.assertEqual(validation['status'],'passed')
            self.assertEqual(validation['link_count'],2)
            self.assertEqual(validation['joint_count'],1)
            second=apply_project(root/'project',recipe(40),expected_revision=1)
            self.assertNotEqual(first['report']['parts'][1]['step_sha256'],second['report']['parts'][1]['step_sha256'])
            restored=apply_project(root/'project',recipe(),expected_revision=2)
            self.assertEqual(first['report']['parts'][1]['step_sha256'],restored['report']['parts'][1]['step_sha256'])
            restored_assembly=export_revision_assembly(restored['package'],root/'restored.step')
            self.assertEqual(restored_assembly['parts'],['Base','Arm'])
            self.assertTrue((Path(first['package'])/'Arm.step').is_file())
            self.assertEqual(json.loads((root/'project/current.json').read_text())['revision'],3)

    def test_tampered_revision_asset_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            first=apply_project(root/'project',recipe(),expected_revision=0)
            asset=Path(first['package'])/'Arm.step'
            asset.write_bytes(asset.read_bytes()+b'changed')
            with self.assertRaisesRegex(AssemblyError,'changed after revision'):
                export_revision_assembly(first['package'],root/'unsafe.step')
            self.assertFalse((root/'unsafe.step').exists())

if __name__=='__main__': unittest.main()
