"""Verify the installed runtime and render the real shell in isolated headless Chromium."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from accept_phase import run_stage
from bootstrap import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts-dir', type=Path, default=ROOT / 'artifacts/S01/desktop')
    args = parser.parse_args()
    output = args.artifacts_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    runtime = ROOT / 'apps/desktop/node_modules/electron/dist'
    try:
        hashes = json.loads((ROOT / 'third_party/electron-runtime-files.json').read_text())
        for name, expected in hashes.items():
            if hashlib.sha256((runtime / name).read_bytes()).hexdigest() != expected:
                raise ValueError('Installed Electron file differs from reviewed archive: ' + name)
    except (OSError, ValueError) as exc:
        print(json.dumps({'status': 'blocked_input', 'message': str(exc),
                          'dependency': 'electron@39.2.7; run bootstrap with --electron-cache'}))
        return 2
    with tempfile.TemporaryDirectory(prefix='electron-smoke-', dir=ROOT / '.tools') as home:
        env = {'PATH': str(ROOT / '.tools/node/bin') + ':/usr/bin:/bin', 'HOME': home,
               'LANG': 'C.UTF-8', 'URDFTOOLS_SMOKE_ARTIFACT_DIR': str(output)}
        build_code, build_log = run_stage([str(ROOT / '.tools/node/bin/node'),
            str(ROOT / '.tools/npm/bin/npm-cli.js'), 'run', 'build'], timeout=60, env=env)
        (output / 'build.log').write_text(build_log)
        if build_code:
            print(build_log)
            return 1
        command = [str(runtime / 'electron'), str(ROOT / 'apps/desktop'), '--smoke',
                   '--ozone-platform=headless', '--disable-gpu']
        code, log = run_stage(command, timeout=40, env=env)
    (output / 'electron.log').write_text(log)
    print(log, end='')
    events = []
    for line in log.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    event = next((e for e in events if e.get('event') == 'desktop_smoke'), {})
    passed = code == 0 and event.get('rendered') is True and event.get('isolated') is True and event.get('sandbox') is True
    capture = output / 'desktop.png'
    if not capture.is_file() or capture.stat().st_size < 1000:
        passed = False
    report = {'status': 'passed' if passed else 'failed', 'command': command,
              'exit_code': code, 'mode': 'isolated headless Chromium; software rendering; no user display',
              'runtime_files_verified': len(hashes), 'render': event,
              'capture_sha256': hashlib.sha256(capture.read_bytes()).hexdigest() if capture.exists() else None}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
