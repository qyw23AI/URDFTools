"""S03 real Electron native-file drop, IPC/Python import, and React selection."""
import json
from pathlib import Path
import tempfile
from accept_phase import run_stage, ROOT


def main():
    output = ROOT/'artifacts/S03/desktop'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='s03-desktop-', dir=ROOT/'.tools') as home:
        env = {'PATH': str(ROOT/'.tools/node/bin')+':/usr/bin:/bin', 'HOME':home,
               'LANG':'C.UTF-8', 'URDFTOOLS_SMOKE_ARTIFACT_DIR':str(output),
               'URDFTOOLS_IMPORT_SMOKE':str(ROOT/'tests/fixtures/S03/中文机器人')}
        build = [str(ROOT/'.tools/node/bin/node'), str(ROOT/'.tools/npm/bin/npm-cli.js'), 'run','build']
        code, log = run_stage(build, env=env, timeout=60)
        (output/'build.log').write_text(log)
        if code:
            print(log)
            return 1
        command = [str(ROOT/'apps/desktop/node_modules/electron/dist/electron'), str(ROOT/'apps/desktop'), '--smoke', '--ozone-platform=headless','--disable-gpu']
        code, log = run_stage(command, env=env, timeout=60)
        # Keep actual copied inputs/reports after the isolated profile is removed.
        imports = list(Path(home).rglob('report.json'))
        reports = []
        for path in imports:
            try:
                report = json.loads(path.read_text())
                if 'selected_model' in report:
                    import shutil
                    shutil.copytree(path.parent, output/report['operation_id'])
                    reports.append(report)
            except (ValueError, OSError):
                continue
    (output/'electron.log').write_text(log)
    print(log)
    events=[]
    for line in log.splitlines():
        try: events.append(json.loads(line))
        except ValueError: pass
    event=next((e for e in events if e.get('event')=='desktop_import_smoke'), {})
    passed=code==0 and event.get('nativeDrag') is True and event.get('missingLocated') is True and bool(reports)
    (output/'report.json').write_text(json.dumps(dict(status='passed' if passed else 'failed',command=command,exit_code=code,event=event,imports=reports),ensure_ascii=False,indent=2)+'\n')
    return 0 if passed else 1


if __name__=='__main__':
    raise SystemExit(main())
