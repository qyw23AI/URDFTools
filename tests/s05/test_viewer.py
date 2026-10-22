"""S05 viewer analysis fixture is imported through the real package importer."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from urdftools.importers import ImportService

SOURCE = ROOT / 'tests/fixtures/S05/simple_robot'


class ViewerAnalysisFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.storage = Path(self.tmp.name) / 'imports'
        self.source_urdf = SOURCE / 'robot.urdf'
        self.source_hash = hashlib.sha256(self.source_urdf.read_bytes()).hexdigest()
        self.report = ImportService(self.storage).ingest(SOURCE)
        self.bundle = self.storage / self.report['operation_id'] / 'bundle'

    def test_explicit_inertial_and_missing_inertial_are_distinguishable(self):
        self.assertEqual(self.report['status'], 'ready')
        root = ET.parse(self.bundle / 'robot.urdf').getroot()
        links = {link.attrib['name']: link for link in root.findall('link')}
        body_inertial = links['body'].find('inertial')
        self.assertIsNotNone(body_inertial)
        self.assertEqual(float(body_inertial.find('mass').attrib['value']), 1.25)
        self.assertEqual(body_inertial.find('origin').attrib['xyz'], '0.01 0 0')
        tensor = body_inertial.find('inertia')
        self.assertEqual([float(tensor.attrib[key]) for key in ('ixx', 'ixy', 'ixz', 'iyy', 'iyz', 'izz')],
                         [0.01, 0.0, 0.0, 0.02, 0.0, 0.03])
        self.assertIsNone(links['arm'].find('inertial'),
                          'missing source inertia must stay missing, never be rewritten to zeros')

    def test_collision_and_visual_geometry_are_distinct_and_source_is_unchanged(self):
        root = ET.parse(self.bundle / 'robot.urdf').getroot()
        body = next(link for link in root.findall('link') if link.attrib['name'] == 'body')
        visual_size = body.find('visual/geometry/box').attrib['size']
        collision_size = body.find('collision/geometry/box').attrib['size']
        self.assertEqual(visual_size, '0.3 0.2 0.08')
        self.assertEqual(collision_size, '0.34 0.24 0.12')
        self.assertNotEqual(visual_size, collision_size)
        self.assertEqual(hashlib.sha256(self.source_urdf.read_bytes()).hexdigest(), self.source_hash)
        self.assertEqual((self.bundle / 'robot.urdf').read_bytes(), self.source_urdf.read_bytes())
        resources = self.report['models'][0]['resources']
        self.assertTrue(any(resource.get('path') == 'meshes/arm.obj' for resource in resources))
        self.assertTrue((self.bundle / 'meshes/arm.obj').is_file())


if __name__ == '__main__':
    unittest.main()
