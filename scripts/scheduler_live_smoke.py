#!/usr/bin/env python3
"""Explicit live acceptance: one bounded CLI task in a disposable Git repository.

Never targets the product state/Git. No fake peer and no provider/API-key fallback.
Exit 1 means real acceptance remains blocked/failed, even if the failure was safe.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
import scheduler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-bin', default='/usr/lib/chatgpt/resources/codex')
    parser.add_argument('--output', type=Path, default=SOURCE / 'artifacts/S00/live-smoke')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    # Kept on failure for inspection; no credentials are ever copied here.
    # This CLI build refuses sandbox helpers beneath /tmp. Keep the disposable
    # repository inside the writable project, isolated from product Git/state.
    repositories = SOURCE / '.scheduler/live-repositories'
    repositories.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='urdftools-live-S00-', dir=repositories))
    for src, dst in [('scheduler.py', 'scheduler.py'),
                     ('tests/fixtures/scheduler/numeric_gate.py', 'numeric_gate.py')]:
        shutil.copy2(SOURCE / src, root / dst)
    (root / '.gitignore').write_text('.scheduler/\n__pycache__/\n')
    (root / 'AGENTS.md').write_text('Only implement the tiny local arithmetic fixture. No subagents, Git commits or state edits.\n')
    (root / 'PROGRESS.md').write_text('Live CLI fixture; no product features claimed.\n')
    (root / 'prompt.md').write_text(
        'Create feature.py defining squares(n) = sum of i*i for integers 0..n inclusive. '
        'Run python3 numeric_gate.py; it asserts 0,1,385,338350 for n=0,1,10,100. '
        'Write acceptance.md describing the real results. Return completed only if these tests pass. '
        'Do not modify numeric_gate.py, scheduler.py, scheduler.json, AGENTS.md or .scheduler/.\n')
    config = {'codex_bin': args.codex_bin, 'policy': {'max_phases_per_round': 1,
              'phase_timeout_seconds': 90, 'round_timeout_seconds': 120,
              'preflight_timeout_seconds': 20, 'test_timeout_seconds': 15},
              'phases': [{'id': 'LIVE', 'level': 'ordinary', 'depends_on': [], 'prompt_file': 'prompt.md',
                          'tests': [[sys.executable, 'numeric_gate.py']], 'required': True,
                          'acceptance_artifacts': ['acceptance.md']}]}
    scheduler.atomic_json(root / 'scheduler.json', config)
    def git(*argv):
        return subprocess.check_output(['git', *argv], cwd=root, stderr=subprocess.STDOUT).decode().strip()
    git('init', '-q')
    git('config', 'user.name', 'S00 live acceptance')
    git('config', 'user.email', 's00-live@example.invalid')
    git('add', '.')
    git('commit', '-qm', 'Live acceptance fixture baseline')
    baseline = git('rev-parse', 'HEAD')
    command = [sys.executable, str(root / 'scheduler.py'), 'run']
    process = scheduler.run_process(command, root, 125, args.output / 'scheduler.stdout',
                                    env=scheduler.chatgpt_environment() | {
                                        **({'CODEX_HOME': __import__('os').environ['CODEX_HOME']}
                                           if 'CODEX_HOME' in __import__('os').environ else {})})
    state = scheduler.read_json(root / '.scheduler/state.json', {})
    success = state.get('completed') == ['LIVE'] and process['exit_code'] == 0
    checks = {'numeric_gate': False, 'commit': False, 'repeat_no_duplicate': False}
    if success:
        gate = scheduler.run_process([sys.executable, 'numeric_gate.py'], root, 15,
                                     args.output / 'numeric-gate.stdout')
        checks['numeric_gate'] = gate['exit_code'] == 0 and scheduler.gate_counts(
            (args.output / 'numeric-gate.stdout').read_text())['passed'] == 4
        checks['commit'] = git('rev-list', '--count', 'HEAD') == '2'
        head = git('rev-parse', 'HEAD')
        repeated = scheduler.run_process(command, root, 5, args.output / 'repeat.stdout')
        checks['repeat_no_duplicate'] = repeated['exit_code'] == 0 and git('rev-parse', 'HEAD') == head
    if (root / '.scheduler/runs').exists():
        shutil.copytree(root / '.scheduler/runs', args.output / 'runs', dirs_exist_ok=True)
    for name in ('prompt.md', 'numeric_gate.py', 'scheduler.json', 'PROGRESS.md', 'AGENTS.md'):
        shutil.copy2(root / name, args.output / name)
    report = {'timestamp': scheduler.now(), 'kind': 'real_codex_cli', 'temporary_repository': str(root),
              'command': command, 'baseline_commit': baseline, 'final_commit': git('rev-parse', 'HEAD'),
              'process': process, 'checks': checks, 'attempts': state.get('attempts', []),
              'status': 'passed' if success and all(checks.values()) else 'blocked',
              'source_sha256': scheduler.file_hash(SOURCE / 'scheduler.py')}
    scheduler.atomic_json(args.output / 'report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
