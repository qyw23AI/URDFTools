import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepTools import BRepTools
from OCP.IGESControl import IGESControl_Writer
from OCP.gp import gp_Pnt
from urdftools.cad.exchange import convert_to_step, ExchangeError
from urdftools.cad.step_reader import inspect_step


class ExchangeTests(unittest.TestCase):
    def make_files(self, path):
        box=BRepPrimAPI_MakeBox(gp_Pnt(0,0,0),20,10,5).Shape()
        self.assertTrue(BRepTools.Write_s(box,str(path/'box.brep')))
        writer=IGESControl_Writer('MM',1)
        self.assertTrue(writer.AddShape(box))
        self.assertTrue(writer.Write(str(path/'box.igs')))
        surface_writer=IGESControl_Writer('MM',0)
        self.assertTrue(surface_writer.AddShape(box))
        self.assertTrue(surface_writer.Write(str(path/'surface.iges')))

    def test_real_iges_and_brep_roundtrip_to_step(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); self.make_files(root)
            for extension,unit in [('box.igs',None),('box.brep','mm')]:
                with self.subTest(extension=extension):
                    output=root/(extension+'.step')
                    result=convert_to_step(root/extension,output,brep_unit=unit)
                    self.assertEqual(result['before']['solid_count'],1)
                    self.assertAlmostEqual(result['before']['volume_mm3'],1000,places=5)
                    self.assertAlmostEqual(result['after']['center_of_mass_mm'][0],10,places=5)
                    report=inspect_step(output)
                    self.assertEqual(report['units']['source_length_unit'],'mm')
                    self.assertEqual(len(report['parts']),1)
                    self.assertIn('assembly hierarchy',result['losses'][0])
                    with self.assertRaisesRegex(ExchangeError,'new .step'):
                        convert_to_step(root/extension,output,brep_unit=unit)

    def test_brep_metre_requires_explicit_unit_and_normalizes_to_mm(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            box=BRepPrimAPI_MakeBox(gp_Pnt(0,0,0),0.02,0.01,0.005).Shape()
            self.assertTrue(BRepTools.Write_s(box,str(root/'metre.brep')))
            with self.assertRaisesRegex(ExchangeError,'explicit --brep-unit'):
                convert_to_step(root/'metre.brep',root/'missing.step')
            result=convert_to_step(root/'metre.brep',root/'converted.step',brep_unit='m')
            self.assertAlmostEqual(result['after']['volume_mm3'],1000,places=5)
            self.assertAlmostEqual(result['after']['center_of_mass_mm'][0],10,places=5)

    def test_surface_only_and_native_cad_rejected_without_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); self.make_files(root)
            with self.assertRaisesRegex(ExchangeError,'No closed solid'):
                convert_to_step(root/'surface.iges',root/'surface.step')
            self.assertFalse((root/'surface.step').exists())
            for suffix,label in [('sldasm','SolidWorks'),('fcstd','FreeCAD')]:
                path=root/f'fake.{suffix}'; path.write_bytes(b'not a CAD file')
                with self.assertRaisesRegex(ExchangeError,label):
                    convert_to_step(path,root/f'{suffix}.step')
                self.assertFalse((root/f'{suffix}.step').exists())

    def test_cli_loss_report_is_json(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.make_files(root)
            process=subprocess.run([sys.executable,str(ROOT/'scripts/cad_exchange.py'),str(root/'box.brep'),
                                    '--brep-unit','mm','--output',str(root/'robot.step')],capture_output=True,text=True,timeout=30)
            self.assertEqual(process.returncode,0,process.stderr)
            report=json.loads(process.stdout.splitlines()[0])
            self.assertEqual(report['status'],'converted_geometry_only')
            self.assertEqual(len(report['losses']),4)

if __name__=='__main__':
    unittest.main()
