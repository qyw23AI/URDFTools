import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from urdftools.importers import ImportService, Limits
from urdftools.importers.service import mesh_check
F = ROOT / 'tests/fixtures/S03'

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.service = ImportService(self.root / 'imports')

    def good(self, source=None):
        return self.service.ingest(source or F / '中文机器人')

    def test_folder_package_relative_chinese_and_selection(self):
        r = self.good()
        self.assertEqual(r['status'], 'selection_required')
        self.assertEqual(len(r['models']), 2)
        self.assertIsNone(r['selected_model'])
        m = r['models'][0]
        self.assertEqual(m['name'], '中文样机')
        self.assertEqual(m['resources'][0]['path'], m['resources'][1]['path'])
        self.assertEqual(m['resources'][0]['inspection'], dict(format='obj', vertices=3, faces=1))
        selected = self.service.select(r['operation_id'], m['path'])
        self.assertEqual(selected['status'], 'ready')
        self.assertEqual(selected, json.loads((self.root/'imports'/r['operation_id']/'report.json').read_text()))
        self.assertEqual(r['package_map'], {'demo_robot': ['示例包']})

    def test_missing_mesh_report_location_and_failed_selection(self):
        r = self.good()
        selected = self.service.select(r['operation_id'], r['models'][1]['path'])
        self.assertEqual(selected['status'], 'failed')
        finding = selected['models'][1]['findings'][0]
        self.assertEqual(finding['code'], 'missing_resource')
        self.assertIn('02缺失.urdf#element[', finding['location'])
        self.assertIn('不存在.stl', finding['message'])

    def test_zip_matches_folder_bytes_and_models(self):
        folder, archive = self.good(), self.good(F/'valid.zip')
        self.assertEqual(folder['models'], archive['models'])
        self.assertEqual(sorted(folder['assets'], key=lambda a:a['path']), sorted(archive['assets'], key=lambda a:a['path']))
        for asset in archive['assets']:
            data = (self.root/'imports'/archive['operation_id']/'bundle'/asset['path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), asset['sha256'])
            self.assertEqual(len(data), asset['size'])

    def test_zip_escape_absolute_backslash_and_link_are_atomic(self):
        for name in ['traversal.zip','absolute.zip','backslash.zip','symlink.zip']:
            with self.subTest(name=name):
                r = self.good(F/name)
                self.assertEqual(r['status'], 'failed')
                self.assertEqual(r['assets'], [])
                self.assertIn(r['findings'][0]['code'], ['unsafe_path','special_file'])
                self.assertEqual(list((self.root/'imports'/r['operation_id']/'bundle').iterdir()), [])
        self.assertFalse((self.root/'escaped.urdf').exists())

    def test_corrupt_zip(self):
        r = self.good(F/'corrupt.zip')
        self.assertEqual(r['status'], 'failed')
        self.assertEqual(r['findings'][0]['location'], 'corrupt.zip')

    def test_malformed_and_entity_xml(self):
        for name in ['malformed', 'entity']:
            r = self.good(F/name)
            self.assertEqual(r['status'], 'failed')
            self.assertEqual(r['models'][0]['findings'][0]['code'], 'invalid_urdf')
            self.assertNotIn('root:x:', json.dumps(r))

    def test_damaged_mesh_is_not_success(self):
        r = self.good(F/'damaged')
        self.assertEqual(r['status'], 'failed')
        self.assertEqual(r['models'][0]['findings'][0]['code'], 'damaged_resource')

    def test_file_and_byte_budgets(self):
        for limits in [Limits(files=1), Limits(total_bytes=20), Limits(file_bytes=20)]:
            r = ImportService(self.root/str(id(limits)), limits).ingest(F/'中文机器人')
            self.assertEqual(r['status'], 'failed')
            self.assertEqual(r['assets'], [])
            self.assertIn(r['findings'][0]['code'], ['file_limit','size_limit'])

    def test_zip_ratio_and_duplicate(self):
        for name in ['ratio', 'duplicate']:
            path = self.root/(name+'.zip')
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
                if name == 'ratio':
                    z.writestr('huge.obj', b'0'*100000)
                else:
                    z.writestr('a.urdf', 'first')
                    z.writestr('./a.urdf', 'second')
            r = self.good(path)
            self.assertEqual(r['status'], 'failed')
            self.assertEqual(r['findings'][0]['code'], 'zip_limit' if name=='ratio' else 'duplicate_path')

    def test_directory_symlink_rejected_and_input_unchanged(self):
        source = self.root/'source'
        shutil.copytree(F/'中文机器人', source)
        before = {p.relative_to(source).as_posix():p.read_bytes() for p in source.rglob('*') if p.is_file()}
        (source/'escape').symlink_to('/etc')
        r = self.good(source)
        self.assertEqual(r['status'], 'failed')
        self.assertEqual(r['findings'][0]['code'], 'symlink')
        (source/'escape').unlink()
        self.assertEqual(before, {p.relative_to(source).as_posix():p.read_bytes() for p in source.rglob('*') if p.is_file()})

    def custom(self, uri, extra=None):
        source = self.root/'custom'
        source.mkdir(exist_ok=True)
        (source/'test.urdf').write_text(f'<robot name="test"><link name="base"><visual><geometry><mesh filename="{uri}"/></geometry></visual></link></robot>')
        if extra: extra(source)
        return self.good(source)

    def test_external_relative_absolute_and_network_resources(self):
        for uri in ['../outside.obj','/etc/passwd','https://example.com/a.obj','file:///etc/passwd','C:\\mesh.obj']:
            r = self.custom(uri)
            self.assertEqual(r['status'], 'failed')
            self.assertIn(r['models'][0]['findings'][0]['code'], ['resource_path','resource_escape'])

    def test_package_ambiguity_missing_and_no_basename_guess(self):
        for uri in ['package://absent/mesh.obj', 'mesh.obj']:
            r = self.custom(uri, lambda s: (s/'nested').mkdir(exist_ok=True))
            self.assertEqual(r['status'], 'failed')
        def duplicate(s):
            for folder in ['one','two']:
                (s/folder).mkdir()
                (s/folder/'package.xml').write_text('<package><name>same</name></package>')
        r = self.custom('package://same/mesh.obj', duplicate)
        self.assertEqual(r['models'][0]['findings'][0]['code'], 'package_unresolved')

    def test_selection_cannot_escape_or_select_unknown(self):
        r = self.good()
        for operation, model in [('../outside', 'a'), (r['operation_id'], '../outside.urdf')]:
            with self.assertRaises(ValueError): self.service.select(operation, model)

    def test_single_urdf_explicit_scope(self):
        r = self.good(F/'中文机器人/示例包/urdf/01好模型.urdf')
        self.assertEqual(len(r['assets']), 1)
        self.assertEqual(r['status'], 'failed')
        source = self.root/'primitive.urdf'
        source.write_text('<robot name="primitive"><link name="base"/></robot>')
        self.assertEqual(self.good(source)['status'], 'ready')

    def test_snapshot_survives_source_changes_and_reimport_is_new(self):
        source = self.root/'snapshot.urdf'
        original = b'<robot name="original"><link name="base"/></robot>'
        source.write_bytes(original)
        first = self.good(source)
        source.write_text('broken')
        second = self.good(source)
        self.assertNotEqual(first['operation_id'], second['operation_id'])
        self.assertEqual(second['status'], 'failed')
        self.assertEqual((self.root/'imports'/first['operation_id']/'bundle/snapshot.urdf').read_bytes(), original)

    def test_mesh_numeric_validation(self):
        path = self.root/'binary.stl'
        path.write_bytes(b'fixture'.ljust(80,b'\0') + struct.pack('<I',1) + struct.pack('<12fH', *([0.0]*12),0))
        self.assertEqual(mesh_check(path, 4096)['triangles'], 1)
        path.write_bytes(b'fixture'.ljust(80,b'\0') + struct.pack('<I',1) + struct.pack('<12fH', *([float('nan')]*12),0))
        with self.assertRaises(ValueError): mesh_check(path,4096)

    def test_empty_and_storage_overlap(self):
        source = self.root/'empty'
        source.mkdir()
        self.assertEqual(self.good(source)['findings'][0]['code'], 'no_models')
        self.assertEqual(self.good(self.root)['findings'][0]['code'], 'storage_overlap')
