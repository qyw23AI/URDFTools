"""Exercise a real STEP pair's shared-axis candidate in the Electron canvas."""
import json
import tempfile
from pathlib import Path
from accept_phase import run_stage, ROOT


def main() -> int:
    source = Path('/home/qyw/Quadruped-Robot-12DOF/cad/step/Quadruped Robot.STEP')
    if not source.is_file():
        print(json.dumps({'status': 'unavailable', 'reason': 'user STEP file missing'}))
        return 2
    output = ROOT / 'artifacts/C03/desktop'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cad-axis-', dir=ROOT / '.tools') as home:
        env = {'PATH': str(ROOT / '.tools/node/bin') + ':/usr/bin:/bin', 'HOME': home,
               'LANG': 'C.UTF-8', 'URDFTOOLS_SMOKE_ARTIFACT_DIR': str(output),
               'URDFTOOLS_CAD_AXIS_SMOKE': str(source)}
        command = [str(ROOT / 'apps/desktop/node_modules/electron/dist/electron'),
                   str(ROOT / 'apps/desktop'), '--smoke', '--ozone-platform=headless',
                   '--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader']
        code, log = run_stage(command, env=env, timeout=180)
    (output / 'real-axis-electron.log').write_text(log)
    events = []
    for line in log.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    event = next((item for item in events if item.get('event') == 'desktop_cad_real_axis_smoke'), None)
    passed = code == 0 and event is not None and event.get('candidateCount', 0) >= 1 and event.get('selected')
    (output / 'real-axis-report.json').write_text(json.dumps({'status': 'passed' if passed else 'failed',
        'exit_code': code, 'event': event}, ensure_ascii=False, indent=2) + '\n')
    print(log[-8000:])
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
