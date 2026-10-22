"""Real Electron model -> FreeCAD return review -> accept -> topology conflict."""
import json
from pathlib import Path
import tempfile
from accept_phase import run_stage,ROOT

def main():
    output=ROOT/'artifacts/M02/desktop';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='m02-desktop-',dir=ROOT/'.tools') as folder:
        root=Path(folder)
        sources={}
        for variant in ('model_same','model_topology'):
            source=root/f'{variant}.FCStd'
            code,log=run_stage([str(ROOT/'.tools/cad-venv/bin/python'),str(ROOT/'scripts/freecad_bridge.py'),
              '--make-fixture','--fixture-variant',variant,'--output',str(source)],timeout=90)
            if code:
                print(log);return 2
            sources[variant]=source
        env={'PATH':str(ROOT/'.tools/node/bin')+':/usr/bin:/bin','HOME':str(root),
          'LANG':'C.UTF-8','URDFTOOLS_MODEL_SMOKE':'1','URDFTOOLS_SMOKE_ARTIFACT_DIR':str(output),
          'URDFTOOLS_CAD_EXPORT_SMOKE':str(output/'robot.zip'),
          'URDFTOOLS_MODEL_RETURN_SMOKE':str(sources['model_same']),
          'URDFTOOLS_MODEL_TOPOLOGY_SMOKE':str(sources['model_topology'])}
        command=[str(ROOT/'apps/desktop/node_modules/electron/dist/electron'),str(ROOT/'apps/desktop'),
          '--smoke','--ozone-platform=headless','--enable-unsafe-swiftshader',
          '--use-gl=angle','--use-angle=swiftshader']
        code,log=run_stage(command,env=env,timeout=240)
        restore_env=dict(env)
        restore_env.pop('URDFTOOLS_MODEL_SMOKE',None)
        restore_env.pop('URDFTOOLS_MODEL_RETURN_SMOKE',None)
        restore_env.pop('URDFTOOLS_MODEL_TOPOLOGY_SMOKE',None)
        restore_env['URDFTOOLS_MODEL_RESTORE_SMOKE']='1'
        restore_code,restore_log=run_stage(command,env=restore_env,timeout=60) if code==0 else (1,'first run failed')
    (output/'electron.log').write_text(log)
    (output/'restore.log').write_text(restore_log)
    events=[]
    for line in log.splitlines():
        try:events.append(json.loads(line))
        except ValueError:pass
    restore_events=[]
    for line in restore_log.splitlines():
        try:restore_events.append(json.loads(line))
        except ValueError:pass
    result=next((event for event in events if event.get('event')=='desktop_model_return_smoke'),None)
    restored=any(event.get('event')=='desktop_model_restore_smoke' and event.get('restored') for event in restore_events)
    passed=code==0 and restore_code==0 and restored and result is not None and all(result.get(key) for key in
      ('samePartRelink','acceptedWithJointReconfirmation','topologyConflictBlocked')) and (output/'freecad-return.png').is_file()
    (output/'report.json').write_text(json.dumps({'status':'passed' if passed else 'failed',
      'exit_code':code,'restore_exit_code':restore_code,'restored':restored,'event':result},ensure_ascii=False,indent=2)+'\n')
    print(log[-7000:]);print(restore_log[-2500:])
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
