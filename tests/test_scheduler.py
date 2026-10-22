import contextlib
import configparser
import datetime as dt
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
import scheduler


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='urdftools-test-')
        self.addCleanup(self.tmp.cleanup)
        # Fault peers must never inherit the developer's real ChatGPT identity.
        auth_tmp = tempfile.TemporaryDirectory(prefix='urdftools-synthetic-auth-')
        self.addCleanup(auth_tmp.cleanup)
        (Path(auth_tmp.name) / 'auth.json').write_text('{"fixture":"not a credential"}')
        env_patch = patch.dict(os.environ, {'CODEX_HOME': auth_tmp.name})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.root = Path(self.tmp.name)
        shutil.copy2(SOURCE / 'scheduler.py', self.root / 'scheduler.py')
        shutil.copy2(SOURCE / 'tests/fixtures/scheduler/codex_fault.py', self.root / 'codex-fake')
        shutil.copy2(SOURCE / 'tests/fixtures/scheduler/numeric_gate.py', self.root / 'numeric_gate.py')
        (self.root / 'prompt.md').write_text('Fault injection fixture; compute sum of squares, then real gate.\n')
        (self.root / '.gitignore').write_text('.scheduler/\n__pycache__/\nfault.json\ncalls.log\nexec.argv.json\n*.pid\n')
        self.config = {'codex_bin': str(self.root / 'codex-fake'), 'policy': {
            'phase_timeout_seconds': 10, 'round_timeout_seconds': 40,
            'test_timeout_seconds': 3, 'preflight_timeout_seconds': 3, 'retry_seconds': 1},
            'phases': [self.phase('one')]}
        self.save_config()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Scheduler fixture')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture baseline')
        if os.environ.get('S00_EVIDENCE_DIR'):
            self.addCleanup(self.persist_evidence)

    def persist_evidence(self):
        destination = Path(os.environ['S00_EVIDENCE_DIR']) / self._testMethodName
        destination.mkdir(parents=True, exist_ok=True)
        for name in ('scheduler.json', 'fault.json', 'prompt.md', 'calls.log', 'exec.argv.json'):
            if (self.root / name).exists():
                shutil.copy2(self.root / name, destination / name)
        if (self.root / '.scheduler').exists():
            shutil.copytree(self.root / '.scheduler', destination / 'scheduler-evidence',
                            dirs_exist_ok=True, symlinks=True,
                            ignore=shutil.ignore_patterns('codex-homes'))

    def phase(self, ident, dependencies=None):
        return dict(id=ident, level='ordinary', prompt_file='prompt.md', depends_on=dependencies or [],
                    tests=[[sys.executable, 'numeric_gate.py']], acceptance_artifacts=['acceptance.md'], required=True)

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.STDOUT).decode().strip()

    def save_config(self, commit=False):
        (self.root / 'scheduler.json').write_text(json.dumps(self.config))
        if commit:
            self.git('add', 'scheduler.json')
            self.git('commit', '-qm', 'fixture config')

    def fault(self, **value):
        (self.root / 'fault.json').write_text(json.dumps(value))

    def invoke(self, *args, **kwargs):
        return subprocess.run([sys.executable, str(self.root / 'scheduler.py'), *args], cwd=self.root,
                              text=True, capture_output=True, timeout=20, **kwargs)

    def state(self):
        return json.loads((self.root / '.scheduler/state.json').read_text())

    def calls(self):
        path = self.root / 'calls.log'
        return path.read_text().splitlines() if path.exists() else []

    def result(self, expected, **fault):
        self.fault(**fault)
        result = self.invoke('run')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        state = self.state()
        self.assertEqual(state['attempts'][-1]['result'], expected, result.stdout + result.stderr)
        self.assertEqual(state['completed'], [])
        return state

    def test_large_license_exception_is_exact(self):
        name = 'third_party/notices/electron-runtime/LICENSES.chromium.html'
        path = self.root / name
        path.parent.mkdir(parents=True)
        path.write_bytes(b'x' * (5 * 1024 * 1024 + 1))
        instance = scheduler.Scheduler(self.root)
        with self.assertRaises(scheduler.Failure):
            instance.manifest()
        approved = 'c16ee3cc1aa0d1669a839428ef26869d7a3844a43df505377b85077e1db14396'
        with patch.object(scheduler, 'file_hash', return_value=approved):
            self.assertEqual(instance.manifest()[name], approved)
            other = path.with_name('unreviewed.html')
            path.rename(other)
            with self.assertRaises(scheduler.Failure):
                instance.manifest()

    def test_four_model_routes(self):
        for level, (model, effort) in scheduler.LEVELS.items():
            self.config['phases'][0]['level'] = level
            self.save_config()
            result = self.invoke('run', '--dry-run')
            self.assertEqual(result.returncode, 0, result.stderr)
            command = json.loads(result.stdout)['command']
            self.assertIn(model, command)
            self.assertIn('model_reasoning_effort=' + effort, command)
            self.assertIn('forced_login_method="chatgpt"', command)
            self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', command)

    def test_git_success_evidence_and_repeat(self):
        result = self.invoke('run')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        state = self.state()
        self.assertEqual(state['completed'], ['one'])
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '2')
        self.assertEqual(self.git('status', '--porcelain'), '')
        log = self.root / state['attempts'][-1]['log']
        counts = json.loads((log / 'gates.json').read_text())['tests'][0]['counts']
        self.assertEqual(counts['passed'], 4)
        request = json.loads((log / 'request.json').read_text())
        self.assertEqual(request['prompt_sha256'], scheduler.file_hash(log / 'prompt.md'))
        self.assertEqual(json.loads((log / 'session.json').read_text())['thread_ids'], ['fault-thread'])
        before = self.calls()
        result = self.invoke('run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), before)
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '2')

    def test_partial_exit_zero(self):
        self.result('partial', result='partial')
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '1')

    def test_429_and_global_backoff(self):
        self.result('quota_wait', error={'code': 'rate_limit_exceeded', 'status': 429})
        calls = self.calls()
        self.assertNotEqual(self.invoke('run').returncode, 0)
        self.assertEqual(self.calls(), calls)

    def test_usage_read_429_allows_one_bounded_exec(self):
        self.config['phases'].append(self.phase('two', ['one']))
        self.save_config(commit=True)
        self.fault(rpc_errors={'account/rateLimits/read': {'status': 429, 'code': 'rate_limit_exceeded'}})
        result = self.invoke('run')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.state()['completed'], ['one'])
        self.assertEqual(self.state()['quota_snapshot']['status'], 'unknown')
        self.assertEqual(self.state()['quota_snapshot']['read_error_class'], 'quota_wait')
        self.assertEqual(self.calls().count('exec'), 1)

    def test_nested_usage_read_429_allows_exec_but_exec_429_stops(self):
        self.result('quota_wait', rpc_errors={'account/rateLimits/read': {
            'code': -32603, 'data': None,
            'codexErrorInfo': {'httpConnectionFailed': {'httpStatusCode': 429}}}},
            error={'code': 'rate_limit_exceeded', 'status': 429})
        self.assertEqual(self.calls().count('exec'), 1)
        before = self.calls()
        self.assertNotEqual(self.invoke('run').returncode, 0)
        self.assertEqual(self.calls(), before)

    def test_usage_read_401_still_requires_auth(self):
        self.result('auth_required', rpc_errors={'account/rateLimits/read': {
            'status': 401, 'code': 'unauthorized'}})
        self.assertNotIn('exec', self.calls())

    def test_typed_error_variants_keep_shared_backoff(self):
        self.result('quota_wait', error={'codexErrorInfo': 'UsageLimitExceeded'})
        before = self.calls()
        self.assertNotEqual(self.invoke('run').returncode, 0)
        self.assertEqual(self.calls(), before)

    def test_structured_http_error_classification(self):
        for error in ({'code': 429}, {'httpStatusCode': 429},
                      {'codexErrorInfo': {'httpStatusCode': 429}},
                      {'codexErrorInfo': 'RateLimitExceeded'}):
            with self.subTest(error=error):
                self.assertEqual(scheduler.classify_failure([{'type': 'turn.failed', 'error': error}]), 'quota_wait')
        for error in ({'code': 401}, {'codexErrorInfo': 'Unauthorized'},
                      {'codexErrorInfo': {'httpConnectionFailed': {'httpStatusCode': 401}}}):
            with self.subTest(error=error):
                self.assertEqual(scheduler.classify_failure([{'type': 'error', 'error': error}]), 'auth_required')

    def test_text_429_does_not_match(self):
        self.assertEqual(self.invoke('run').returncode, 0)

    def test_unknown_quota_one_bounded_exec(self):
        self.fault(quota_unknown=True)
        result = self.invoke('run')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.state()['quota_snapshot']['status'], 'unknown')
        self.assertEqual(self.calls().count('exec'), 1)

    def test_unknown_quota_stops_multi_phase_round(self):
        self.config['phases'].append(self.phase('two', ['one']))
        self.save_config(commit=True)
        self.fault(quota_unknown=True)
        self.assertEqual(self.invoke('run').returncode, 0)
        self.assertEqual(self.state()['completed'], ['one'])
        self.assertEqual(self.calls().count('exec'), 1)

    def test_no_tasks_no_external_calls(self):
        self.config['phases'] = []
        self.save_config(commit=True)
        self.assertEqual(self.invoke('run').returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_three_phase_round_ceiling(self):
        self.config['phases'] = [self.phase(str(i)) for i in range(4)]
        self.save_config(commit=True)
        self.assertEqual(self.invoke('run').returncode, 0)
        self.assertEqual(self.state()['completed'], ['0', '1', '2'])
        self.assertEqual(self.calls().count('exec'), 3)

    def test_quota_threshold_and_model_buckets(self):
        self.result('quota_wait', buckets={'astra': {'secondary': {'usedPercent': 96}}})
        self.assertNotIn('exec', self.calls())

    def test_primary_quota_boundary(self):
        self.result('quota_wait', primary=90)
        self.assertNotIn('exec', self.calls())

    def test_chatgpt_only_and_no_inherited_keys(self):
        env = os.environ | {'OPENAI_API_KEY': 'not-a-real-key', 'CODEX_API_KEY': 'not-a-real-key',
                            'ANTHROPIC_API_KEY': 'not-a-real-key', 'OPENAI_BASE_URL': 'https://invalid.example'}
        self.fault(auth='apiKey')
        result = self.invoke('run', env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state()['attempts'][-1]['result'], 'auth_required')
        self.assertNotIn('exec', self.calls())

    def test_model_unavailable_no_downgrade(self):
        self.config['phases'][0]['level'] = 'critical_xhigh'
        self.save_config(commit=True)
        self.result('wait_model', models=['gpt-6-sol'])
        self.assertNotIn('exec', self.calls())

    def test_explicit_sol_fallback(self):
        self.fault(models=['gpt-6-sol'])
        result = self.invoke('run')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        path = self.root / self.state()['attempts'][-1]['log'] / 'request.json'
        request = json.loads(path.read_text())
        self.assertEqual(request['model'], 'gpt-6-sol')
        self.assertTrue(request['substitution'])

    def test_invalid_result(self):
        self.result('partial', invalid_result=True)

    def test_invalid_stream(self):
        self.result('partial', invalid_stream=True)

    def test_missing_turn_completed(self):
        self.result('partial', no_turn=True)

    def test_completed_with_blocker_fails(self):
        self.result('partial', blockers=['not actually done'])

    def test_graph_validation(self):
        self.config['phases'] += [self.phase('two', ['one'])]
        self.config['phases'][0]['depends_on'] = ['two']
        self.save_config()
        self.assertEqual(self.invoke('validate').returncode, 2)
        self.config['phases'][0]['depends_on'] = ['missing']
        self.save_config()
        self.assertEqual(self.invoke('validate').returncode, 2)
        self.config['phases'][0]['depends_on'] = []
        self.config['phases'][0]['tests'] = []
        self.save_config()
        self.assertEqual(self.invoke('validate').returncode, 2)

    def test_dependency_order(self):
        self.config['phases'] = [self.phase('two', ['one']), self.phase('one')]
        self.save_config(commit=True)
        result = self.invoke('run')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.state()['completed'], ['one', 'two'])

    def test_hardware_wait_does_not_block_independent(self):
        self.config['phases'].append(self.phase('independent'))
        self.save_config(commit=True)
        directory = self.root / '.scheduler'
        directory.mkdir()
        scheduler.atomic_json(directory / 'state.json', dict(completed=[], attempts=[], tasks={
            'one': {'status': 'blocked_hardware', 'reason': 'no GPU'}}))
        result = self.invoke('run')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.state()['completed'], ['independent'])

    def test_hardware_wip_checkpoint_and_operator_resume(self):
        self.config['phases'].append(self.phase('independent'))
        self.save_config(commit=True)
        self.fault(by_phase={'one': {'result': 'blocked', 'blocker_type': 'hardware'}})
        result = self.invoke('run')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.state()['completed'], ['independent'])
        checkpoint = self.state()['checkpoints']['one']
        self.assertEqual(checkpoint['files']['feature.py'], scheduler.file_hash(
            self.root / checkpoint['directory'] / 'feature.py'))
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.fault()
        self.assertEqual(self.invoke('retry', 'one').returncode, 0)
        # Independent fixture wrote the same names, so overwrite is refused until reviewed.
        retry = self.invoke('run')
        self.assertNotEqual(retry.returncode, 0)
        self.assertIn('checkpoint conflicts', retry.stderr)

    def test_checkpoint_resume_preserves_exact_wip(self):
        self.result('blocked_hardware', result='blocked', blocker_type='hardware')
        self.assertIn('one', self.state()['checkpoints'])
        self.assertFalse((self.root / 'feature.py').exists())
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.fault()
        self.assertEqual(self.invoke('retry', 'one').returncode, 0)
        result = self.invoke('run')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.state()['completed'], ['one'])
        self.assertEqual(self.state()['checkpoints'], {})

    def test_restored_checkpoint_is_reparked_when_quota_threshold_stops_preflight(self):
        self.result('blocked_hardware', result='blocked', blocker_type='hardware')
        first = self.state()['checkpoints']['one']
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual(self.invoke('retry', 'one').returncode, 0)
        self.fault(primary=90)
        stopped = self.invoke('run')
        self.assertEqual(stopped.returncode, 75, stopped.stderr + stopped.stdout)
        self.assertEqual(self.state()['attempts'][-1]['result'], 'quota_wait')
        self.assertIn('one', self.state()['checkpoints'])
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual(self.state()['checkpoints']['one']['files'], first['files'])
        self.assertEqual(self.invoke('retry', 'one').returncode, 0)
        self.fault()
        resumed = self.invoke('run')
        self.assertEqual(resumed.returncode, 0, resumed.stderr + resumed.stdout)
        self.assertEqual(self.state()['completed'], ['one'])

    def test_waiting_experiment_poll_avoids_model(self):
        self.config['phases'][0]['experiment_status_file'] = 'job.json'
        self.save_config(commit=True)
        self.result('waiting_experiment', result='waiting_experiment', job_id='job-42')
        before = self.calls()
        self.assertEqual(self.invoke('run').returncode, 0)
        self.assertEqual(self.calls(), before)
        self.assertEqual(self.state()['tasks']['one']['job_id'], 'job-42')

    def test_zero_tests_rejected(self):
        self.config['phases'][0]['tests'] = [[sys.executable, '-m', 'unittest', 'discover', '-s', 'empty']]
        (self.root / 'empty').mkdir()
        (self.root / 'empty/.keep').write_text('fixture')
        self.save_config(commit=True)
        self.git('add', 'empty')
        self.git('commit', '-qm', 'empty discovery fixture')
        self.result('test_failed')

    def test_all_skipped_rejected(self):
        (self.root / 'test_skip.py').write_text('import unittest\nclass Skip(unittest.TestCase):\n'
            ' @unittest.skip("injected")\n def test_skip(self): pass\n')
        self.config['phases'][0]['tests'] = [[sys.executable, '-m', 'unittest', 'test_skip']]
        self.save_config(commit=True)
        self.git('add', 'test_skip.py')
        self.git('commit', '-qm', 'all skip fixture')
        self.result('test_failed')

    def test_real_test_failure(self):
        self.config['phases'][0]['tests'] = [[sys.executable, '-c', 'assert 385 == 384']]
        self.save_config(commit=True)
        self.result('test_failed')

    def test_unrecognized_zero_exit_is_not_gate(self):
        self.config['phases'][0]['tests'] = [[sys.executable, '-c', 'pass']]
        self.save_config(commit=True)
        self.result('test_failed')

    def test_multiple_gates_keep_separate_logs(self):
        self.config['phases'][0]['tests'] *= 2
        self.save_config(commit=True)
        result = self.invoke('run')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        tests = json.loads((self.root / self.state()['attempts'][-1]['log'] / 'gates.json').read_text())['tests']
        self.assertEqual([x['counts']['passed'] for x in tests], [4, 4])

    def test_graph_mutation_rejected(self):
        self.result('blocked_input', graph_change=True)

    def test_gate_cannot_replace_plan_before_commit(self):
        # Real gate process tampers with the next phase after the model finished.
        command = ('import json; from pathlib import Path; p=Path("scheduler.json"); '
                   'c=json.loads(p.read_text()); c["phases"][1]["level"]="critical"; '
                   'p.write_text(json.dumps(c)); '
                   'print(json.dumps({"scheduler_gate":{"executed":1,"passed":1,"failed":0,"skipped":0}}))')
        self.config['phases'].append(self.phase('independent'))
        self.config['phases'][0]['tests'] = [[sys.executable, '-c', command]]
        self.save_config(commit=True)
        before_head = self.git('rev-parse', 'HEAD')
        self.result('blocked_input')
        self.assertEqual(self.calls().count('exec'), 1)
        self.assertEqual(self.git('rev-parse', 'HEAD'), before_head)
        self.assertNotIn('checkpoints', self.state())
        self.assertEqual(json.loads((self.root / 'scheduler.json').read_text())['phases'][1]['level'], 'critical')

    def test_existing_user_changes_protected(self):
        original = (self.root / 'prompt.md').read_bytes()
        (self.root / 'prompt.md').write_bytes(original + b'user edit')
        result = self.invoke('run')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / 'prompt.md').read_bytes(), original + b'user edit')
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '1')

    def test_staged_user_changes_protected(self):
        (self.root / 'user.txt').write_text('keep me')
        self.git('add', 'user.txt')
        before = self.git('diff', '--cached')
        self.assertNotEqual(self.invoke('run').returncode, 0)
        self.assertEqual(self.git('diff', '--cached'), before)
        self.assertEqual(self.calls(), [])

    def test_gitignore_is_safe_phase_wip_but_other_dotfiles_are_not(self):
        (self.root / '.gitignore').write_text((self.root / '.gitignore').read_text() + 'dist/\n')
        manifest = scheduler.Scheduler(self.root).manifest()
        self.assertIn('.gitignore', manifest)
        (self.root / '.secret').write_text('do not commit')
        with self.assertRaises(scheduler.Failure):
            scheduler.Scheduler(self.root).manifest()

    def test_concurrent_lock(self):
        directory = self.root / '.scheduler'
        directory.mkdir()
        with (directory / 'run.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.invoke('run').returncode, 3)
        self.assertEqual(self.calls(), [])

    def assert_child_dead(self):
        pid = int((self.root / 'child.pid').read_text())
        for _ in range(30):
            stat = Path('/proc') / str(pid) / 'stat'
            if not stat.exists() or stat.read_text().split()[2] == 'Z':
                return
            time.sleep(.03)
        self.fail('descendant still executing: ' + str(pid))

    def test_timeout_kills_descendants(self):
        self.config['policy']['phase_timeout_seconds'] = 1
        self.save_config(commit=True)
        self.result('timeout', sleep=True, ignore_term=True)
        self.assert_child_dead()
        self.assertNotEqual(self.invoke('run').returncode, 3)

    def test_signal_kills_descendants_and_releases_lock(self):
        self.fault(sleep=True)
        proc = subprocess.Popen([sys.executable, 'scheduler.py', 'run'], cwd=self.root,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        deadline = time.monotonic() + 5
        while not (self.root / 'child.pid').exists() and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertTrue((self.root / 'child.pid').exists())
        proc.send_signal(signal.SIGTERM)
        proc.communicate(timeout=5)
        self.assertEqual(self.state()['attempts'][-1]['result'], 'interrupted')
        self.assert_child_dead()
        self.assertNotEqual(self.invoke('run').returncode, 3)

    def test_hard_crash_recovers_live_orphan_group(self):
        self.fault(sleep=True)
        proc = subprocess.Popen([sys.executable, 'scheduler.py', 'run'], cwd=self.root,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        deadline = time.monotonic() + 5
        while not (self.root / 'child.pid').exists() and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertTrue((self.root / 'child.pid').exists())
        proc.kill()
        proc.communicate(timeout=5)
        before = self.calls()
        self.assertEqual(self.invoke('run').returncode, 0)
        self.assertEqual(self.state()['attempts'][-1]['result'], 'interrupted')
        self.assertEqual(self.calls(), before)
        self.assert_child_dead()

    def test_commit_failure_recovers_without_new_exec(self):
        hook = self.root / '.git' / (self.git('symbolic-ref', 'HEAD') + '.lock')
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text('real ref lock fault')
        self.result('commit_failed')
        before = self.calls()
        hook.unlink()
        result = self.invoke('run')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.calls(), before)
        self.assertEqual(self.state()['completed'], ['one'])
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '2')
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_failed_commit_tampered_evidence_never_resealed(self):
        hook = self.root / '.git' / (self.git('symbolic-ref', 'HEAD') + '.lock')
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text('real ref lock fault')
        self.result('commit_failed')
        hook.unlink()
        log = self.root / self.state()['attempts'][-1]['log']
        (log / 'test-00.stdout').write_text('changed after successful numeric gate\n')
        before = self.calls()
        result = self.invoke('run')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('evidence changed', result.stderr)
        self.assertEqual(self.calls(), before)
        self.assertEqual(self.state()['completed'], [])
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '1')
        self.assertEqual((log / 'test-00.stdout').read_text(), 'changed after successful numeric gate\n')

    def test_unsealed_pending_transaction_requires_review(self):
        hook = self.root / '.git' / (self.git('symbolic-ref', 'HEAD') + '.lock')
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text('real ref lock fault')
        self.result('commit_failed')
        hook.unlink()
        journal_path = self.root / '.scheduler/journal.json'
        journal = scheduler.read_json(journal_path)
        journal.pop('evidence_sha256', None)
        scheduler.atomic_json(journal_path, journal)
        before = self.calls()
        result = self.invoke('run')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('unsealed', result.stderr)
        self.assertEqual(self.calls(), before)
        self.assertEqual(self.state()['completed'], [])
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '1')

    def test_commit_done_state_not_saved_recovery(self):
        # Crash exactly after Git commit, before JSON state; real Git, no process mocks.
        script = '''import scheduler\ns=scheduler.Scheduler(scheduler.ROOT)\ndef crash(*args):\n import os\n os._exit(91)\ns.finish=crash\ns.run()\n'''
        result = subprocess.run([sys.executable, '-c', script], cwd=self.root, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 91, result.stderr)
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '2')
        before = self.calls()
        result = self.invoke('run')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.state()['completed'], ['one'])
        self.assertEqual(self.calls(), before)
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '2')

    def test_false_completed_without_commit_rejected(self):
        scheduler.atomic_json(self.root / '.scheduler/state.json', {'completed': ['one'], 'attempts': []})
        self.assertNotEqual(self.invoke('run').returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_tampered_completion_evidence_rejected(self):
        self.assertEqual(self.invoke('run').returncode, 0)
        log = self.root / self.state()['attempts'][-1]['log']
        (log / 'gates.json').write_text('{"passed":true,"tests":[]}')
        before = self.calls()
        result = self.invoke('run')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), before)

    def test_tampered_raw_test_log_rejected(self):
        self.assertEqual(self.invoke('run').returncode, 0)
        log = self.root / self.state()['attempts'][-1]['log']
        (log / 'test-00.stdout').write_text('altered raw numeric results\n')
        before = self.calls()
        self.assertNotEqual(self.invoke('run').returncode, 0)
        self.assertEqual(self.calls(), before)

    def test_stale_instance_reloads_after_lock(self):
        stale = scheduler.Scheduler(self.root)
        self.assertEqual(self.invoke('run').returncode, 0)
        before = self.calls()
        state_bytes = (self.root / '.scheduler/state.json').read_bytes()
        self.assertEqual(stale.run(), 0)
        self.assertEqual(stale.state['completed'], ['one'])
        self.assertEqual(self.calls(), before)
        self.assertEqual((self.root / '.scheduler/state.json').read_bytes(), state_bytes)
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '2')

    def test_failed_commit_changed_files_not_committed(self):
        hook = self.root / '.git' / (self.git('symbolic-ref', 'HEAD') + '.lock')
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text('real ref lock fault')
        self.result('commit_failed')
        hook.unlink()
        (self.root / 'feature.py').write_text('user changed after gates\n')
        before = self.calls()
        self.assertNotEqual(self.invoke('run').returncode, 0)
        self.assertEqual(self.calls(), before)
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '1')

    def test_project_provider_config_refused(self):
        directory = self.root / '.codex'
        directory.mkdir()
        (directory / 'config.toml').write_text('model_provider="paid"\n')
        self.assertEqual(self.invoke('validate').returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_isolated_codex_home_excludes_provider_and_mcp(self):
        auth_source = self.root / 'auth-source'
        auth_source.mkdir()
        (auth_source / 'auth.json').write_text('{"fixture":"synthetic auth, no token"}')
        with patch.dict(os.environ, {'CODEX_HOME': str(auth_source)}), scheduler.codex_home(self.root) as env:
            home = Path(env['CODEX_HOME'])
            self.assertEqual(home.parent, self.root / '.scheduler/codex-homes')
            self.assertEqual(set(home.iterdir()), {home / 'auth.json', home / 'config.toml'})
            self.assertTrue((home / 'auth.json').is_symlink())
            self.assertEqual((home / 'auth.json').resolve(), auth_source / 'auth.json')
            self.assertEqual((home / 'auth.json').read_text(), '{"fixture":"synthetic auth, no token"}')
            self.assertIn('forced_login_method = "chatgpt"', (home / 'config.toml').read_text())
            self.assertNotIn('OPENAI_API_KEY', env)
        self.assertFalse(home.exists())
        self.assertEqual((auth_source / 'auth.json').read_text(), '{"fixture":"synthetic auth, no token"}')

    def test_changed_wip_not_overwritten(self):
        self.result('partial', result='partial')
        (self.root / 'feature.py').write_text('user intervened\n')
        time.sleep(1.05)
        before = self.calls()
        self.assertNotEqual(self.invoke('run').returncode, 0)
        self.assertEqual(self.calls(), before)
        self.assertEqual((self.root / 'feature.py').read_text(), 'user intervened\n')

    def test_self_modification_stops_round(self):
        self.config['phases'].append(self.phase('two', ['one']))
        self.save_config(commit=True)
        self.fault(edit_scheduler=True)
        result = self.invoke('run')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.state()['completed'], ['one'])
        self.assertEqual(self.calls().count('exec'), 1)
        self.fault()
        self.assertEqual(self.invoke('run').returncode, 0)
        self.assertEqual(self.state()['completed'], ['one', 'two'])

    def test_gate_counts_numerical_invariants(self):
        for text in ['Ran 0 tests in 0.000s\n\nOK', 'Ran 1 test in 0.001s\n\nOK (skipped=1)',
                     '{"scheduler_gate":{"executed":1,"passed":2,"failed":0,"skipped":0}}']:
            counts = scheduler.gate_counts(text)
            self.assertTrue(counts is None or counts['passed'] == 0)

    def test_repository_plan_preserved(self):
        baseline = {'phases': json.loads((SOURCE / 'tests/fixtures/scheduler/plan-baseline.json').read_text())}
        current = scheduler.load_config(SOURCE)
        self.assertEqual(len(current['phases']), 50)
        self.assertEqual(current['phases'][1:], baseline['phases'][1:])
        first = dict(current['phases'][0])
        added = first['tests'][len(baseline['phases'][0]['tests']):]
        self.assertEqual(added, [['python3', 'scripts/check_s00_acceptance.py']])
        first['tests'] = first['tests'][:len(baseline['phases'][0]['tests'])]
        self.assertEqual(first, baseline['phases'][0])

    def test_real_systemd_calendar_has_hourly_intervals(self):
        timer = configparser.ConfigParser(interpolation=None)
        timer.read(SOURCE / 'systemd/urdftools-dev.timer')
        self.assertTrue(timer.getboolean('Timer', 'Persistent'))
        calendar = timer['Timer']['OnCalendar']
        self.assertEqual(calendar, '*-*-* *:00:00')
        command = ['systemd-analyze', 'calendar', '--base-time=2026-10-22 00:00:01', '--iterations=4', calendar]
        result = subprocess.run(command, env=os.environ | {'TZ': 'Asia/Shanghai', 'LC_ALL': 'C'},
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        times = [dt.datetime.strptime(line.split('(in UTC): ', 1)[1], '%a %Y-%m-%d %H:%M:%S UTC')
                 for line in result.stdout.splitlines() if '(in UTC): ' in line]
        self.assertEqual(len(times), 4)
        self.assertEqual(times[0], dt.datetime(2026, 10, 21, 17))
        self.assertEqual([(b - a).total_seconds() for a, b in zip(times, times[1:])], [3600] * 3)
        if os.environ.get('S00_EVIDENCE_DIR'):
            target = Path(os.environ['S00_EVIDENCE_DIR']) / self._testMethodName / 'calendar.json'
            scheduler.atomic_json(target, {'command': command, 'exit_code': result.returncode,
                                           'stdout': result.stdout, 'stderr': result.stderr})

    def test_s00_acceptance_gate_rejects_missing_or_blocked_live(self):
        spec = importlib.util.spec_from_file_location('s00_gate', SOURCE / 'scripts/check_s00_acceptance.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        checks = module.evaluate(self.root)
        self.assertEqual(len(checks), 3)
        self.assertFalse(any(item['passed'] for item in checks))
        live = self.root / 'artifacts/S00/live-smoke/report.json'
        scheduler.atomic_json(live, {'status': 'blocked', 'kind': 'real_codex_cli'})
        self.assertFalse(module.evaluate(self.root)[1]['passed'])

    def test_s00_timer_gate_requires_deployed_units_and_actual_trigger(self):
        spec = importlib.util.spec_from_file_location('s00_timer_gate', SOURCE / 'scripts/check_s00_acceptance.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name in ('systemd/urdftools-dev.service', 'systemd/urdftools-dev.timer', 'scripts/verify_scheduler_timer.py'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / name, target)
        path = self.root / 'artifacts/S00/timer/report.json'
        report = {'status': 'passed', 'actual_trigger': {'token': 'fixture', 'elapsed_seconds': 2.5},
                  'source_sha256': scheduler.file_hash(self.root / 'systemd/urdftools-dev.service'),
                  'timer_sha256': scheduler.file_hash(self.root / 'systemd/urdftools-dev.timer'),
                  'verifier_sha256': scheduler.file_hash(self.root / 'scripts/verify_scheduler_timer.py'),
                  'deployment_matches': True, 'timer_active': True}
        scheduler.atomic_json(path, report)
        self.assertTrue(module.evaluate(self.root)[2]['passed'])
        for key, value in [('deployment_matches', False), ('timer_active', False),
                           ('actual_trigger', {}), ('timer_sha256', 'stale')]:
            scheduler.atomic_json(path, report | {key: value})
            self.assertFalse(module.evaluate(self.root)[2]['passed'], key)


if __name__ == '__main__':
    unittest.main()
