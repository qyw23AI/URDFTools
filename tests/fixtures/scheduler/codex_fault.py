#!/usr/bin/env python3
"""Deterministic protocol peer for fault injection ONLY; never a real model result."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

root = Path.cwd()
fault = json.loads((root / 'fault.json').read_text()) if (root / 'fault.json').exists() else {}
if any(k in os.environ for k in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'ANTHROPIC_API_KEY', 'OPENAI_BASE_URL')):
    raise SystemExit('credential leaked')
with (root / 'calls.log').open('a') as out:
    out.write(sys.argv[1] + '\n')
if sys.argv[1] == 'app-server':
    for line in sys.stdin:
        request = json.loads(line)
        method = request['method']
        if method == 'initialized':
            continue
        if method in fault.get('rpc_errors', {}):
            print(json.dumps({'id': request['id'], 'error': fault['rpc_errors'][method]}), flush=True)
            continue
        if method == 'initialize':
            result = {'userAgent': 'fault-peer/1'}
        elif method == 'account/read':
            result = {'account': {'type': fault.get('auth', 'chatgpt'), 'planType': 'test'}}
        elif method == 'model/list':
            result = {'data': [dict(id=m, model=m, supportedReasoningEfforts=[{'reasoningEffort': e}
                      for e in ['low', 'medium', 'high', 'xhigh']]) for m in fault.get('models',
                      ['gpt-6.1-sol', 'gpt-6-sol', 'gpt-6-astra'])], 'nextCursor': None}
        elif method == 'account/rateLimits/read':
            if fault.get('quota_unknown'):
                print(json.dumps({'id': request['id'], 'error': {'code': -32601}}), flush=True)
                continue
            result = {'rateLimits': {'primary': {'usedPercent': fault.get('primary', 3),
                      'windowDurationMins': 300, 'resetsAt': 9999999999},
                      'secondary': {'usedPercent': fault.get('secondary', 2)}},
                      'rateLimitsByLimitId': fault.get('buckets')}
        else:
            raise SystemExit('unexpected RPC: ' + method)
        print(json.dumps({'id': request['id'], 'result': result}), flush=True)
    raise SystemExit(0)

prompt = sys.stdin.read()
for ident, settings in fault.get('by_phase', {}).items():
    if ('Work only on phase ' + ident + '.') in prompt:
        fault.update(settings)
(root / 'exec.argv.json').write_text(json.dumps(sys.argv))
if fault.get('sleep'):
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
    (root / 'child.pid').write_text(str(child.pid))
    (root / 'leader.pid').write_text(str(os.getpid()))
    if fault.get('ignore_term'):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(120)
if fault.get('error'):
    print(json.dumps({'type': 'turn.failed', 'error': fault['error']}))
    raise SystemExit(fault.get('exit', 0))
(root / 'feature.py').write_text('def squares(n):\n    return sum(i * i for i in range(n + 1))\n')
(root / 'acceptance.md').write_text('Fault fixture: arithmetic gate verifies sum of squares 1..10 = 385.\n')
if fault.get('edit_scheduler'):
    (root / 'scheduler.py').write_text((root / 'scheduler.py').read_text() + '\n# loaded next process\n')
if fault.get('graph_change'):
    config = json.loads((root / 'scheduler.json').read_text())
    config['phases'][0]['tests'] = [[sys.executable, '-c', 'pass']]
    (root / 'scheduler.json').write_text(json.dumps(config))
if fault.get('invalid_stream'):
    print('not JSON')
else:
    print(json.dumps({'type': 'thread.started', 'thread_id': 'fault-thread'}))
    print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '429 quota example is harmless'}}))
    if not fault.get('no_turn'):
        print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 1, 'output_tokens': 1}}))
result = {'status': fault.get('result', 'completed'), 'summary': 'fault fixture result',
          'blockers': fault.get('blockers', []), 'artifacts': ['acceptance.md'],
          'job_id': fault.get('job_id'), 'blocker_type': fault.get('blocker_type')}
output = Path(sys.argv[sys.argv.index('--output-last-message') + 1])
output.write_text('invalid' if fault.get('invalid_result') else json.dumps(result))
raise SystemExit(fault.get('exit', 0))
