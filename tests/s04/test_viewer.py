"""S04 synthetic URDF package and joints exercise the actual import path."""
import math
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'python'))
from urdftools.importers import ImportService

SOURCE = ROOT/'tests/fixtures/S04/simple_robot'

class ViewerModelTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.storage = Path(tmp.name)/'imports'
        self.report = ImportService(self.storage).ingest(SOURCE)

    def test_fixture_is_real_model_with_one_bounded_revolute_joint(self):
        self.assertEqual(self.report['status'], 'ready')
        tree = ET.parse(self.storage/self.report['operation_id']/'bundle/robot.urdf').getroot()
        self.assertEqual(tree.attrib['name'], 'JointViewerFixture')
        self.assertEqual(len(tree.findall('link')), 2)
        joints = tree.findall('joint')
        self.assertEqual(len(joints), 1)
        joint = joints[0]
        self.assertEqual(joint.attrib['name'], 'shoulder')
        self.assertEqual(joint.attrib['type'], 'revolute')
        self.assertEqual(joint.find('parent').attrib['link'], 'body')
        self.assertEqual(joint.find('child').attrib['link'], 'arm')
        self.assertEqual(joint.find('axis').attrib['xyz'], '0 0 1')
        self.assertTrue(math.isclose(float(joint.find('limit').attrib['lower']), -1.2))
        self.assertTrue(math.isclose(float(joint.find('limit').attrib['upper']), 1.2))

    def test_package_mesh_survives_verified_import(self):
        self.assertEqual(self.report['package_map'], {'viewer_robot': ['.']})
        model = self.report['models'][0]
        self.assertEqual(model['resources'][0]['path'], 'meshes/arm.obj')
        self.assertEqual(model['resources'][0]['inspection']['faces'], 4)
        self.assertEqual(model['status'], 'ready')
        self.assertEqual(len(self.report['assets']), 3)
        self.assertTrue((self.storage/self.report['operation_id']/'bundle/meshes/arm.obj').is_file())

if __name__ == '__main__':
    unittest.main()
