import json
import math
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
FIXTURES=ROOT/'tests/fixtures/E00'

def vec(raw):return [float(value) for value in raw.split()]

class GoldFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((FIXTURES/'manifest.json').read_text())

    def test_inventory_tree_and_context_labels(self):
        cases=self.manifest['cases']
        self.assertEqual(len(cases),9)
        self.assertEqual(self.manifest['origin'],'synthetic_fixture')
        self.assertTrue(self.manifest['not_reference_performance'])
        self.assertEqual({case['file'] for case in cases},{path.name for path in FIXTURES.glob('*.urdf')})
        for case in cases:
            robot=ET.parse(FIXTURES/case['file']).getroot()
            links={item.get('name') for item in robot.findall('link')}
            joints=robot.findall('joint')
            self.assertEqual(len(links),len(robot.findall('link')))
            self.assertEqual(len(joints),len(links)-1)
            parents={joint.find('parent').get('link') for joint in joints}
            children=[joint.find('child').get('link') for joint in joints]
            self.assertEqual(len(children),len(set(children)))
            self.assertEqual(len(links-set(children)),1)
            self.assertTrue(parents<=links and set(children)<=links)
            self.assertEqual(len({item['rule'] for item in case['expected']}),len(case['expected']))
        self.assertEqual(self.manifest['design_context']['quadruped_torso_size_m'],[0.4,0.2,0.1])

    def test_unit_and_joint_axis_faults_have_distinct_evidence(self):
        good=ET.parse(FIXTURES/'quadruped_valid.urdf').getroot()
        unit=ET.parse(FIXTURES/'quadruped_misunit_visual.urdf').getroot()
        good_box=vec(good.find("./link[@name='torso']/visual/geometry/box").get('size'))
        bad_box=vec(unit.find("./link[@name='torso']/visual/geometry/box").get('size'))
        collision=vec(unit.find("./link[@name='torso']/collision/geometry/box").get('size'))
        self.assertEqual([wrong/right for wrong,right in zip(bad_box,good_box)],[1000]*3)
        self.assertEqual(collision,good_box)
        zero=vec(ET.parse(FIXTURES/'quadruped_zero_axis.urdf').getroot().find("./joint[@name='LF_knee']/axis").get('xyz'))
        wrong=vec(ET.parse(FIXTURES/'quadruped_axis_context_mismatch.urdf').getroot().find("./joint[@name='LF_knee']/axis").get('xyz'))
        expected=self.manifest['design_context']['LF_knee_expected_axis']
        self.assertEqual(math.dist(zero,[0,0,0]),0)
        self.assertAlmostEqual(math.dist(wrong,[0,0,0]),1)
        self.assertEqual(sum(a*b for a,b in zip(wrong,expected)),0)
        self.assertEqual(vec(good.find("./joint[@name='LF_knee']/axis").get('xyz')),expected)

    def test_inertia_faults_are_numeric_not_name_only(self):
        triangle=ET.parse(FIXTURES/'humanoid_triangle_violation.urdf').getroot()
        values=triangle.find("./link[@name='torso']/inertial/inertia").attrib
        principal=[float(values[key]) for key in ('ixx','iyy','izz')]
        self.assertTrue(all(x>0 for x in principal))
        self.assertGreater(principal[2],principal[0]+principal[1])
        negative=ET.parse(FIXTURES/'humanoid_negative_inertia.urdf').getroot()
        self.assertLess(float(negative.find("./link[@name='L_thigh']/inertial/inertia").get('ixx')),0)
        healthy=ET.parse(FIXTURES/'humanoid_valid.urdf').getroot()
        for body in healthy.findall('./link/inertial'):
            tensor=body.find('inertia')
            a,b,c=[float(tensor.get(k)) for k in ('ixx','iyy','izz')]
            self.assertTrue(min(a,b,c)>0 and max(a,b,c)<=sum((a,b,c))-max(a,b,c)+1e-12)

    def test_fixed_frame_and_hollow_mass_are_legal_counterexamples(self):
        sensor=ET.parse(FIXTURES/'humanoid_fixed_sensor_frame.urdf').getroot()
        frame=sensor.find("./link[@name='imu_frame']")
        joint=sensor.find("./joint[@name='imu_mount']")
        self.assertIsNone(frame.find('inertial'))
        self.assertEqual(joint.get('type'),'fixed')
        self.assertEqual(joint.find('child').get('link'),'imu_frame')
        hollow=ET.parse(FIXTURES/'hollow_frame_valid.urdf').getroot()
        self.assertEqual(float(hollow.find('./link/inertial/mass').get('value')),2)
        self.assertEqual(vec(hollow.find('./link/inertial/origin').get('xyz')),[0,0,0])
        for visual in hollow.findall('./link/visual'):
            center=vec(visual.find('origin').get('xyz'))
            size=vec(visual.find('geometry/box').get('size'))
            self.assertFalse(all(abs(v)<=s/2 for v,s in zip(center,size)))
        inertia=hollow.find('./link/inertial/inertia')
        values=[float(inertia.get(k)) for k in ('ixx','iyy','izz')]
        for actual,expected in zip(values,[0.010416666666666666,0.027283333333333333,0.0374]):
            self.assertAlmostEqual(actual,expected,places=12)
        self.assertLess(values[2],values[0]+values[1])
        for name in ('humanoid_fixed_sensor_frame.urdf','hollow_frame_valid.urdf'):
            case=next(item for item in self.manifest['cases'] if item['file']==name)
            self.assertEqual(case['expected'],[])
            self.assertIn('positive_boundary',case)

if __name__=='__main__':unittest.main()
