#!/usr/bin/env python3
"""Bounded ChatGPT-only development scheduler; all writes belong to the selected root."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parent
LEVELS = {
    'ordinary': ('gpt-6.1-sol', 'medium'),
    'complex': ('gpt-6.1-sol', 'high'),
    'critical': ('gpt-6-astra', 'high'),
    'critical_xhigh': ('gpt-6-astra', 'xhigh'),
}
POLICY = dict(max_phases_per_round=3, round_timeout_seconds=14400,
              phase_timeout_seconds=4200, test_timeout_seconds=1200,
              preflight_timeout_seconds=45, primary_used_pause_percent=90,
              secondary_used_pause_percent=95, retry_seconds=14400)
RESULT_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'status': {'type': 'string', 'enum': ['completed', 'partial', 'blocked', 'waiting_experiment']},
        'summary': {'type': 'string'},
        'blockers': {'type': 'array', 'items': {'type': 'string'}},
        'artifacts': {'type': 'array', 'items': {'type': 'string'}},
        'job_id': {'type': ['string', 'null']},
        'blocker_type': {'type': ['string', 'null'],
                         'enum': ['hardware', 'input', None]},
    },
    'required': ['status', 'summary', 'blockers', 'artifacts', 'job_id', 'blocker_type'],
}
STOP = None


class Failure(Exception):
    def __init__(self, status, reason):
        self.status, self.reason = status, reason
        super().__init__(reason)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    return digest(path.read_bytes()) if path.is_file() else None


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as out:
            name = out.name
            json.dump(data, out, ensure_ascii=False, indent=2, allow_nan=False)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def read_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def chatgpt_environment():
    # Positive environment boundary: no inherited API keys, providers, proxy credentials,
    # shell hooks, Python injection or Git index overrides. No token values are logged.
    allowed = {'HOME', 'PATH', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TZ', 'TMPDIR',
               'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS', 'SSL_CERT_FILE', 'SSL_CERT_DIR'}
    return {k: v for k, v in os.environ.items() if k in allowed or k.startswith('LC_')}


@contextlib.contextmanager
def codex_home(root):
    """Discard all user/provider/MCP configuration; use only existing ChatGPT auth."""
    root = root.resolve()
    auth = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'auth.json'
    # Stay inside the selected writable workspace, never the global Codex home.
    # Only an auth symlink is created; credentials do not enter source/evidence.
    isolated_parent = root / '.scheduler' / 'codex-homes'
    isolated_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='urdftools-chatgpt-', dir=isolated_parent) as directory:
        home = Path(directory)
        if auth.is_file():
            (home / 'auth.json').symlink_to(auth.resolve())
        (home / 'config.toml').write_text('forced_login_method = "chatgpt"\n'
                                         'model_provider = "openai"\n'
                                         'approval_policy = "never"\n')
        env = chatgpt_environment()
        env['CODEX_HOME'] = str(home)
        yield env


def stop_handler(signum, _frame):
    global STOP
    STOP = signum


def kill_group(proc):
    # Always kill the group, including descendants whose leader has already exited.
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        proc.wait()
        return
    try:
        proc.wait(timeout=0.3)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def process_identity(pid):
    try:
        stat = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
        return {'pid': pid, 'start_ticks': stat[19], 'group': int(stat[2]),
                'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except (OSError, IndexError):
        return None


def recover_process(marker):
    identity = read_json(marker)
    if not identity:
        return
    current = process_identity(identity['pid'])
    if current == identity and current['group'] == current['pid']:
        try:
            os.killpg(current['pid'], signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_process(argv, cwd, timeout, output, env=None, input_text=None):
    """Stream independent stdout/stderr to disk; bounded even with inherited pipe holders."""
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    atomic_json(output.with_suffix(output.suffix + '.started.json'), process_identity(proc.pid))
    selector = selectors.DefaultSelector()
    with output.open('wb') as stdout, output.with_suffix(output.suffix + '.stderr').open('wb') as stderr:
        for pipe, target in ((proc.stdout, stdout), (proc.stderr, stderr)):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, target)
        pending = input_text.encode() if input_text is not None else b''
        if proc.stdin:
            os.set_blocking(proc.stdin.fileno(), False)
            selector.register(proc.stdin, selectors.EVENT_WRITE, None)
        status = None
        try:
            while selector.get_map():
                if STOP or time.monotonic() - started >= timeout:
                    status = 'interrupted' if STOP else 'timeout'
                    break
                for key, _ in selector.select(0.05):
                    if key.fileobj is proc.stdin:
                        try:
                            n = os.write(proc.stdin.fileno(), pending[:65536]) if pending else 0
                            pending = pending[n:]
                        except BrokenPipeError:
                            pending = b''
                        if not pending:
                            selector.unregister(proc.stdin)
                            proc.stdin.close()
                    else:
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if chunk:
                            key.data.write(chunk)
                            key.data.flush()
                        else:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
            while status is None and proc.poll() is None:
                if STOP or time.monotonic() - started >= timeout:
                    status = 'interrupted' if STOP else 'timeout'
                    break
                time.sleep(0.02)
        finally:
            kill_group(proc)
            selector.close()
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream and not stream.closed:
                    stream.close()
        result = dict(argv=argv, exit_code=proc.returncode, status=status,
                      duration_seconds=round(time.monotonic() - started, 3))
        for target in (stdout, stderr):
            target.flush()
            os.fsync(target.fileno())
    atomic_json(output.with_suffix(output.suffix + '.process.json'), result)
    return result


class RPC:
    """Only read-only preflight RPCs are exposed; never login/reset/buy credits."""
    def __init__(self, codex, root, env, timeout, directory):
        self.stderr = (directory / 'app-server.stderr').open('wb')
        self.proc = subprocess.Popen([codex, 'app-server', '--listen', 'stdio://'], cwd=root,
                                     env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.stderr, start_new_session=True)
        atomic_json(directory / 'app-server.started.json', process_identity(self.proc.pid))
        self.seq = 0
        self.deadline = time.monotonic() + timeout
        self.buffer = b''
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.proc.stdout, selectors.EVENT_READ)
        os.set_blocking(self.proc.stdout.fileno(), False)

    def call(self, method, params=None):
        if method not in {'initialize', 'account/read', 'model/list', 'account/rateLimits/read'}:
            raise ValueError('RPC not permitted')
        self.seq += 1
        request = dict(id=self.seq, method=method)
        if params is not None:
            request['params'] = params
        self.send(request)
        while time.monotonic() < self.deadline and not STOP:
            while b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if event.get('id') == self.seq:
                    failure = classify_failure([{'type': 'error', 'error': event.get('error', {})}])
                    # A 429 from the read-only usage endpoint does not prove that
                    # model inference is exhausted. Preserve it as unknown usage;
                    # one bounded exec will confirm whether inference can run.
                    if method == 'account/rateLimits/read' and failure == 'quota_wait':
                        return event
                    if failure in {'quota_wait', 'auth_required'}:
                        raise Failure(failure, 'preflight RPC rejected: ' + method)
                    return event
                # No callbacks are serviced: interactive login/approvals cannot proceed.
            if self.selector.select(0.05):
                chunk = os.read(self.proc.stdout.fileno(), 65536)
                if not chunk:
                    break
                self.buffer += chunk
        return {'error': {'code': 'interrupted' if STOP else 'unavailable'}}

    def send(self, value):
        try:
            self.proc.stdin.write((json.dumps(value) + '\n').encode())
            self.proc.stdin.flush()
        except BrokenPipeError:
            raise Failure('auth_required', 'app-server exited during preflight')

    def close(self):
        kill_group(self.proc)
        self.selector.close()
        self.proc.stdin.close()
        self.proc.stdout.close()
        self.stderr.close()


def preflight(codex, root, env, policy, directory):
    rpc = RPC(codex, root, env, policy['preflight_timeout_seconds'], directory)
    snapshot = dict(timestamp=now(), auth='unknown', models=[], quota={'status': 'unknown'})
    try:
        initialized = rpc.call('initialize', {'clientInfo': {'name': 'urdftools_scheduler',
                               'title': 'URDFTools scheduler', 'version': '1.0.0'}})
        if 'error' in initialized:
            raise Failure('auth_required', 'app-server initialization unavailable')
        rpc.send({'method': 'initialized'})
        # Model catalog is read-only and useful evidence even when account routing
        # discovery fails. It does not prove model entitlement.
        response = rpc.call('model/list', {'limit': 100, 'includeHidden': True, 'cursor': None})
        if 'result' in response:
            snapshot['models'].extend(response['result'].get('data', []))
            cursor = response['result'].get('nextCursor')
        else:
            cursor = None
            snapshot['model_error'] = response.get('error', {}).get('code', 'unavailable')
        response = rpc.call('account/read', {'refreshToken': False})
        account = response.get('result', {}).get('account') or {}
        snapshot['auth'] = account.get('type', 'unknown')
        snapshot['plan_type'] = account.get('planType')
        if snapshot['auth'] != 'chatgpt':
            snapshot['auth_error'] = response.get('error', {}).get('message', 'ChatGPT identity unavailable')
            raise Failure('auth_required', 'account/read did not verify ChatGPT identity')
        for _ in range(19):
            if not cursor:
                break
            response = rpc.call('model/list', {'limit': 100, 'includeHidden': True, 'cursor': cursor})
            if 'error' in response:
                snapshot['model_error'] = response['error'].get('code', 'unavailable')
                break
            snapshot['models'].extend(response.get('result', {}).get('data', []))
            cursor = response.get('result', {}).get('nextCursor')
            if not cursor:
                break
        response = rpc.call('account/rateLimits/read')
        result = response.get('result')
        if isinstance(result, dict):
            # Credits/reset products are intentionally excluded; only usage windows are kept.
            snapshot['quota'] = dict(status='available', rateLimits=result.get('rateLimits'),
                                      rateLimitsByLimitId=result.get('rateLimitsByLimitId'))
            windows = [result.get('rateLimits')] + list((result.get('rateLimitsByLimitId') or {}).values())
            if not any(isinstance(b, dict) and any(
                    type((b.get(w) or {}).get('usedPercent')) in (int, float) and
                    math.isfinite((b[w]['usedPercent'])) for w in ('primary', 'secondary')) for b in windows):
                snapshot['quota']['status'] = 'unknown'
        else:
            snapshot['quota']['error_code'] = response.get('error', {}).get('code', 'unavailable')
            snapshot['quota']['read_error_class'] = classify_failure(
                [{'type': 'error', 'error': response.get('error', {})}])
        if STOP:
            raise Failure('interrupted', 'signal during preflight')
        return snapshot
    finally:
        atomic_json(directory / 'preflight.json', snapshot)
        rpc.close()


def route(phase, snapshot):
    requested, effort = LEVELS[phase['level']]
    for candidate in ([requested, 'gpt-6-sol'] if requested == 'gpt-6.1-sol' else [requested]):
        for model in snapshot['models']:
            if model.get('model', model.get('id')) == candidate and effort in [
                    item.get('reasoningEffort') for item in model.get('supportedReasoningEfforts', [])]:
                return candidate, effort
    raise Failure('wait_model', 'requested model/effort absent from model/list')


def quota_pause(snapshot, policy):
    quota = snapshot['quota']
    buckets = [quota.get('rateLimits')]
    buckets += list((quota.get('rateLimitsByLimitId') or {}).values())
    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        if bucket.get('rateLimitReachedType'):
            return True
        for window in ('primary', 'secondary'):
            value = (bucket.get(window) or {}).get('usedPercent')
            if isinstance(value, (int, float)) and math.isfinite(value) and value >= policy[window + '_used_pause_percent']:
                return True
    return False


def classify_failure(events):
    """Only typed error events are interpreted. Agent text cannot trigger quota handling."""
    for event in events:
        if event.get('type') not in {'error', 'turn.failed'}:
            continue
        error = event.get('error', event)
        if not isinstance(error, dict):
            continue
        info = error.get('codexErrorInfo') or error.get('code') or error.get('type')
        encoded = re.sub(r'[^a-z0-9]', '', json.dumps(info).lower())
        # Upstream statuses can be inside a tagged codexErrorInfo variant.
        # Read only structured status fields, never numbers in agent prose.
        def statuses(value):
            if not isinstance(value, dict):
                return []
            found = [value.get(k) for k in ('status', 'http_status', 'httpStatusCode', 'code')]
            for nested in value.values():
                if isinstance(nested, dict):
                    found.extend(statuses(nested))
            return found
        http_codes = statuses(error)
        if (429 in http_codes or any(code in encoded for code in (
                'usagelimitexceeded', 'ratelimitexceeded', 'insufficientquota'))):
            return 'quota_wait'
        if 401 in http_codes or any(code in encoded for code in ('unauthorized', 'authentication', 'authrequired')):
            return 'auth_required'
        # This CLI version sometimes emits only a typed error's message, no numeric code.
        message = error.get('message', '')
        if re.search(r'\b429\b|usage limit|rate limit|quota exceeded', message, re.I):
            return 'quota_wait'
        if re.search(r'\b401\b|authentication failed|not logged in', message, re.I):
            return 'auth_required'
    return 'internal_error'


def build_codex_command(phase, codex, root=ROOT, directory=None, model=None):
    requested, effort = LEVELS[phase['level']]
    directory = directory or root / '.scheduler' / 'preview'
    return [codex, 'exec', '--ignore-user-config', '--ephemeral', '--json',
            '--model', model or requested, '--config', 'model_reasoning_effort=' + effort,
            '--config', 'forced_login_method="chatgpt"', '--config', 'model_provider="openai"',
            '--config', 'approval_policy="never"', '--sandbox', 'workspace-write', '--cd', str(root),
            '--output-schema', str(directory / 'result.schema.json'),
            '--output-last-message', str(directory / 'result.json'), '-']


def safe_path(root, value):
    if not isinstance(value, str) or not value or Path(value).is_absolute() or '..' in Path(value).parts:
        raise ValueError('unsafe relative path: ' + str(value))
    path = root / value
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('symlink escapes root: ' + value)
    return path


def load_config(root=ROOT):
    # Project-local provider overrides and hooks must not bypass the isolated user config.
    if (root / '.codex/config.toml').exists():
        raise ValueError('project .codex/config.toml requires manual removal/review before unattended execution')
    config = read_json(root / 'scheduler.json', {})
    if not isinstance(config, dict):
        raise ValueError('scheduler config must be an object')
    phases = config.get('phases')
    if not isinstance(phases, list):
        raise ValueError('scheduler.json must contain a phases array')
    ids = set()
    for phase in phases:
        if not isinstance(phase, dict):
            raise ValueError('phase must be an object')
        ident = phase.get('id')
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', ident) or ident in ids:
            raise ValueError('invalid/duplicate phase id')
        ids.add(ident)
        if phase.get('level') not in LEVELS:
            raise ValueError('invalid phase level: ' + ident)
        if not safe_path(root, phase.get('prompt_file')).is_file():
            raise ValueError('missing prompt for ' + ident)
        tests = phase.get('tests')
        if not isinstance(tests, list) or not tests:
            raise ValueError('phase needs nonempty test argv: ' + ident)
        for test in tests:
            if not isinstance(test, list) or not test or not all(isinstance(x, str) and x for x in test):
                raise ValueError('invalid test argv: ' + ident)
        artifacts = phase.get('acceptance_artifacts')
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError('phase needs acceptance artifacts: ' + ident)
        for artifact in artifacts:
            safe_path(root, artifact)
        deps = phase.get('depends_on', [])
        if (not isinstance(deps, list) or not all(isinstance(x, str) for x in deps) or
                len(set(deps)) != len(deps)):
            raise ValueError('invalid dependencies')
        if phase.get('experiment_status_file'):
            safe_path(root, phase['experiment_status_file'])
    graph = {p['id']: p.get('depends_on', []) for p in phases}
    visiting, visited = set(), set()
    def visit(ident):
        if ident in visiting:
            raise ValueError('dependency cycle')
        if ident not in graph:
            raise ValueError('unknown dependency: ' + str(ident))
        if ident in visited:
            return
        visiting.add(ident)
        for dep in graph[ident]:
            visit(dep)
        visiting.remove(ident)
        visited.add(ident)
    for ident in graph:
        visit(ident)
    if not isinstance(config.get('policy', {}), dict):
        raise ValueError('policy must be an object')
    policy = POLICY | config.get('policy', {})
    for key, default in POLICY.items():
        value = policy[key]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError('invalid policy: ' + key)
        # A config cannot silently relax the documented cost/time ceilings.
        if value > default and key != 'retry_seconds':
            raise ValueError('policy exceeds authorized ceiling: ' + key)
    if int(policy['max_phases_per_round']) != policy['max_phases_per_round']:
        raise ValueError('phase count must be an integer')
    for key, forbidden in [('allow_paid_api', True), ('allow_auto_reset_credit', True), ('allow_auto_model_upgrade', True)]:
        if policy.get(key) == forbidden:
            raise ValueError('forbidden cost policy: ' + key)
    if policy.get('auth_mode', 'chatgpt_only') != 'chatgpt_only':
        raise ValueError('ChatGPT only')
    config['policy'] = policy
    return config


def gate_counts(output):
    # unittest/pytest summaries or a documented machine record for custom numerical gates.
    counts = None
    for line in output.splitlines():
        try:
            record = json.loads(line).get('scheduler_gate')
            if record is not None:
                counts = record
        except (ValueError, AttributeError):
            pass
    if counts is not None:
        if not isinstance(counts, dict) or any(type(counts.get(k)) is not int or counts[k] < 0
                                              for k in ('executed', 'passed', 'failed', 'skipped')):
            return None
        if counts['executed'] != counts['passed'] + counts['failed'] + counts['skipped']:
            return None
        return counts
    matches = re.findall(r'Ran (\d+) tests? in [\d.]+s', output)
    if matches:
        n = int(matches[-1])
        skipped = re.findall(r'skipped=(\d+)', output)
        failures = re.findall(r'(?:failures|errors)=(\d+)', output)
        fail = sum(map(int, failures))
        skip = int(skipped[-1]) if skipped else 0
        if not re.search(r'^OK(?:\s|$)', output, re.M):
            fail = max(1, fail)
        return dict(executed=n, passed=max(0, n - skip - fail), failed=fail, skipped=skip)
    passed = re.findall(r'(\d+) passed', output)
    if passed or re.search(r'\d+ skipped', output):
        def count(word):
            values = re.findall(r'(\d+) ' + word, output)
            return int(values[-1]) if values else 0
        p, f, s = count('passed'), count('failed') + count('error'), count('skipped')
        return dict(executed=p + f + s, passed=p, failed=f, skipped=s)
    return None


def parse_result(directory, process):
    if process['status']:
        raise Failure(process['status'], 'child did not finish within its bound')
    events = []
    try:
        for line in (directory / 'stdout.jsonl').read_text().splitlines():
            if line.strip():
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError('non-object event')
                events.append(event)
    except (ValueError, UnicodeError):
        raise Failure('partial', 'invalid JSONL stream')
    errors = [e for e in events if e.get('type') in {'error', 'turn.failed'}]
    if errors or process['exit_code'] != 0:
        raise Failure(classify_failure(errors), 'CLI failed; see typed events and stderr')
    completed = [e for e in events if e.get('type') == 'turn.completed']
    if not completed:
        raise Failure('partial', 'missing turn.completed')
    try:
        result = read_json(directory / 'result.json')
        if not isinstance(result, dict) or set(result) != set(RESULT_SCHEMA['required']):
            raise ValueError('result fields')
        for key in ('summary',):
            if not isinstance(result[key], str) or not result[key].strip():
                raise ValueError(key)
        for key in ('blockers', 'artifacts'):
            if not isinstance(result[key], list) or not all(isinstance(x, str) for x in result[key]):
                raise ValueError(key)
        if result['status'] not in RESULT_SCHEMA['properties']['status']['enum']:
            raise ValueError('status')
        if result['job_id'] is not None and not isinstance(result['job_id'], str):
            raise ValueError('job_id')
        if result['blocker_type'] not in ('hardware', 'input', None):
            raise ValueError('blocker_type')
    except (ValueError, TypeError):
        raise Failure('partial', 'invalid structured result')
    atomic_json(directory / 'session.json', dict(
        thread_ids=[e.get('thread_id') for e in events if e.get('type') == 'thread.started'],
        usage=[e.get('usage') for e in completed], exit_code=process['exit_code']))
    (directory / 'summary.md').write_text(result['summary'] + '\n')
    if result['status'] == 'blocked':
        raise Failure('blocked_' + (result['blocker_type'] or 'input'), result['summary'])
    if result['status'] == 'waiting_experiment':
        if not result['job_id']:
            raise Failure('partial', 'waiting_experiment needs job_id')
        raise Failure('waiting_experiment', result['job_id'])
    if result['status'] != 'completed' or result['blockers']:
        raise Failure('partial', result['summary'])
    return result


class Scheduler:
    def __init__(self, root):
        self.root = root.resolve()
        self.directory = self.root / '.scheduler'
        self.state_path = self.directory / 'state.json'
        self.journal_path = self.directory / 'journal.json'
        self.reload_state()

    def reload_state(self):
        self.state = read_json(self.state_path, {'completed': [], 'attempts': [], 'tasks': {}, 'completions': {}})
        if not isinstance(self.state, dict):
            raise ValueError('scheduler state must be an object')
        for key, value in [('tasks', {}), ('completions', {}), ('completed', []), ('attempts', [])]:
            self.state.setdefault(key, value)
            if not isinstance(self.state[key], type(value)):
                raise ValueError('invalid scheduler state field: ' + key)

    def git(self, *args, env=None):
        result = subprocess.run(['git', *args], cwd=self.root, text=True, capture_output=True,
                                env=env or chatgpt_environment(), timeout=60)
        if result.returncode:
            raise Failure('commit_failed', result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    def head(self):
        return self.git('rev-parse', 'HEAD')

    def save(self):
        atomic_json(self.state_path, self.state)

    def changed(self):
        data = subprocess.check_output(['git', 'status', '--porcelain=v1', '-z', '--untracked-files=all'], cwd=self.root)
        entries = data.decode().split('\0')
        paths = set()
        i = 0
        while i < len(entries) and entries[i]:
            entry = entries[i]
            path = entry[3:]
            if not path.startswith('.scheduler/'):
                paths.add(path)
            if 'R' in entry[:2] or 'C' in entry[:2]:
                i += 1
                paths.add(entries[i])
            i += 1
        return paths

    def manifest(self):
        result = {}
        for name in sorted(self.changed()):
            path = safe_path(self.root, name)
            if path.name.lower() in {'auth.json', 'credentials.json', 'token.json', 'tokens.json'}:
                raise Failure('blocked_input', 'credential file cannot enter scheduler commit: ' + name)
            if path.is_symlink() or (name != '.gitignore' and any(
                    part.startswith('.') for part in Path(name).parts)) or (
                path.suffix.lower() in {'.pem', '.key', '.step', '.stp', '.fcstd', '.mp4', '.zip', '.pt', '.pth'}):
                raise Failure('blocked_input', 'manual review required for non-source path: ' + name)
            if path.is_file() and path.stat().st_size > 5 * 1024 * 1024:
                raise Failure('blocked_input', 'large file requires manual review: ' + name)
            result[name] = file_hash(path)
        return result

    def verify_clean(self):
        staged = self.git('diff', '--cached', '--name-only')
        if staged:
            raise Failure('blocked_input', 'existing staged changes are protected')
        changed = self.changed()
        wip = self.state.get('wip')
        if wip and self.head() == wip['head'] and self.manifest() == wip['files']:
            return
        if changed:
            raise Failure('blocked_input', 'external/changed WIP files require review; nothing stashed/reset')
        if wip:
            raise Failure('blocked_input', 'WIP checkpoint no longer matches HEAD/files')

    def evidence_hash(self, directory):
        names = ['completion.json', 'gates.json', 'artifacts.json', 'result.json',
                 'request.json', 'session.json', 'stdout.jsonl']
        names += ['prompt.md', 'result.schema.json', 'preflight.json', 'stdout.jsonl.stderr']
        names += [p.name for p in directory.glob('test-*') if p.is_file()]
        return digest(json.dumps({name: file_hash(directory / name) for name in names}, sort_keys=True).encode())

    def park_wip(self, ident, run_id, base_head):
        """Preserve exact owned WIP, restore its baseline, permit independent phases.

        No reset/clean/stash and no commits. Initial user changes were rejected before
        starting the phase. Every modified byte is retained in the checkpoint.
        """
        files = self.manifest()
        if not files:
            self.state.pop('wip', None)
            return
        directory = self.directory / 'checkpoints' / run_id
        originals, modes = {}, {}
        for name, sha in files.items():
            target = safe_path(self.root, name)
            saved = directory / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            if sha is not None:
                shutil.copy2(target, saved)
                modes[name] = target.stat().st_mode & 0o777
            original = subprocess.run(['git', 'show', base_head + ':' + name], cwd=self.root, capture_output=True)
            originals[name] = digest(original.stdout) if original.returncode == 0 else None
        checkpoint = dict(files=files, originals=originals, modes=modes, base_head=base_head,
                          directory=str(directory.relative_to(self.root)))
        atomic_json(directory / 'checkpoint.json', checkpoint)
        if self.manifest() != files or self.head() != base_head or self.git('diff', '--cached', '--name-only'):
            raise Failure('blocked_input', 'files/index changed while preserving WIP; nothing restored')
        for name in files:
            target = safe_path(self.root, name)
            if originals[name] is None:
                target.unlink(missing_ok=True)
            else:
                original = subprocess.check_output(['git', 'show', base_head + ':' + name], cwd=self.root)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(original)
                mode = self.git('ls-tree', base_head, '--', name).split()[0]
                target.chmod(0o755 if mode == '100755' else 0o644)
        self.state.setdefault('checkpoints', {})[ident] = checkpoint
        self.state.pop('wip', None)
        self.save()

    def restore_checkpoint(self, ident):
        checkpoint = self.state.get('checkpoints', {}).get(ident)
        if not checkpoint:
            return
        for name, original in checkpoint['originals'].items():
            if file_hash(safe_path(self.root, name)) != original:
                raise Failure('blocked_input', 'checkpoint conflicts with later changes: ' + name)
        for name, sha in checkpoint['files'].items():
            if sha is not None and file_hash(self.root / checkpoint['directory'] / name) != sha:
                raise Failure('blocked_input', 'checkpoint bytes corrupted: ' + name)
        for name, sha in checkpoint['files'].items():
            target = safe_path(self.root, name)
            if sha is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.root / checkpoint['directory'] / name, target)
                target.chmod(checkpoint['modes'][name])
        self.state['wip'] = dict(head=self.head(), phase=ident, files=checkpoint['files'])
        del self.state['checkpoints'][ident]
        self.save()

    def verify_transaction(self, journal, commit):
        directory = self.root / journal['log']
        message = self.git('show', '-s', '--format=%B', commit)
        if 'Scheduler-Evidence: ' + self.evidence_hash(directory) not in message:
            raise Failure('internal_error', 'Git trailer/evidence hash mismatch')
        if not read_json(directory / 'gates.json', {}).get('passed'):
            raise Failure('internal_error', 'transaction has no successful gates')
        changed = subprocess.check_output(['git', 'diff-tree', '--no-commit-id', '--name-only', '-z',
                                           '-r', journal['base_head'], commit], cwd=self.root)
        if not set(changed.decode().rstrip('\0').split('\0') if changed else []).issubset(journal['files']):
            raise Failure('internal_error', 'commit contains paths outside the authorized manifest')
        for name, expected in journal['files'].items():
            proc = subprocess.run(['git', 'show', commit + ':' + name], cwd=self.root, capture_output=True)
            actual = digest(proc.stdout) if proc.returncode == 0 else None
            if actual != expected:
                raise Failure('internal_error', 'committed file differs from gated snapshot: ' + name)

    def completion_valid(self, ident, evidence):
        try:
            commit = evidence['commit']
            message = self.git('show', '-s', '--format=%B', commit)
            self.git('merge-base', '--is-ancestor', commit, 'HEAD')
            directory = self.root / evidence['log']
            manifest = read_json(directory / 'completion.json')
            if ('Scheduler-Run: ' + evidence['run_id'] not in message or not manifest or
                    manifest.get('phase') != ident or manifest.get('run_id') != evidence['run_id']):
                return False
            if not read_json(directory / 'gates.json', {}).get('passed'):
                return False
            self.verify_transaction(manifest, commit)
            return True
        except (Failure, KeyError, ValueError):
            return False

    def recover(self):
        journal = read_json(self.journal_path)
        if journal:
            ident, run_id = journal['phase'], journal['run_id']
            if journal['stage'] in {'prepared', 'commit_failed', 'committed'}:
                if self.head() != journal['base_head']:
                    message = self.git('show', '-s', '--format=%B', 'HEAD')
                    parent = self.git('rev-parse', 'HEAD^')
                    if parent != journal['base_head'] or 'Scheduler-Run: ' + run_id not in message:
                        raise Failure('blocked_input', 'HEAD diverged during Git transaction')
                    self.finish(journal, self.head())
                else:
                    if self.manifest() != journal['files']:
                        raise Failure('blocked_input', 'transaction files changed after gates')
                    self.commit(journal)
            elif journal['stage'] == 'running':
                directory = self.root / journal['log']
                for marker in directory.glob('*.started.json'):
                    recover_process(marker)
                files = self.manifest()
                self.state['wip'] = dict(head=journal['base_head'], phase=ident, files=files)
                self.record(ident, run_id, 'interrupted', 'recovering abandoned process', journal['log'])
                self.journal_path.unlink()
        for ident in self.state['completed']:
            if not self.completion_valid(ident, self.state['completions'].get(ident, {})):
                raise Failure('internal_error', 'completed state has no verifiable Git/evidence: ' + ident)

    def finish(self, journal, commit):
        self.verify_transaction(journal, commit)
        # A private transaction index protects user staging during commit. Synchronize
        # the ordinary index only if nobody changed it since the write-ahead record.
        index = Path(self.git('rev-parse', '--git-path', 'index'))
        if not index.is_absolute():
            index = self.root / index
        current_hash = file_hash(index)
        if current_hash != journal.get('index_sha256'):
            if self.git('diff', '--cached', '--name-only'):
                raise Failure('blocked_input', 'user index changed during transaction; commit retained for recovery')
        else:
            self.git('read-tree', commit)
        ident = journal['phase']
        evidence = dict(commit=commit, run_id=journal['run_id'], log=journal['log'])
        self.state['completions'][ident] = evidence
        if ident not in self.state['completed']:
            self.state['completed'].append(ident)
        self.state['head'] = commit
        self.state.pop('wip', None)
        self.record(ident, journal['run_id'], 'completed', 'gates and Git transaction complete', journal['log'])
        self.journal_path.unlink(missing_ok=True)

    def commit(self, journal):
        if self.head() != journal['base_head'] or self.manifest() != journal['files']:
            raise Failure('blocked_input', 'HEAD/files changed since gate')
        directory = self.root / journal['log']
        # Seal at gate completion, before the first commit attempt. Retrying Git
        # must not legitimize evidence modified while waiting for a ref lock or
        # recovering from a crash. Older pending journals require manual review;
        # already committed evidence remains verifiable through its Git trailer.
        evidence = journal.get('evidence_sha256')
        if not evidence:
            raise Failure('blocked_input', 'unsealed pending transaction requires manual review')
        if evidence != self.evidence_hash(directory):
            raise Failure('blocked_input', 'transaction evidence changed after gates; manual review required')
        index = directory / 'git.index'
        index.unlink(missing_ok=True)
        env = chatgpt_environment() | {'GIT_INDEX_FILE': str(index)}
        try:
            self.git('read-tree', 'HEAD', env=env)
            if journal['files']:
                self.git('add', '--', *journal['files'], env=env)
            message = ('Complete phase ' + journal['phase'] +
                     '\n\nScheduler-Run: ' + journal['run_id'] + '\nScheduler-Phase: ' + journal['phase'] +
                     '\nScheduler-Evidence: ' + evidence)
            # Declared phase gates are the validation boundary. Unreviewed local/global
            # hooks or signing helpers cannot mutate the private index during commit.
            process = run_process(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgSign=false',
                                   'commit', '--allow-empty', '-m', message], self.root,
                                  60, directory / 'git-commit.stdout', env=env)
            if process['status'] or process['exit_code']:
                raise Failure(process['status'] or 'commit_failed', 'Git commit failed; see git-commit.stdout/stderr')
            journal['stage'] = 'committed'
            atomic_json(self.journal_path, journal)
            self.finish(journal, self.head())
        except Failure:
            journal['stage'] = 'commit_failed'
            atomic_json(self.journal_path, journal)
            self.record(journal['phase'], journal['run_id'], 'commit_failed', 'Git failed; retry transaction without inference', journal['log'])
            raise
        finally:
            index.unlink(missing_ok=True)

    def record(self, ident, run_id, status, reason, log, **extra):
        entry = dict(phase=ident, run_id=run_id, finished=now(), result=status,
                     reason=reason, log=log, **extra)
        if self.state['attempts'] and self.state['attempts'][-1].get('run_id') == run_id:
            self.state['attempts'][-1].update(entry)
        else:
            self.state['attempts'].append(entry)
        task = dict(status=status, reason=reason, last_run=run_id)
        if status in {'quota_wait', 'auth_required', 'wait_model', 'partial', 'test_failed', 'timeout', 'interrupted', 'internal_error'}:
            task['next_eligible_time'] = time.time() + self.policy['retry_seconds']
        if status == 'waiting_experiment':
            task['job_id'] = reason
        self.state['tasks'][ident] = task
        if status in {'quota_wait', 'auth_required'}:
            self.state['external_next_eligible_time'] = time.time() + self.policy['retry_seconds']
        self.save()
        directory = self.root / log
        directory.mkdir(parents=True, exist_ok=True)
        atomic_json(directory / 'attempt.json', self.state['attempts'][-1])

    def eligible(self, config):
        completed = set(self.state['completed'])
        for phase in config['phases']:
            if phase['id'] in completed or not set(phase.get('depends_on', [])).issubset(completed):
                continue
            task = self.state['tasks'].get(phase['id'], {})
            if task.get('status') in {'blocked_hardware', 'blocked_input', 'waiting_experiment'}:
                # Deterministic job polling is explicit and never invokes a model.
                if task.get('status') == 'waiting_experiment' and phase.get('experiment_status_file'):
                    job = read_json(safe_path(self.root, phase['experiment_status_file']), {})
                    if job.get('job_id') == task.get('job_id') and job.get('status') == 'completed':
                        return phase
                continue
            if task.get('next_eligible_time', 0) > time.time():
                continue
            return phase
        return None

    def gates(self, phase, directory, deadline):
        gates = []
        for i, argv in enumerate(phase['tests']):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Failure('timeout', 'phase budget exhausted before gate')
            output = directory / ('test-%02d.stdout' % i)
            process = run_process(argv, self.root, min(self.policy['test_timeout_seconds'], remaining), output,
                                  env=chatgpt_environment())
            text = output.read_text(errors='replace') + '\n' + output.with_suffix(output.suffix + '.stderr').read_text(errors='replace')
            counts = gate_counts(text)
            passed = (not process['status'] and process['exit_code'] == 0 and counts is not None and
                      counts['passed'] > 0 and counts['failed'] == 0 and counts['executed'] > 0)
            gates.append(dict(**process, counts=counts, passed=passed))
            atomic_json(directory / 'gates.json', dict(passed=all(g['passed'] for g in gates), tests=gates))
            if not passed:
                raise Failure(process['status'] or 'test_failed', 'gate failed/empty/all-skip/unrecognized: ' + str(i))
        artifacts = {}
        for name in phase['acceptance_artifacts']:
            path = safe_path(self.root, name)
            if not path.is_file() or not path.read_text().strip():
                raise Failure('test_failed', 'missing/empty acceptance artifact: ' + name)
            if path.suffix == '.json':
                json.loads(path.read_text())
            artifacts[name] = file_hash(path)
        atomic_json(directory / 'artifacts.json', artifacts)

    def one(self, phase, config, codex, round_deadline):
        run_id = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + phase['id'] + '-' + uuid.uuid4().hex[:8]
        directory = self.directory / 'runs' / run_id
        directory.mkdir(parents=True)
        log = str(directory.relative_to(self.root))
        deadline = min(round_deadline, time.monotonic() + self.policy['phase_timeout_seconds'])
        base_head = self.head()
        journal = dict(stage='running', phase=phase['id'], run_id=run_id, base_head=base_head, log=log)
        index = Path(self.git('rev-parse', '--git-path', 'index'))
        journal['index_sha256'] = file_hash(index if index.is_absolute() else self.root / index)
        atomic_json(self.journal_path, journal)
        self.record(phase['id'], run_id, 'running', 'preflight', log, started=now())
        state_hash = file_hash(self.state_path)
        original_graph = config['phases']
        task_hashes = {p['prompt_file']: file_hash(self.root / p['prompt_file']) for p in config['phases']}
        task_hashes.update({name: file_hash(self.root / name)
                            for name in ('AGENTS.md', 'docs/REQUIREMENTS.md')})
        prompt = ('Work only on phase ' + phase['id'] + '. Read scheduler.json, AGENTS.md, PROGRESS.md and relevant design documents. '
                  'Implement and test the phase. Do not edit .scheduler/state.json or create Git commits. '
                  'Return the required structured result. Never declare future phases completed.\n\n' +
                  safe_path(self.root, phase['prompt_file']).read_text())
        previous = self.state.get('wip')
        if previous:
            prompt += '\nResume preserved WIP; inspect git diff first. Checkpoint:\n' + json.dumps(previous)
        (directory / 'prompt.md').write_text(prompt)
        atomic_json(directory / 'result.schema.json', RESULT_SCHEMA)
        request = dict(command=build_codex_command(phase, codex, self.root, directory),
                       requested_model=LEVELS[phase['level']][0], effort=LEVELS[phase['level']][1],
                       prompt_sha256=digest(prompt.encode()), config_sha256=file_hash(self.root / 'scheduler.json'),
                       base_head=base_head, started=now(), executed=False)
        atomic_json(directory / 'request.json', request)
        def verify_inputs():
            if file_hash(self.state_path) != state_hash:
                raise Failure('blocked_input', 'protected scheduler state changed; manual review required')
            if (load_config(self.root)['phases'] != original_graph or self.head() != base_head or any(
                    file_hash(self.root / name) != value for name, value in task_hashes.items())):
                raise Failure('blocked_input', 'protected phase graph/gates, task inputs or Git HEAD changed')

        try:
            with codex_home(self.root) as env:
                preflight_policy = self.policy | {'preflight_timeout_seconds': min(
                    self.policy['preflight_timeout_seconds'], max(0.01, deadline - time.monotonic()))}
                snapshot = preflight(codex, self.root, env, preflight_policy, directory)
                self.unknown_quota_used = snapshot['quota']['status'] == 'unknown'
                self.state['quota_snapshot'] = snapshot['quota'] | {'timestamp': snapshot['timestamp']}
                if quota_pause(snapshot, self.policy):
                    raise Failure('quota_wait', 'preflight usage threshold reached; no exec')
                model, effort = route(phase, snapshot)
                (directory / 'before.diff').write_text(self.git('diff', 'HEAD'))
                command = build_codex_command(phase, codex, self.root, directory, model)
                request.update(command=command, model=model, effort=effort, executed=True,
                               substitution=model != LEVELS[phase['level']][0])
                atomic_json(directory / 'request.json', request)
                process = run_process(command, self.root, max(0.01, deadline - time.monotonic()),
                                      directory / 'stdout.jsonl', env=env, input_text=prompt)
                verify_inputs()
                result = parse_result(directory, process)
                for artifact in result['artifacts']:
                    safe_path(self.root, artifact)
                self.gates(phase, directory, deadline)
                verify_inputs()
                files = self.manifest()
                journal.update(stage='prepared', files=files)
                atomic_json(directory / 'completion.json', journal)
                # Stored outside completion.json to avoid hashing the seal itself.
                journal['evidence_sha256'] = self.evidence_hash(directory)
                atomic_json(self.journal_path, journal)
                self.commit(journal)
                return 'completed'
        except (Failure, ValueError, OSError, subprocess.SubprocessError) as exc:
            status = exc.status if isinstance(exc, Failure) else 'internal_error'
            try:
                if journal['stage'] == 'running':
                    verify_inputs()
            except (Failure, ValueError, OSError):
                # Never park/restore protected edits or continue an independent phase
                # after a task/gate changed the plan or state. Preserve it for review.
                status = 'blocked_input'
                self.protected_input_changed = True
                atomic_json(directory / 'protected-input-change.json', {'manual_review_required': True})
            if STOP:
                status = 'interrupted'
            if journal.get('stage') == 'running':
                try:
                    self.state['wip'] = dict(head=base_head, phase=phase['id'], files=self.manifest())
                    (directory / 'wip.diff').write_text(self.git('diff', 'HEAD'))
                except (Failure, ValueError):
                    status = 'blocked_input'
                self.journal_path.unlink(missing_ok=True)
            self.record(phase['id'], run_id, status, str(exc), log)
            (directory / 'failure-summary.md').write_text(status + ': ' + str(exc) + '\n')
            return status

    def run(self, dry_run=False, codex_override=None):
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / 'run.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print('another run is active', file=sys.stderr)
                return 3
            # An instance can predate a competing run. Only the lock owner reads
            # authoritative state, including any commit completed while we waited.
            self.reload_state()
            config = load_config(self.root)
            self.policy = config['policy']
            if not dry_run:
                self.recover()
                if (self.state.get('external_next_eligible_time', 0) > time.time() and
                        len(self.state['completed']) < len(config['phases'])):
                    print('external preflight backoff active')
                    return 75
            phase = self.eligible(config)
            if phase is None:
                print(json.dumps(dict(status='no_op', completed=self.state['completed'],
                                      tasks=self.state['tasks'], final_release_path=self.state.get('final_release_path'))))
                return 0
            codex = codex_override or config.get('codex_bin') or shutil.which('codex')
            if dry_run:
                print(json.dumps(dict(phase=phase['id'], command=build_codex_command(phase, codex or 'codex', self.root),
                                      tests=phase['tests'])))
                return 0
            if self.state.get('external_next_eligible_time', 0) > time.time():
                print('external preflight backoff active')
                return 75
            self.verify_clean()
            if self.state.get('wip', {}).get('files') and self.state['wip']['phase'] != phase['id']:
                raise Failure('blocked_input', 'another phase has dirty WIP; review it before continuing')
            self.restore_checkpoint(phase['id'])
            if not codex:
                raise Failure('wait_model', 'codex executable unavailable')
            loaded_source = file_hash(self.root / 'scheduler.py')
            deadline = time.monotonic() + self.policy['round_timeout_seconds']
            for _ in range(int(self.policy['max_phases_per_round'])):
                if STOP or deadline - time.monotonic() < self.policy['phase_timeout_seconds']:
                    break
                result = self.one(phase, config, codex, deadline)
                print(json.dumps(self.state['attempts'][-1], ensure_ascii=False))
                if getattr(self, 'protected_input_changed', False):
                    return 1
                # A restored checkpoint may contain source edits before preflight.
                # Park unfinished edits so quota/auth waits and failed gates
                # leave a clean baseline. Commit failures retain their sealed
                # transaction and staged files for transaction recovery.
                if result not in {'completed', 'commit_failed'}:
                    self.park_wip(phase['id'], self.state['attempts'][-1]['run_id'], self.head())
                if result in {'blocked_hardware', 'blocked_input', 'waiting_experiment'}:
                    if getattr(self, 'unknown_quota_used', False):
                        return 1
                    config = load_config(self.root)
                    phase = self.eligible(config)
                    if phase and not STOP:
                        self.verify_clean()
                        self.restore_checkpoint(phase['id'])
                        continue
                if result != 'completed':
                    return 75 if result in {'quota_wait', 'auth_required', 'wait_model'} else 1
                if self.unknown_quota_used:
                    break
                # Self modifications are loaded by a fresh process on the next timer invocation.
                if file_hash(self.root / 'scheduler.py') != loaded_source:
                    break
                self.state = read_json(self.state_path)
                config = load_config(self.root)
                self.policy = config['policy']
                phase = self.eligible(config)
                if not phase:
                    break
                self.verify_clean()
                if self.state.get('wip', {}).get('files') and self.state['wip']['phase'] != phase['id']:
                    raise Failure('blocked_input', 'another phase has preserved dirty WIP; review/isolate it before continuing')
                self.restore_checkpoint(phase['id'])
            return 0

    def retry(self, ident):
        """Explicit operator retry after fixing input/auth/hardware; preserves evidence."""
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / 'run.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Failure('interrupted', 'cannot retry while another process owns the lock')
            self.reload_state()
            if ident not in self.state['tasks'] or ident in self.state['completed']:
                raise ValueError('retry requires an existing unfinished task')
            self.state['tasks'][ident]['status'] = 'retry_requested'
            self.state['tasks'][ident].pop('next_eligible_time', None)
            self.state.pop('external_next_eligible_time', None)
            self.state.setdefault('operator_actions', []).append(dict(action='retry', phase=ident, timestamp=now()))
            self.save()
        print(json.dumps(dict(status='retry_requested', phase=ident)))
        return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('validate')
    sub.add_parser('status')
    sub.add_parser('doctor')
    retry = sub.add_parser('retry')
    retry.add_argument('phase')
    run = sub.add_parser('run')
    run.add_argument('--dry-run', action='store_true')
    run.add_argument('--codex-bin')
    args = parser.parse_args()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop_handler)
    try:
        config = load_config(args.root)
        if args.command == 'validate':
            print(json.dumps(dict(valid=True, phases=len(config['phases']), scheduler_gate=dict(
                executed=len(config['phases']), passed=len(config['phases']), failed=0, skipped=0))))
            return 0
        if args.command == 'doctor':
            # Read-only w.r.t. repository/state; auth metadata contains no email/token.
            with tempfile.TemporaryDirectory(prefix='urdftools-doctor-') as tmp, codex_home(args.root) as env:
                result = preflight(config.get('codex_bin') or shutil.which('codex'), args.root,
                                   env, config['policy'], Path(tmp))
                print(json.dumps(result, ensure_ascii=False))
            return 0
        scheduler = Scheduler(args.root)
        if args.command == 'retry':
            return scheduler.retry(args.phase)
        if args.command == 'status':
            print(json.dumps(dict(completed=scheduler.state['completed'], tasks=scheduler.state['tasks'],
                                  next=(scheduler.eligible(config) or {}).get('id'),
                                  last_attempt=(scheduler.state['attempts'] or [None])[-1]), ensure_ascii=False, indent=2))
            return 0
        return scheduler.run(args.dry_run, args.codex_bin)
    except (Failure, ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps(dict(status=exc.status if isinstance(exc, Failure) else 'internal_error', reason=str(exc))), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
