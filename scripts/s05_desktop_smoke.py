"""S05 real Electron/Three.js E2E for structure, visibility, physics evidence and measurement."""
import json
import os
from pathlib import Path
import tempfile
from accept_phase import run_stage, ROOT


def main():
    output = ROOT / 'artifacts/S05/desktop'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='s05-desktop-', dir=ROOT/'.tools') as home:
        env = {
            'PATH': str(ROOT/'.tools/node/bin') + ':/usr/bin:/bin',
            'HOME': home, 'LANG': 'C.UTF-8',
            'URDFTOOLS_SMOKE_ARTIFACT_DIR': str(output),
            'URDFTOOLS_VIEWER_SMOKE': str(ROOT/'tests/fixtures/S05/simple_robot'),
            'URDFTOOLS_VIEWER_S05_SMOKE': '1',
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
        code, log = run_stage(command, env=env, timeout=100)
    (output/'electron.log').write_text(log)
    events = []
    for line in log.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    event = next((item for item in events if item.get('event') == 'desktop_viewer_s05_smoke'), None)
    passed = (
        code == 0 and event is not None
        and event.get('linkCount') == 2 and event.get('jointCount') == 1
        and event.get('visualCount') == 2 and event.get('visibleVisualCount') == 2
        and event.get('collisionCount') == 1 and event.get('collisionStyledMeshCount') == 1
        and event.get('visibleCollisionCount') == 1
        and event.get('visualVisible') is True and event.get('collisionVisible') is True
        and event.get('visualChecked') is True and event.get('collisionChecked') is True
        and event.get('isolationRestored') is True and event.get('comMarkerVerified') is True
        and event.get('viewResetCount') == 1 and event.get('screenshotReady') is True
        and event.get('screenshotExportBytes', 0) > 1000
        and (output/'viewer-export.png').exists()
        and event.get('massKnownCount') == 1 and event.get('massUnknownCount') == 1
        and event.get('massComplete') is False
        and abs(event.get('totalKnownMass', 0) - 1.25) < 0.001
        and event.get('physicsUnchanged') is True
        and event.get('joint') == 'shoulder'
        and abs(event.get('jointValue', 0) - 1.2) < 0.011
        and event.get('bounds') and len(event['bounds']) == 3
        and all(value > 0 for value in event['bounds'])
        and event.get('selectedDimensions') and len(event['selectedDimensions']) == 3
        and (output/'viewer-analysis.png').exists()
    )
    (output/'report.json').write_text(json.dumps({
        'status': 'passed' if passed else 'failed', 'exit_code': code,
        'command': command, 'viewer_event': event}, ensure_ascii=False, indent=2) + '\n')
    print(log[-10000:])
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
