#!/usr/bin/env python3
"""Actually trigger a short user timer; never starts a model or edits scheduler state."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
import scheduler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=SOURCE / 'artifacts/S00/timer')
    parser.add_argument('--probe', nargs=3, metavar=('MARKER', 'START', 'TOKEN'))
    args = parser.parse_args()
    if args.probe:
        marker, start, token = args.probe
        elapsed = time.monotonic() - float(start)
        scheduler.atomic_json(Path(marker), dict(token=token, elapsed_seconds=elapsed, timestamp=scheduler.now()))
        return 0 if 1 <= elapsed < 60 else 1
    args.output.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    marker = args.output.resolve() / ('trigger-' + token + '.json')
    unit = 'urdftools-s00-probe-' + token[:12]
    start = time.monotonic()
    command = ['systemd-run', '--user', '--unit=' + unit, '--on-active=2s', '--timer-property=AccuracySec=100ms',
               '--collect', sys.executable, str(Path(__file__).resolve()), '--probe', str(marker), str(start), token]
    process = scheduler.run_process(command, SOURCE, 10, args.output / 'systemd-run.stdout')
    fired = None
    if process['exit_code'] == 0:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            fired = scheduler.read_json(marker)
            if fired:
                break
            time.sleep(.1)
    passed = bool(fired and fired.get('token') == token and 1 <= fired.get('elapsed_seconds', 0) < 60)
    report = dict(status='passed' if passed else 'blocked', timestamp=scheduler.now(),
                  command=command, process=process, actual_trigger=fired,
                  source_sha256=scheduler.file_hash(SOURCE / 'systemd/urdftools-dev.service'),
                  calendar='*-*-* 00/6:00:00', permanent_timer_modified=False)
    scheduler.atomic_json(args.output / 'report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
