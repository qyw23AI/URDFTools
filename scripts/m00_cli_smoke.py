"""Real CLI project revision, changed geometry and rollback smoke."""
import json
from pathlib import Path
import subprocess
import tempfile
from accept_phase import ROOT


def run(recipe,project,revision):
    return subprocess.run([str(ROOT/'.tools/model-venv/bin/python'),str(ROOT/'scripts/model_project.py'),
                           str(recipe),'--project',str(project),'--expected-revision',str(revision)],
                          capture_output=True,text=True,timeout=60,env={'PATH':'/usr/bin:/bin','PYTHONPATH':'','HOME':'/tmp'})


def main():
    fixture=ROOT/'tests/fixtures/M00/two_part_recipe.json'
    with tempfile.TemporaryDirectory(prefix='m00-cli-') as folder:
        root=Path(folder)
        project=root/'project'
        first=run(fixture,project,0)
        if first.returncode: raise AssertionError(first.stderr)
        old=json.loads(first.stdout)
        changed=json.loads(fixture.read_text())
        changed['parts'][1]['profile']['width_mm']=45
        edited=root/'changed.json';edited.write_text(json.dumps(changed))
        second=run(edited,project,1)
        if second.returncode: raise AssertionError(second.stderr)
        new=json.loads(second.stdout)
        if new['report']['parts'][1]['mass_kg']<=old['report']['parts'][1]['mass_kg']*1.4:
            raise AssertionError('Parameter edit did not recompute mass')
        pointer=(project/'current.json').read_bytes()
        changed['parts'][0]['profile']['holes'][0]['radius_mm']=10
        bad=root/'bad.json';bad.write_text(json.dumps(changed))
        failure=run(bad,project,2)
        if failure.returncode!=2 or (project/'current.json').read_bytes()!=pointer:
            raise AssertionError('Bad sketch modified committed project revision')
        print(json.dumps({'status':'passed','first_revision':old['revision'],'current_revision':new['revision'],
                          'mass_before_kg':old['report']['parts'][1]['mass_kg'],
                          'mass_after_kg':new['report']['parts'][1]['mass_kg'],
                          'bad_sketch_exit':failure.returncode}))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
