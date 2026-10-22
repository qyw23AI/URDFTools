#!/usr/bin/env python3
"""Run declared fault suite, preserve per-case inputs/evidence and numerical counts."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scheduler

output = ROOT / 'artifacts/S00'
output.mkdir(parents=True, exist_ok=True)
command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_scheduler*.py', '-v']
with tempfile.TemporaryDirectory(prefix='urdftools-fault-evidence-') as tmp:
    env = os.environ | {'S00_EVIDENCE_DIR': tmp}
    completed = subprocess.run(command, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (output / 'unit-tests.log').write_text(completed.stdout)
    with tarfile.open(output / 'fault-evidence.tar.gz', 'w:gz') as archive:
        archive.add(tmp, arcname='fault-evidence')
counts = scheduler.gate_counts(completed.stdout)
report = dict(timestamp=scheduler.now(), command=command, exit_code=completed.returncode,
              status='passed' if completed.returncode == 0 and counts and counts['passed'] > 0 and counts['failed'] == 0 else 'failed',
              tests_run=counts['executed'] if counts else 0, failures=counts['failed'] if counts else None,
              errors=0 if completed.returncode == 0 else None, skipped=counts['skipped'] if counts else None,
              source_sha256=scheduler.file_hash(ROOT / 'scheduler.py'),
              tests_sha256=scheduler.file_hash(ROOT / 'tests/test_scheduler.py'),
              fixture_sha256=scheduler.file_hash(ROOT / 'tests/fixtures/scheduler/codex_fault.py'),
              evidence_sha256=scheduler.file_hash(output / 'fault-evidence.tar.gz'))
scheduler.atomic_json(output / 'unit-report.json', report)
print(json.dumps(report, indent=2))
raise SystemExit(completed.returncode or (0 if report['status'] == 'passed' else 1))
