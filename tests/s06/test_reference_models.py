"""S06 validates provenance and imports official Go2/G1 reference packages."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from urdftools.importers import ImportService

FIXTURES = ROOT / 'tests/fixtures/S06'
MODELS = FIXTURES / 'reference_models'
MANIFEST = json.loads((FIXTURES / 'reference_models.json').read_text())


class RealReferenceModelTests(unittest.TestCase):
    def test_upstream_license_and_hash_manifest_are_present(self):
        license_text = (FIXTURES / 'UNITREE_LICENSE').read_text()
        self.assertIn('BSD 3-Clause License', license_text)
        self.assertIn('Copyright (c) 2016-2022 HangZhou YuShu TECHNOLOGY CO.,LTD.', license_text)
        self.assertEqual(MANIFEST['repository'], 'https://github.com/unitreerobotics/unitree_ros')
        self.assertEqual(len(MANIFEST['commit']), 40)
        self.assertIn('BSD-3-Clause', MANIFEST['license'])
        for model in MANIFEST['models'].values():
            folder = ROOT / model['fixture_dir']
            urdf = folder / model['urdf_path']
            self.assertEqual(hashlib.sha256(urdf.read_bytes()).hexdigest(), model['source_urdf_sha256'])
            self.assertEqual(model['source_urdf_sha256'], model['fixture_urdf_sha256'])
            for record in model['fixture_files']:
                file = folder / record['path']
                self.assertTrue(file.is_file(), str(file))
                self.assertEqual(file.stat().st_size, record['size'], str(file))
                self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), record['sha256'], str(file))

    def test_go2_folder_import_preserves_all_mesh_references(self):
        model = MANIFEST['models']['go2']
        folder = ROOT / model['fixture_dir']
        root = ET.parse(folder / model['urdf_path']).getroot()
        self.assertEqual(len(root.findall('link')), 42)
        self.assertEqual(len(root.findall('joint')), 41)
        self.assertEqual(root.attrib['name'].lower().find('go2') >= 0, True)
        package = ET.parse(folder / 'package.xml').getroot()
        self.assertEqual(package.findtext('name'), 'go2_description')
        with tempfile.TemporaryDirectory(prefix='s06-go2-import-') as temp:
            report = ImportService(Path(temp) / 'imports').ingest(folder)
            self.assertEqual(report['status'], 'ready', report)
            self.assertEqual(len(report['models']), 1)
            self.assertEqual(report['models'][0]['status'], 'ready', report['models'][0])
            self.assertGreaterEqual(len(report['models'][0]['resources']), model['mesh_reference_count'])
            self.assertIn('go2_description', report['package_map'])

    def test_g1_zip_import_preserves_relative_mesh_paths(self):
        model = MANIFEST['models']['g1']
        folder = ROOT / model['fixture_dir']
        root = ET.parse(folder / model['urdf_path']).getroot()
        self.assertEqual(len(root.findall('link')), 40)
        self.assertEqual(len(root.findall('joint')), 39)
        package = ET.parse(folder / 'package.xml').getroot()
        self.assertEqual(package.findtext('name'), 'g1_description')
        with tempfile.TemporaryDirectory(prefix='s06-g1-zip-') as temp:
            temp_path = Path(temp)
            archive = temp_path / 'g1_description.zip'
            with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
                for file in sorted(folder.rglob('*')):
                    if file.is_file():
                        zipped.write(file, (Path('g1_description') / file.relative_to(folder)).as_posix())
            report = ImportService(temp_path / 'imports').ingest(archive)
            self.assertEqual(report['status'], 'ready')
            self.assertEqual(len(report['models']), 1)
            self.assertEqual(report['models'][0]['status'], 'ready')
            self.assertGreaterEqual(len(report['models'][0]['resources']), model['mesh_reference_count'])
            self.assertIn('g1_description', report['package_map'])


if __name__ == '__main__':
    unittest.main()
