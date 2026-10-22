#!/usr/bin/env python3
"""Bounded multi-stage acceptance launcher; unknown phases never pass implicitly."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run_stage(command, cwd=ROOT, timeout=300, env=None):
    """Bound a whole stage, including servers launched by its tests."""
    with subprocess.Popen(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, start_new_session=True, env=env) as process:
        try:
            output, _ = process.communicate(timeout=timeout)
            return process.returncode, output
        except subprocess.TimeoutExpired:
            # Kill the group even if its parent exited while a descendant held stdout.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            output, _ = process.communicate()
            return 2, output + f"\nStage timed out after {timeout} seconds; process group terminated.\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase")
    args = parser.parse_args()
    phases = json.loads((ROOT / "scripts/acceptance_manifest.json").read_text())["phases"]
    if args.phase not in phases:
        print(f"No implemented acceptance suite registered for {args.phase}", file=sys.stderr)
        return 2
    output = ROOT / "artifacts/acceptance"
    output.mkdir(parents=True, exist_ok=True)
    # Preserve earlier failures, rather than overwriting the only evidence.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    evidence = ROOT / "artifacts" / args.phase / "runs" / stamp
    evidence.mkdir(parents=True)
    python = ROOT / ".venv/bin/python"
    stages = []
    for stage in phases[args.phase]:
        counts = evidence / (stage["id"] + ".json")
        if stage["kind"] == "unittest":
            command = [str(python), "scripts/run_test_suite.py", "--directory", stage["directory"], "--report", str(counts)]
        else:
            command = [s.replace("{python}", str(python)) for s in stage["argv"]]
        try:
            code, log = run_stage(command, timeout=stage.get('timeout_seconds', 300))
        except (OSError, subprocess.TimeoutExpired) as exc:
            code, log = 2, str(exc)
        log_path = evidence / (stage["id"] + ".log")
        log_path.write_text(log)
        record = {"id": stage["id"], "command": command, "exit_code": code,
                  "log": str(log_path.relative_to(ROOT)), "log_sha256": hashlib.sha256(log.encode()).hexdigest()}
        if stage["kind"] == "unittest":
            record["counts"] = json.loads(counts.read_text()) if counts.exists() else {}
            code = code or (0 if record["counts"].get("status") == "passed" else 1)
        record["exit_code"] = code
        record["status"] = "passed" if code == 0 else "failed"
        stages.append(record)
        print(f"{stage['id']}: {record['status']}", flush=True)
        print(log, end="", flush=True)
    report = {"phase": args.phase, "timestamp": stamp, "status": "passed" if stages and all(s["status"] == "passed" for s in stages) else "failed", "checks": stages}
    encoded = json.dumps(report, indent=2) + "\n"
    (evidence / "report.json").write_text(encoded)
    (output / (args.phase + ".json")).write_text(encoded)
    # Scheduler's console count parser must see a failing summary if any stage fails.
    passed = sum(s["status"] == "passed" for s in stages)
    print(f"{passed} passed, {len(stages)-passed} failed, 0 skipped")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
