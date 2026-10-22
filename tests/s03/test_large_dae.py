"""Large but bounded DAE assets should not inherit the smaller URDF XML limit."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from urdftools.importers import ImportService, Limits


class LargeDaeImportTests(unittest.TestCase):
    def test_dae_may_exceed_urdf_xml_limit_but_stays_under_per_file_limit(self):
        with tempfile.TemporaryDirectory(prefix='large-dae-source-') as source_tmp, \
             tempfile.TemporaryDirectory(prefix='large-dae-storage-') as storage_tmp:
            source = Path(source_tmp)
            (source / 'package.xml').write_text(
                '<?xml version="1.0"?><package><name>test_robot</name><version>0.1.0</version></package>')
            (source / 'robot.urdf').write_text(
                '<?xml version="1.0"?><robot name="large_dae"><link name="base">'
                '<visual><geometry><mesh filename="package://test_robot/meshes/large.dae"/></geometry></visual>'
                '</link></robot>')
            meshes = source / 'meshes'
            meshes.mkdir()
            padding = 'x' * (Limits().xml_bytes + 128)
            (meshes / 'large.dae').write_text(
                '<?xml version="1.0"?><COLLADA><!--' + padding +
                '--><library_geometries><geometry id="mesh"/></library_geometries></COLLADA>')
            self.assertGreater((meshes / 'large.dae').stat().st_size, Limits().xml_bytes)
            self.assertLess((meshes / 'large.dae').stat().st_size, Limits().file_bytes)
            report = ImportService(Path(storage_tmp) / 'imports').ingest(source)
            self.assertEqual(report['status'], 'ready', report)
            self.assertEqual(report['models'][0]['status'], 'ready', report['models'][0])
            self.assertEqual(report['models'][0]['resources'][0]['inspection']['format'], 'dae')


if __name__ == '__main__':
    unittest.main()
