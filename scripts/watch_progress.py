#!/usr/bin/env python3
"""Read-only terminal view of the URDFTools scheduler and its live Codex log."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.scheduler/state.json'
RUNS = ROOT / '.scheduler/runs'


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def timer_status():
    try:
        result = subprocess.run(
            ['systemctl', '--user', 'show', 'urdftools-dev.timer',
             '-p', 'ActiveState', '-p', 'UnitFileState', '-p', 'NextElapseUSecRealtime'],
            capture_output=True, text=True, timeout=3)
        if result.returncode:
            return 'systemd 查询失败: ' + result.stderr.strip()[:160]
        return ' | '.join(line for line in result.stdout.splitlines() if line)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 'systemd 查询失败: ' + str(exc)


def recent_events(log_dir):
    path = log_dir / 'stdout.jsonl'
    try:
        lines = path.read_text(errors='replace').splitlines()
    except OSError:
        return ['等待 CLI 事件…']
    events = []
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get('type')
        item = event.get('item') or {}
        if kind == 'item.completed' and item.get('type') == 'agent_message':
            events.append('模型: ' + str(item.get('text', '')).replace('\n', ' ')[:230])
        elif kind in {'item.started', 'item.completed'} and item.get('type') == 'command_execution':
            state = '执行' if kind == 'item.started' else '结束'
            exit_code = item.get('exit_code')
            suffix = '' if exit_code is None else ' [exit=' + str(exit_code) + ']'
            events.append(state + ': ' + str(item.get('command', '')).replace('\n', ' ')[:150] + suffix)
        elif kind in {'turn.completed', 'turn.failed'}:
            events.append('模型回合: ' + kind)
    return events[-10:] or ['CLI 已启动，等待事件…']


def render():
    state = read_json(STATE)
    completed = state.get('completed') or []
    attempts = state.get('attempts') or []
    latest = attempts[-1] if attempts else {}
    run_id = latest.get('run_id')
    log_dir = RUNS / run_id if run_id else None
    request = read_json(log_dir / 'request.json') if log_dir else {}
    phase = latest.get('phase')
    task = (state.get('tasks') or {}).get(phase, {})
    eligible_at = task.get('next_eligible_time')
    retry = (datetime.fromtimestamp(eligible_at).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
             if isinstance(eligible_at, (int, float)) else '当前可尝试')
    call_state = '已进入 exec' if request.get('executed') else '尚未进入 exec'
    now = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
    lines = [f'URDFTools 自动开发进度   {now}',
             '=' * 72,
             f'完成阶段: {len(completed)}/50  |  当前阶段: {latest.get("phase", "尚未启动")}',
             f'阶段状态: {latest.get("result", "等待")}  |  原因: {latest.get("reason", "")}',
             f'模型路由: {request.get("model", request.get("requested_model", "等待预检"))}  |  思考强度: {request.get("effort", "-")}  |  {call_state}',
             f'最早可重试: {retry}',
             'timer: ' + timer_status(),
             '运行日志: ' + (str(log_dir) if log_dir else '暂无'),
             '-' * 72]
    if log_dir:
        lines += recent_events(log_dir)
    lines += ['-' * 72, '此窗口每 3 秒读取真实状态和日志。Ctrl+C 仅关闭进度显示，不停止开发。']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    while True:
        print(('' if args.once else '\033[2J\033[H') + render(), flush=True)
        if args.once:
            break
        time.sleep(3)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
