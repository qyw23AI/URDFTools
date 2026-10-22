"""FreeCAD FCStd revisions: relink same part, report topology conflict."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
from urdftools.modeling.reconcile import compare_cad_versions,ReconcileError
from urdftools.cad.step_reader import inspect_step

def bridge(*args):
    command=[str(ROOT/'.tools/cad-venv/bin/python'),str(ROOT/'scripts/freecad_bridge.py'),*map(str,args)]
    process=subprocess.run(command,capture_output=True,text=True,timeout=120)
    if process.returncode: raise AssertionError(process.stderr[-2000:])

class ReconcileTests(unittest.TestCase):
    def test_real_freecad_relink_and_conflict_preserve_mapping(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for variant in ('base','resized','topology','renamed'):
                fcstd=root/f'{variant}.FCStd';step=root/f'{variant}.step'
                bridge('--make-fixture','--fixture-variant',variant,'--output',fcstd)
                bridge(fcstd,'--output',step)
                self.assertEqual(len(inspect_step(step)['parts']),2)
            baseline=root/'base.step'
            baseline_sha=hashlib.sha256(baseline.read_bytes()).hexdigest()
            names={part['name'] for part in inspect_step(baseline)['parts']}
            self.assertEqual(len(names),2)
            mapping={name:f'Link_{index}' for index,name in enumerate(sorted(names))}
            original=copy.deepcopy(mapping)
            resized=compare_cad_versions(baseline,root/'resized.step',
                expected_baseline_sha256=baseline_sha,link_mapping=mapping)
            self.assertEqual(resized['status'],'review_required')
            self.assertEqual(len(resized['relinks']),2)
            self.assertTrue(any(abs(item['volume_delta_mm3'])>1 for item in resized['relinks']))
            self.assertTrue(resized['requires_human_confirmation'])
            self.assertFalse(resized['automatically_applied'])
            renamed=compare_cad_versions(baseline,root/'renamed.step',
                expected_baseline_sha256=baseline_sha,link_mapping=mapping)
            self.assertEqual(renamed['status'],'review_required')
            self.assertEqual(len(renamed['relinks']),2)
            self.assertTrue(any(item['renamed'] for item in renamed['relinks']))
            topology=compare_cad_versions(baseline,root/'topology.step',
                expected_baseline_sha256=baseline_sha,link_mapping=mapping)
            self.assertEqual(topology['status'],'conflict')
            self.assertTrue(any(item['kind']=='topology_changed' for item in topology['conflicts']))
            self.assertEqual(mapping,original)
            self.assertEqual(topology['link_mapping_preserved'],original)
            mapping_path=root/'mapping.json';mapping_path.write_text(json.dumps(mapping))
            process=subprocess.run([str(ROOT/'.tools/cad-venv/bin/python'),
              str(ROOT/'scripts/model_reconcile.py'),str(baseline),str(root/'topology.step'),
              '--baseline-sha256',baseline_sha,'--mapping',str(mapping_path)],
              capture_output=True,text=True,timeout=60,check=True)
            self.assertEqual(json.loads(process.stdout.splitlines()[0])['status'],'conflict')
            self.assertEqual(hashlib.sha256(baseline.read_bytes()).hexdigest(),baseline_sha)
            with self.assertRaisesRegex(ReconcileError,'changed since mapping'):
                compare_cad_versions(baseline,root/'resized.step',
                    expected_baseline_sha256='0'*64,link_mapping=mapping)

if __name__=='__main__':unittest.main()
