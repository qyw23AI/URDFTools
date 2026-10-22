import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'python'))
from urdftools.cad.exporter import ExportError, write_package_zip, write_package_directory
from urdftools.cad.wizard import default_configuration, inspect_conversion_draft
from urdftools.importers import ImportService


class CadPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT/'tests/fixtures/C00/two_part_mm.step'
        cls.draft = inspect_conversion_draft(cls.source)
        cls.config = default_configuration(cls.draft)
        cls.config['joints'][0].update(type='revolute', axis=[1, 0, 0], limits=[-1.2, 1.2],
                                       effort=10, velocity=2, confirmed=True)
        cls.densities = {part['name']: 2700 for part in cls.draft['parts']}

    def test_real_step_roundtrip_and_floating_mujoco_mass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = write_package_zip(self.source, self.config, self.densities, root/'robot1.zip')
            second = write_package_zip(self.source, self.config, self.densities, root/'robot2.zip')
            self.assertEqual(first['sha256'], second['sha256'])
            self.assertEqual(set(first['files']), {'robot.urdf', 'package.xml', 'CMakeLists.txt', 'metadata.json',
                                                    'meshes/BasePart.stl', 'meshes/OffsetPart.stl'})
            report = ImportService(root/'imports').ingest(root/'robot1.zip')
            self.assertEqual(report['status'], 'ready', report['findings'])
            self.assertEqual(len(report['models'][0]['resources']), 2)
            process = subprocess.run([str(ROOT/'.tools/sim-venv/bin/python'),
                str(ROOT/'scripts/validate_cad_package.py'), str(root/'robot1.zip')],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(process.returncode, 0, process.stderr)
            validation = json.loads(process.stdout)
            self.assertEqual(validation['status'], 'passed')
            self.assertEqual(validation['link_count'], 2)
            self.assertEqual(validation['movable_joint_count'], 1)
            self.assertAlmostEqual(validation['urdf_mass_kg'], 0.003348, places=9)
            self.assertAlmostEqual(validation['mujoco_floating']['mass_kg'], 0.003348, places=9)
            self.assertAlmostEqual(validation['mujoco_raw']['fixed_base_mass_excluded_kg'], 0.0027, places=9)
            self.assertFalse(validation['training_ready'])

    def test_directory_export_reimports_with_same_physics(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = write_package_directory(self.source, self.config, self.densities, root/'robot_dir')
            self.assertTrue((root/'robot_dir/robot.urdf').is_file())
            self.assertEqual(result['metadata']['joint_count'], 1)
            imported = ImportService(root/'imports').ingest(root/'robot_dir')
            self.assertEqual(imported['status'], 'ready', imported['findings'])
            self.assertEqual(len(imported['models'][0]['resources']), 2)
            with self.assertRaisesRegex(ExportError, 'already exists'):
                write_package_directory(self.source, self.config, self.densities, root/'robot_dir')

    def test_missing_material_or_motor_limits_prevent_export(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'robot.zip'
            with self.assertRaisesRegex(ExportError, 'density assignment'):
                write_package_zip(self.source, self.config, {'BasePart': 2700}, target)
            with self.assertRaisesRegex(ExportError, 'density'):
                write_package_zip(self.source, self.config, {'BasePart': 2700, 'OffsetPart': 0}, target)
            changed = copy.deepcopy(self.config)
            del changed['joints'][0]['effort']
            with self.assertRaisesRegex(ExportError, 'effort'):
                write_package_zip(self.source, changed, self.densities, target)
            changed = copy.deepcopy(self.config)
            changed['joints'][0]['confirmed'] = False
            with self.assertRaisesRegex(ValueError, 'human confirmation'):
                write_package_zip(self.source, changed, self.densities, target)
            self.assertFalse(target.exists())

    def test_removed_mesh_fails_reimport_and_independent_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            good = root/'good.zip'
            bad = root/'missing-mesh.zip'
            write_package_zip(self.source, self.config, self.densities, good)
            with zipfile.ZipFile(good) as source, zipfile.ZipFile(bad, 'w') as output:
                for member in source.infolist():
                    if member.filename.endswith('meshes/OffsetPart.stl'):
                        continue
                    output.writestr(member, source.read(member.filename))
            imported = ImportService(root/'imports').ingest(bad)
            self.assertEqual(imported['status'], 'failed')
            self.assertTrue(any(f['code'] in ('missing_resource', 'damaged_resource') for f in imported['models'][0]['findings']))
            process = subprocess.run([str(ROOT/'.tools/sim-venv/bin/python'),
                str(ROOT/'scripts/validate_cad_package.py'), str(bad)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(process.returncode, 2)
            self.assertIn('mesh missing or changed', process.stderr)


if __name__ == '__main__':
    unittest.main()
