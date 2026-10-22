#!/usr/bin/env python3
"""Fail closed until local, live CLI and actual timer acceptance all pass."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scheduler


def evaluate(root):
    reports = [root / 'artifacts/S00/unit-report.json', root / 'artifacts/S00/live-smoke/report.json',
               root / 'artifacts/S00/timer/report.json']
    checks = []
    for path in reports:
        report = scheduler.read_json(path, {})
        passed = report.get('status') == 'passed'
        if path.name == 'unit-report.json':
            passed = passed and report.get('tests_run', 0) >= 40 and report.get('failures') == 0 and report.get('errors') == 0
            passed = passed and report.get('source_sha256') == scheduler.file_hash(root / 'scheduler.py')
            passed = passed and report.get('tests_sha256') == scheduler.file_hash(root / 'tests/test_scheduler.py')
            passed = passed and report.get('fixture_sha256') == scheduler.file_hash(root / 'tests/fixtures/scheduler/codex_fault.py')
            passed = passed and report.get('evidence_sha256') == scheduler.file_hash(root / 'artifacts/S00/fault-evidence.tar.gz')
            passed = passed and report.get('skipped') == 0
        elif path.parent.name == 'live-smoke':
            passed = passed and report.get('kind') == 'real_codex_cli' and all(
                report.get('checks', {}).get(key) is True for key in ('numeric_gate', 'commit', 'repeat_no_duplicate'))
            passed = passed and report.get('source_sha256') == scheduler.file_hash(root / 'scheduler.py')
        else:
            trigger = report.get('actual_trigger')
            passed = passed and isinstance(trigger, dict) and isinstance(trigger.get('token'), str) and bool(trigger['token'])
            passed = passed and type((trigger or {}).get('elapsed_seconds')) in (int, float)
            passed = passed and 1 <= trigger['elapsed_seconds'] < 60
            passed = passed and report.get('source_sha256') == scheduler.file_hash(root / 'systemd/urdftools-dev.service')
            passed = passed and report.get('timer_sha256') == scheduler.file_hash(root / 'systemd/urdftools-dev.timer')
            passed = passed and report.get('verifier_sha256') == scheduler.file_hash(root / 'scripts/verify_scheduler_timer.py')
            passed = passed and report.get('deployment_matches') is True and report.get('timer_active') is True
        checks.append({'report': str(path.relative_to(root)), 'passed': bool(passed), 'reported_status': report.get('status', 'missing')})
    return checks


def main():
    checks = evaluate(ROOT)
    passed = sum(item['passed'] for item in checks)
    print(json.dumps({'checks': checks, 'scheduler_gate': {
        'executed': len(checks), 'passed': passed, 'failed': len(checks) - passed, 'skipped': 0}}))
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    raise SystemExit(main())
