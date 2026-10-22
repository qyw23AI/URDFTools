"""S04 genuine offline Electron+Three.js/URDFLoader mesh and joint E2E."""
import json
import os
from pathlib import Path
import tempfile
from accept_phase import run_stage, ROOT


def main():
    output = ROOT / 'artifacts/S04/desktop'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='s04-desktop-', dir=ROOT/'.tools') as home:
        env = {
            'PATH': str(ROOT/'.tools/node/bin')+':/usr/bin:/bin',
            'HOME': home, 'LANG': 'C.UTF-8',
            'URDFTOOLS_SMOKE_ARTIFACT_DIR': str(output),
            'URDFTOOLS_VIEWER_SMOKE': str(ROOT/'tests/fixtures/S04/simple_robot'),
        }
        build = [str(ROOT/'.tools/node/bin/node'), str(ROOT/'.tools/npm/bin/npm-cli.js'), 'run', 'build']
        code, log = run_stage(build, env=env, timeout=90)
        (output/'build.log').write_text(log)
        if code:
            print(log)
            return 1
        command = [str(ROOT/'apps/desktop/node_modules/electron/dist/electron'),
                   str(ROOT/'apps/desktop'), '--smoke', '--ozone-platform=headless',
                   '--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader']
        code, log = run_stage(command, env=env, timeout=90)
    (output/'electron.log').write_text(log)
    events = []
    for line in log.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    event = next((x for x in events if x.get('event') == 'desktop_viewer_smoke'), None)
    passed = (code == 0 and event is not None and event.get('meshCount', 0) >= 2
              and event.get('joint') == 'shoulder'
              and abs(event.get('value', 0) - 1.2) < 0.011
              and (output/'viewer.png').exists())
    (output/'report.json').write_text(json.dumps({
        'status': 'passed' if passed else 'failed', 'exit_code': code,
        'command': command, 'viewer_event': event}, ensure_ascii=False, indent=2)+'\n')
    print(log[-8000:])
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
