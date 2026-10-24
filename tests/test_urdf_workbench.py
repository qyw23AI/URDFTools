import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'python'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'scripts'))
from urdftools.importers.service import ImportService
from urdf_workbench import validate, prepare, cad

class WorkbenchTests(unittest.TestCase):
    def test_real_cad_edit_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d); store=d/'imports'; svc=ImportService(store)
            cad(Path('/home/qyw/URDFTools/tests/fixtures/C01/box_mm.step'),d/'cad','mm')
            first=svc.ingest(d/'cad')
            self.assertEqual(first['status'],'ready',first)
            xml=(store/first['operation_id']/'bundle'/first['selected_model']).read_text()
            prepare(store,xml.replace('name="part"','name="changed"'),d/'edited',first)
            second=svc.ingest(d/'edited')
            self.assertEqual(second['status'],'ready',second)
            self.assertTrue(any(a['path'].endswith('.stl') for a in second['assets']))
            self.assertIn('name="part"', (store/first['operation_id']/'bundle'/first['selected_model']).read_text())
            xml2=(store/second['operation_id']/'bundle'/second['selected_model']).read_text()
            prepare(store,xml2,d/'again',second)
            self.assertEqual(svc.ingest(d/'again')['status'],'ready')
    def test_invalid_graphs(self):
        for xml in ['<robot><link name="a"/><link name="b"/></robot>', '<robot><link name="a"/><joint name="j" type="fixed"><parent link="a"/><child link="a"/></joint></robot>', '<!DOCTYPE robot><robot/>']:
            with self.assertRaises(ValueError):validate(xml)
    def test_untrusted_resource(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):prepare(Path(d),'<robot><link name="x"><visual><geometry><mesh filename="/etc/passwd"/></geometry></visual></link></robot>',Path(d)/'out',None)

if __name__=='__main__':unittest.main()
