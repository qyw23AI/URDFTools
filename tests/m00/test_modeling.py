import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
from urdftools.modeling.core import apply_project, build_part, ModelingError
from build123d import import_step


def two_part_recipe():
    return {'schema_version':1,'parts':[
        {'name':'Bracket','material':'Aluminium 6061 (user declared)','density_kg_m3':2700,
         'profile':{'kind':'rectangle','width_mm':20,'height_mm':10,
                    'holes':[{'center_mm':[0,0],'radius_mm':2}]},
         'operation':{'kind':'extrude','distance_mm':5},
         'modifiers':[{'kind':'fillet','parallel_axis':'Z','radius_mm':0.5}]},
        {'name':'ArmLink','material':'Steel (user declared)','density_kg_m3':7800,
         'profile':{'kind':'rectangle','width_mm':30,'height_mm':4},
         'operation':{'kind':'extrude','distance_mm':4},
         'modifiers':[{'kind':'subtract_cylinder','center_mm':[0,0,2],
                       'radius_mm':1,'height_mm':6}]}]}


class ModelingTests(unittest.TestCase):
    def test_bracket_two_links_mass_and_step_mesh(self):
        with tempfile.TemporaryDirectory() as folder:
            result=apply_project(folder,two_part_recipe(),expected_revision=0)
            self.assertEqual(result['revision'],1)
            self.assertEqual(len(result['report']['parts']),2)
            root=Path(result['package'])
            bracket,arm=result['report']['parts']
            self.assertGreater(bracket['volume_mm3'],900)
            self.assertLess(bracket['volume_mm3'],950)
            self.assertGreater(arm['volume_mm3'],460)
            self.assertLess(arm['volume_mm3'],480)
            self.assertAlmostEqual(bracket['mass_kg'],bracket['volume_mm3']*2700/1e9,places=9)
            self.assertAlmostEqual(arm['mass_kg'],arm['volume_mm3']*7800/1e9,places=9)
            for part in result['report']['parts']:
                step=import_step(str(root/(part['name']+'.step')))
                self.assertAlmostEqual(step.volume,part['volume_mm3'],places=5)
                self.assertGreater((root/(part['name']+'.stl')).stat().st_size,100)
                self.assertTrue(all(math.isfinite(x) for row in part['inertia_com_kg_m2'] for x in row))

    def test_parameter_change_recomputes_mass_and_inertia(self):
        with tempfile.TemporaryDirectory() as folder:
            first=apply_project(folder,two_part_recipe(),expected_revision=0)
            changed=two_part_recipe();changed['parts'][1]['profile']['width_mm']=45
            second=apply_project(folder,changed,expected_revision=1)
            arm1,arm2=first['report']['parts'][1],second['report']['parts'][1]
            self.assertGreater(arm2['mass_kg'],arm1['mass_kg']*1.4)
            self.assertGreater(arm2['inertia_com_kg_m2'][1][1],arm1['inertia_com_kg_m2'][1][1])
            self.assertEqual(json.loads((Path(folder)/'current.json').read_text())['revision'],2)
            self.assertTrue((Path(first['package'])/'ArmLink.step').is_file())

    def test_invalid_sketch_does_not_change_current_revision(self):
        with tempfile.TemporaryDirectory() as folder:
            first=apply_project(folder,two_part_recipe(),expected_revision=0)
            pointer=(Path(folder)/'current.json').read_bytes()
            invalid=two_part_recipe();invalid['parts'][0]['profile']['holes'][0]['radius_mm']=10
            with self.assertRaisesRegex(ModelingError,'crosses sketch boundary'):
                apply_project(folder,invalid,expected_revision=1)
            self.assertEqual((Path(folder)/'current.json').read_bytes(),pointer)
            self.assertEqual(sorted(p.name for p in (Path(folder)/'revisions').iterdir()),['000001'])
            with self.assertRaisesRegex(ModelingError,'Stale revision'):
                apply_project(folder,two_part_recipe(),expected_revision=0)
            self.assertTrue((Path(first['package'])/'report.json').is_file())

    def test_revolve_boolean_and_bad_modifier(self):
        ring={'profile':{'kind':'polygon','points_mm':[[5,0],[10,0],[10,4],[5,4]]},
              'operation':{'kind':'revolve','axis':'Y','angle_deg':360}}
        shape=build_part(ring)
        self.assertAlmostEqual(shape.volume,math.pi*(10**2-5**2)*4,places=4)
        ring['modifiers']=[{'kind':'add_box','size_mm':[2,2,2],'center_mm':[7.5,0,2]}]
        self.assertGreater(build_part(ring).volume,shape.volume)
        ring['modifiers']=[{'kind':'execute_python','script':'raise Exception()'}]
        with self.assertRaisesRegex(ModelingError,'Unsupported modifier'):
            build_part(ring)

if __name__=='__main__':
    unittest.main()
