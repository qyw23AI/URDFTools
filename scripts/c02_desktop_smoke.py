"""C02 real Electron STEP inspection, human-confirmed joint and 3D preview smoke."""
import json
from pathlib import Path
import tempfile
from accept_phase import run_stage, ROOT


def main():
    output = ROOT / 'artifacts/C02/desktop'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='c02-desktop-', dir=ROOT/'.tools') as home:
        env = {'PATH': str(ROOT/'.tools/node/bin')+':/usr/bin:/bin', 'HOME': home,
               'LANG': 'C.UTF-8', 'URDFTOOLS_SMOKE_ARTIFACT_DIR': str(output),
               'URDFTOOLS_CAD_WIZARD_SMOKE': str(ROOT/'tests/fixtures/C00/two_part_mm.step')}
        command = [str(ROOT/'apps/desktop/node_modules/electron/dist/electron'),
                   str(ROOT/'apps/desktop'), '--smoke', '--ozone-platform=headless',
                   '--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader']
        code, log = run_stage(command, env=env, timeout=120)
    (output/'electron.log').write_text(log)
    events = []
    for line in log.splitlines():
        try: events.append(json.loads(line))
        except ValueError: pass
    event = next((item for item in events if item.get('event') == 'desktop_cad_wizard_smoke'), None)
    passed = code == 0 and event is not None and event.get('linkCount') == 2 and event.get('jointCount') == 1 and (output/'cad-wizard.png').is_file()
    (output/'report.json').write_text(json.dumps({'status': 'passed' if passed else 'failed',
        'exit_code': code, 'command': command, 'viewer_event': event}, ensure_ascii=False, indent=2)+'\n')
    print(log[-7000:])
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
