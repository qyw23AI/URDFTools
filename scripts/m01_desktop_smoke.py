"""Real Electron empty-project model/edit/undo/redo/URDF export smoke."""
import json
import tempfile
from accept_phase import run_stage, ROOT

def main():
    output=ROOT/'artifacts/M01/desktop'
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='m01-desktop-',dir=ROOT/'.tools') as home:
        env={'PATH':str(ROOT/'.tools/node/bin')+':/usr/bin:/bin','HOME':home,'LANG':'C.UTF-8',
             'URDFTOOLS_MODEL_SMOKE':'1','URDFTOOLS_SMOKE_ARTIFACT_DIR':str(output),
             'URDFTOOLS_CAD_EXPORT_SMOKE':str(output/'robot.zip')}
        command=[str(ROOT/'apps/desktop/node_modules/electron/dist/electron'),str(ROOT/'apps/desktop'),
                 '--smoke','--ozone-platform=headless','--enable-unsafe-swiftshader',
                 '--use-gl=angle','--use-angle=swiftshader']
        code,log=run_stage(command,env=env,timeout=240)
    (output/'electron.log').write_text(log)
    events=[]
    for line in log.splitlines():
        try: events.append(json.loads(line))
        except ValueError: pass
    event=next((item for item in events if item.get('event')=='desktop_model_smoke'),None)
    passed=code==0 and event is not None and event.get('gizmos')==1 and event.get('zipBytes',0)>1000 and (output/'model.png').is_file()
    (output/'report.json').write_text(json.dumps({'status':'passed' if passed else 'failed',
        'exit_code':code,'command':command,'model_event':event},ensure_ascii=False,indent=2)+'\n')
    print(log[-10000:])
    return 0 if passed else 1

if __name__=='__main__': raise SystemExit(main())
