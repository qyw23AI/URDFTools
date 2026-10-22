"""Real FCStd fixture and FreeCADCmd headless STEP roundtrip; requires pinned AppImage."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'python'))
from freecad_bridge import invoke
from urdftools.cad.step_reader import inspect_step


class FreeCadRoundTrip(unittest.TestCase):
    def test_fcstd_feature_document_to_step(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            fcstd=root/'bracket.FCStd'
            fixture=invoke('fixture',None,fcstd)
            self.assertEqual(fixture['status'],'created')
            self.assertEqual(len(fixture['objects']),2)
            before=hashlib.sha256(fcstd.read_bytes()).hexdigest()
            step=root/'bracket.step'
            exported=invoke('export',fcstd,step)
            self.assertEqual(exported['status'],'exported_geometry_only')
            self.assertEqual(len(exported['objects']),2)
            self.assertEqual(exported['reimport']['part_count'],2)
            self.assertEqual(exported['reimport']['source_length_unit'],'mm')
            self.assertEqual(exported['source_sha256'],before)
            self.assertEqual(hashlib.sha256(fcstd.read_bytes()).hexdigest(),before)
            self.assertAlmostEqual(exported['objects'][0]['volume_mm3'],1000-20*3.141592653589793,places=3)
            inspected=inspect_step(step)
            self.assertEqual(inspected['counts']['part_instance_count'],2)
            self.assertEqual(inspected['adapter']['status'],'matched')
            with self.assertRaisesRegex(ValueError,'already exists'):
                invoke('export',fcstd,step)

if __name__=='__main__':
    unittest.main()
