"""S06 runs the actual Electron viewer on Go2 folder and G1 ZIP imports."""
import json
import os
from pathlib import Path
import tempfile
import zipfile
from accept_phase import run_stage, ROOT


def load_event(log, event_name):
    for line in log.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get('event') == event_name:
            return record
    return None


def main():
    output = ROOT / 'artifacts/S06/desktop'
    output.mkdir(parents=True, exist_ok=True)
    zip_dir = ROOT / 'artifacts/S06/input-zips'
    zip_dir.mkdir(parents=True, exist_ok=True)
    g1_dir = ROOT / 'tests/fixtures/S06/reference_models/g1_description'
    g1_zip = zip_dir / 'g1_description.zip'
    with zipfile.ZipFile(g1_zip, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
        for file in sorted(g1_dir.rglob('*')):
            if file.is_file():
                zipped.write(file, (Path('g1_description') / file.relative_to(g1_dir)).as_posix())

    base_env = {
        'PATH': str(ROOT/'.tools/node/bin') + ':/usr/bin:/bin',
        'LANG': 'C.UTF-8',
    }
    build = [str(ROOT/'.tools/node/bin/node'), str(ROOT/'.tools/npm/bin/npm-cli.js'), 'run', 'build']
    code, log = run_stage(build, env=base_env, timeout=120)
    (output/'build.log').write_text(log)
    if code:
        print(log)
        return 1

    cases = [
        ('go2', ROOT/'tests/fixtures/S06/reference_models/go2_description'),
        ('g1', g1_zip),
    ]
    expected = {'go2': (42, 41), 'g1': (40, 39)}
    failures = []
    for label, fixture in cases:
        case_env = dict(base_env)
        with tempfile.TemporaryDirectory(prefix='s06-'+label+'-', dir=ROOT/'.tools') as home:
            case_env.update({
                'HOME': home,
                'URDFTOOLS_SMOKE_ARTIFACT_DIR': str(output),
                'URDFTOOLS_VIEWER_SMOKE': str(fixture),
                'URDFTOOLS_VIEWER_S06_SMOKE': label,
            })
            command = [str(ROOT/'apps/desktop/node_modules/electron/dist/electron'),
                       str(ROOT/'apps/desktop'), '--smoke', '--ozone-platform=headless',
                       '--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader']
            try:
                code, log = run_stage(command, env=case_env, timeout=140)
            except Exception as exc:
                code, log = 1, repr(exc)
        (output/(label+'-electron.log')).write_text(log)
        event = load_event(log, 'desktop_viewer_s06_smoke')
        links, joints = expected[label]
        passed = (
            code == 0 and event is not None
            and event.get('model') == label and event.get('assetsLoaded') is True
            and event.get('linkCount') == links and event.get('jointCount') == joints
            and event.get('meshCount', 0) >= 5 and event.get('visualCount', 0) >= 5
            and event.get('collisionCount', 0) > 0 and event.get('collisionStyledMeshCount', 0) > 0
            and event.get('visibleCollisionCount', 0) > 0 and event.get('massKnownCount', 0) > 0
            and event.get('jointPoseChanged') is True and event.get('collisionToggleVerified') is True
            and event.get('visualToggleVerified') is True and event.get('physicsUnchanged') is True
            and event.get('screenshotReady') is True and event.get('screenshotExportBytes', 0) > 1000
            and event.get('viewResetCount') == 1 and not event.get('alerts')
            and (output/(label+'-viewer-export.png')).is_file()
            and (output/(label+'-viewer.png')).is_file()
        )
        record = {'status':'passed' if passed else 'failed','exit_code':code,'model':label,
                  'input':str(fixture),'viewer_event':event}
        (output/(label+'-report.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(record,ensure_ascii=False))
        if not passed:
            failures.append(label)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
