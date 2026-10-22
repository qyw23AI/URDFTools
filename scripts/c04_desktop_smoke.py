"""Real FCStd creation -> FreeCADCmd -> Electron conversion UI smoke."""
import json
from pathlib import Path
import tempfile
from accept_phase import run_stage, ROOT


def main():
    output=ROOT/'artifacts/C04/desktop'
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='c04-desktop-',dir=ROOT/'.tools') as directory:
        root=Path(directory)
        fixture=root/'bracket.FCStd'
        code, created=run_stage([str(ROOT/'.tools/cad-venv/bin/python'),str(ROOT/'scripts/freecad_bridge.py'),
                                '--make-fixture','--output',str(fixture)],timeout=60)
        if code:
            print(created)
            return 2
        env={'PATH':str(ROOT/'.tools/node/bin')+':/usr/bin:/bin','HOME':str(root),
             'LANG':'C.UTF-8','URDFTOOLS_SMOKE_ARTIFACT_DIR':str(output),
             'URDFTOOLS_CAD_EXCHANGE_SMOKE':str(fixture)}
        command=[str(ROOT/'apps/desktop/node_modules/electron/dist/electron'),str(ROOT/'apps/desktop'),
                 '--smoke','--ozone-platform=headless','--enable-unsafe-swiftshader',
                 '--use-gl=angle','--use-angle=swiftshader']
        code,log=run_stage(command,env=env,timeout=180)
    (output/'electron.log').write_text(log)
    events=[]
    for line in log.splitlines():
        try:events.append(json.loads(line))
        except ValueError:pass
    event=next((item for item in events if item.get('event')=='desktop_freecad_exchange_smoke'),None)
    passed=code==0 and event is not None and event.get('partCount')==2 and event.get('lossVisible') and (output/'freecad-exchange.png').is_file()
    (output/'report.json').write_text(json.dumps({'status':'passed' if passed else 'failed',
        'exit_code':code,'event':event},ensure_ascii=False,indent=2)+'\n')
    print(log[-5000:])
    return 0 if passed else 1

if __name__=='__main__':
    raise SystemExit(main())
