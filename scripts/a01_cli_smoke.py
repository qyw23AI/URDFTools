#!/usr/bin/env python3
"""Real ChatGPT login: two-part suggestion, reject/accept, URDF validation and undo."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from urdftools.modeling.core import apply_project
from urdftools.modeling.assembly import export_revision_assembly
from urdftools.cad.wizard import inspect_conversion_draft, default_configuration
from urdftools.cad.exporter import write_package_zip

recipe={'schema_version':1,'parts':[
    {'name':'Base','material':'user declared','density_kg_m3':2700,
     'profile':{'kind':'rectangle','width_mm':20,'height_mm':10},
     'operation':{'kind':'extrude','distance_mm':5},'placement_mm':[0,0,0]},
    {'name':'Arm','material':'user declared','density_kg_m3':7800,
     'profile':{'kind':'rectangle','width_mm':30,'height_mm':4},
     'operation':{'kind':'extrude','distance_mm':4},'placement_mm':[50,0,0]}]}

def invoke(action,project,request):
    with tempfile.TemporaryDirectory(prefix='a01-request-') as tmp:
        request_path=Path(tmp)/'request.json'
        request_path.write_text(json.dumps(request))
        result=subprocess.run([str(ROOT/'.tools/model-venv/bin/python'),str(ROOT/'scripts/a01_agent_model.py'),
            action,'--project',str(project),'--request',str(request_path)],capture_output=True,text=True,timeout=210)
        if result.returncode: raise RuntimeError(result.stderr[-3000:])
        return json.loads(result.stdout.strip().splitlines()[-1])

with tempfile.TemporaryDirectory(prefix='a01-cli-') as tmp:
    root=Path(tmp);project=root/'project'
    first=apply_project(project,recipe,expected_revision=0)
    pointer=(project/'current.json').read_bytes()
    instruction='In the two-part Base and Arm recipe, increase only Arm profile width_mm from 30 to 40. Keep Base and all other values unchanged.'
    rejected=invoke('suggest',project,{'expected_revision':1,'instruction':instruction})
    assert rejected['status']=='preview_only' and rejected['recipe']['parts'][1]['profile']['width_mm']==40
    assert (project/'current.json').read_bytes()==pointer
    accepted_proposal=invoke('suggest',project,{'expected_revision':1,'instruction':instruction})
    assert (project/'current.json').read_bytes()==pointer
    second=invoke('apply',project,{'proposal_id':accepted_proposal['proposal_id'],'human_confirmed':True})
    assert second['revision']==2 and second['report']['parts'][1]['mass_kg']>first['report']['parts'][1]['mass_kg']
    step=root/'model.step';export_revision_assembly(second['package'],step)
    draft=inspect_conversion_draft(step)
    config=default_configuration(draft)
    assert len(config['joints'])==1
    config['joints'][0].update({'type':'revolute','axis':[0,0,1],'origin_m':[0.05,0,0],
        'limits':[-1,1],'effort':8,'velocity':3,'confirmed':True})
    package=write_package_zip(step,config,{'Base':2700,'Arm':7800},root/'robot.zip')
    validated=subprocess.run([str(ROOT/'.tools/sim-venv/bin/python'),str(ROOT/'scripts/validate_cad_package.py'),package['path']],capture_output=True,text=True,check=True)
    validation=json.loads(validated.stdout)
    assert validation['status']=='passed' and validation['link_count']==2 and validation['joint_count']==1
    third=apply_project(project,recipe,expected_revision=2)
    assert third['revision']==3
    assert abs(third['report']['parts'][1]['volume_mm3']-first['report']['parts'][1]['volume_mm3'])<1e-9
    assert abs(third['report']['parts'][1]['mass_kg']-first['report']['parts'][1]['mass_kg'])<1e-12
    print(json.dumps({'status':'passed','provider':'ChatGPT Codex CLI','rejected_without_mutation':True,
        'accepted_revision':2,'undo_revision':3,'link_count':2,'joint_count':1,
        'arm_mass_before':first['report']['parts'][1]['mass_kg'],
        'arm_mass_after':second['report']['parts'][1]['mass_kg']}))
