"""Real Electron Agent review, reject, accept and undo with ChatGPT CLI login."""
import json
import os
from pathlib import Path
import tempfile
from accept_phase import run_stage, ROOT


def main():
    output=ROOT/'artifacts/A01/desktop';output.mkdir(parents=True,exist_ok=True)
    codex_home=os.environ.get('CODEX_HOME',str(Path.home()/'.codex'))
    with tempfile.TemporaryDirectory(prefix='a01-desktop-',dir=ROOT/'.tools') as home:
        env={'PATH':str(ROOT/'.tools/node/bin')+':/usr/bin:/bin','HOME':home,'CODEX_HOME':codex_home,
             'LANG':'C.UTF-8','URDFTOOLS_MODEL_SMOKE':'1','URDFTOOLS_AGENT_SMOKE':'1',
             'URDFTOOLS_SMOKE_ARTIFACT_DIR':str(output),'URDFTOOLS_CAD_EXPORT_SMOKE':str(output/'robot.zip')}
        command=[str(ROOT/'apps/desktop/node_modules/electron/dist/electron'),str(ROOT/'apps/desktop'),
                 '--smoke','--ozone-platform=headless','--enable-unsafe-swiftshader',
                 '--use-gl=angle','--use-angle=swiftshader']
        code,log=run_stage(command,env=env,timeout=540)
    (output/'electron.log').write_text(log)
    events=[]
    for line in log.splitlines():
        try:events.append(json.loads(line))
        except ValueError:pass
    event=next((item for item in events if item.get('event')=='desktop_agent_smoke'),None)
    passed=code==0 and event is not None and event.get('accepted_revision')==2 and event.get('undo_revision')==3 and (output/'agent.png').is_file()
    (output/'report.json').write_text(json.dumps({'status':'passed' if passed else 'failed','exit_code':code,
        'command':command,'agent_event':event},ensure_ascii=False,indent=2)+'\n')
    print(log[-10000:])
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
