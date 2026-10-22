import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
from urdftools.agent.facade import TOOLS
from urdftools.modeling.core import apply_project
from urdftools.modeling.assembly import export_revision_assembly
from urdftools.cad.wizard import inspect_conversion_draft, default_configuration
from urdftools.cad.exporter import write_package_zip

RECIPE={'schema_version':1,'parts':[
    {'name':'Base','material':'declared','density_kg_m3':2700,'profile':{'kind':'rectangle','width_mm':20,'height_mm':10},'operation':{'kind':'extrude','distance_mm':5},'placement_mm':[0,0,0]},
    {'name':'Arm','material':'declared','density_kg_m3':7800,'profile':{'kind':'rectangle','width_mm':30,'height_mm':4},'operation':{'kind':'extrude','distance_mm':4},'placement_mm':[50,0,0]}]}

class FacadeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='a02-workspace-')
        self.addCleanup(self.temp.cleanup)
        self.workspace=Path(self.temp.name)
        self.python=str(ROOT/'.tools/model-venv/bin/python')
        self.env={**os.environ,'PYTHONPATH':str(ROOT/'python')}

    def cli(self,name,args):
        run=subprocess.run([self.python,'-m','urdftools','tool','--workspace',str(self.workspace),
            '--name',name,'--arguments',json.dumps(args)],cwd=ROOT,env=self.env,capture_output=True,text=True,timeout=180)
        return run.returncode,json.loads(run.stdout)

    def mcp(self,name,args):
        child=subprocess.Popen([self.python,'-m','urdftools','mcp','--workspace',str(self.workspace)],
            cwd=ROOT,env=self.env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            def rpc(i,method,params=None):
                req={'jsonrpc':'2.0','id':i,'method':method}
                if params is not None:req['params']=params
                child.stdin.write(json.dumps(req)+'\n');child.stdin.flush()
                return json.loads(child.stdout.readline())
            hello=rpc(1,'initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'test','version':'1'}})
            self.assertEqual(hello['result']['protocolVersion'],'2025-06-18')
            self.assertEqual({tool['name'] for tool in rpc(2,'tools/list')['result']['tools']},set(TOOLS))
            result=rpc(3,'tools/call',{'name':name,'arguments':args})['result']
            self.assertEqual(json.loads(result['content'][0]['text']),result['structuredContent'])
            return result
        finally:
            child.stdin.close();child.wait(timeout=5);child.stdout.close();child.stderr.close()

    def test_cli_mcp_same_error_and_path_isolation(self):
        (self.workspace/'escape.urdf').symlink_to('/etc/hosts')
        for name,args,code in [('import_source',{'source':'../outside.urdf'},'invalid_path'),
                               ('import_source',{'source':'escape.urdf'},'invalid_path'),
                               ('unknown',{},'unknown_tool')]:
            exit_code,cli=self.cli(name,args);mcp=self.mcp(name,args)
            self.assertEqual(exit_code,2);self.assertTrue(mcp['isError'])
            self.assertEqual(cli,mcp['structuredContent'])
            self.assertEqual(cli['error']['code'],code)
        with tempfile.TemporaryDirectory(prefix='a02-outside-') as outside:
            (self.workspace/'.urdftools').symlink_to(outside, target_is_directory=True)
            proposal={'schema_version':1,'action':'replace_recipe','expected_revision':0,
                      'recipe':RECIPE,'rationale':'Review geometry.'}
            exit_code,blocked=self.cli('preview_model_recipe',{'suggestion':proposal})
            self.assertEqual(exit_code,2)
            self.assertEqual(blocked['error']['code'],'invalid_path')
            self.assertEqual(list(Path(outside).iterdir()),[])

    def test_actual_import_conversion_preview_and_physics(self):
        shutil.copy2(ROOT/'tests/fixtures/S03/valid.zip',self.workspace/'import.zip')
        shutil.copy2(ROOT/'tests/fixtures/C00/two_part_mm.step',self.workspace/'two_part.step')
        code,imported=self.cli('import_source',{'source':'import.zip'})
        self.assertEqual(code,0);self.assertEqual(imported['data']['status'],'selection_required')
        self.assertGreaterEqual(len(imported['data']['models']),2)
        conversion=self.mcp('inspect_step_conversion',{'source':'two_part.step'})
        self.assertFalse(conversion['isError'])
        self.assertEqual(len(conversion['structuredContent']['data']['draft']['parts']),2)
        cli_code,cli_conversion=self.cli('inspect_step_conversion',{'source':'two_part.step'})
        self.assertEqual(cli_code,0)
        self.assertEqual(cli_conversion,conversion['structuredContent'])
        project=self.workspace/'.urdftools/modeling'
        first=apply_project(project,RECIPE,expected_revision=0)
        pointer=(project/'current.json').read_bytes()
        proposed=json.loads(json.dumps(RECIPE));proposed['parts'][1]['profile']['width_mm']=40
        suggestion={'schema_version':1,'action':'replace_recipe','expected_revision':1,'recipe':proposed,'rationale':'Widen Arm for review.'}
        code,preview=self.cli('preview_model_recipe',{'suggestion':suggestion})
        self.assertEqual(code,0);self.assertEqual(preview['data']['status'],'preview_only')
        self.assertEqual((project/'current.json').read_bytes(),pointer)
        self.assertGreater(preview['data']['report']['parts'][1]['mass_kg'],first['report']['parts'][1]['mass_kg'])
        step=self.workspace/'assembly.step';export_revision_assembly(first['package'],step)
        draft=inspect_conversion_draft(step);config=default_configuration(draft)
        config['joints'][0].update({'type':'revolute','axis':[0,0,1],'origin_m':[0.05,0,0],
            'limits':[-1,1],'effort':8,'velocity':3,'confirmed':True})
        write_package_zip(step,config,{'Base':2700,'Arm':7800},self.workspace/'robot.zip')
        validation=self.mcp('validate_urdf_package',{'source':'robot.zip'})
        self.assertFalse(validation['isError'])
        self.assertEqual(validation['structuredContent']['data']['status'],'passed')
        self.assertEqual(validation['structuredContent']['data']['link_count'],2)
        self.assertEqual(validation['structuredContent']['data']['joint_count'],1)

if __name__=='__main__':unittest.main()
