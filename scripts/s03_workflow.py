"""Real subprocess CLI/desktop bridge workflow with retained bytes and reports."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT/'tests/fixtures/S03'


def main():
    output = ROOT/'artifacts/S03/workflows'/str(uuid4())
    output.mkdir(parents=True)
    storage = output/'imports'
    env = {'PATH':os.environ.get('PATH','/usr/bin:/bin'), 'PYTHONPATH':str(ROOT/'python')}
    records=[]
    for source, model, expected, expected_exit in [
        ('valid.zip','示例包/urdf/01好模型.urdf','ready',0),
        ('中文机器人','示例包/urdf/02缺失.urdf','failed',1),
        ('traversal.zip',None,'failed',1),
        ('corrupt.zip',None,'failed',1)]:
        command=[sys.executable,'-m','urdftools','import',str(FIXTURES/source),'--storage',str(storage),'--json']
        if model: command += ['--model', model]
        result=subprocess.run(command,cwd=ROOT,env=env,text=True,capture_output=True,timeout=20)
        records.append(dict(command=command,exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr))
        (output/'commands.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
        assert result.returncode==expected_exit, records[-1]
        report=json.loads(result.stdout)
        assert report['status']==expected
        if expected=='ready':
            resources=report['models'][0]['resources']
            assert [r['inspection']['faces'] for r in resources]==[1,1]
            for asset in report['assets']:
                data=(storage/report['operation_id']/'bundle'/asset['path']).read_bytes()
                assert hashlib.sha256(data).hexdigest()==asset['sha256']
    # The same entry point used by the Electron main process accepts JSON over stdin.
    command=[sys.executable,'-m','urdftools.importers',str(storage)]
    worker=subprocess.run(command,input=json.dumps(dict(action='import',source=str(FIXTURES/'valid.zip'))),cwd=ROOT,env=env,text=True,capture_output=True,timeout=20)
    records.append(dict(command=command,exit_code=worker.returncode,stdout=worker.stdout,stderr=worker.stderr))
    report=json.loads(worker.stdout)
    assert worker.returncode==0 and report['status']=='selection_required'
    worker=subprocess.run(command,input=json.dumps(dict(action='select',operation_id=report['operation_id'],model=report['models'][0]['path'])),cwd=ROOT,env=env,text=True,capture_output=True,timeout=20)
    records.append(dict(command=command,exit_code=worker.returncode,stdout=worker.stdout,stderr=worker.stderr))
    assert worker.returncode==0 and json.loads(worker.stdout)['status']=='ready'
    (output/'commands.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
    (output/'report.json').write_text(json.dumps(dict(status='passed',processes=len(records),cli_cases=4,bridge_steps=2),indent=2)+'\n')
    print(f'4 CLI cases and 2 real desktop bridge subprocess steps passed; evidence: {output.relative_to(ROOT)}')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
