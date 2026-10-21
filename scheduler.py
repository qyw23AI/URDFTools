#!/usr/bin/env python3
"""One bounded, resumable Codex development attempt per invocation."""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "scheduler.json"
STATE = ROOT / ".scheduler" / "state.json"
LOCK = ROOT / ".scheduler" / "run.lock"
LOG_DIR = ROOT / ".scheduler" / "runs"
LEVELS = {
    "ordinary": ("gpt-6.1-sol", "medium"),
    "complex": ("gpt-6.1-sol", "high"),
    "critical": ("gpt-6-astra", "high"),
    "critical_xhigh": ("gpt-6-astra", "xhigh"),
}
QUOTA_RE = re.compile(r"(rate.limit|usage.limit|quota|too.many.requests|429|credits?.exhausted)", re.I)
AUTH_RE = re.compile(r"(unauthorized|authentication|login.required|401)", re.I)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def atomic_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as out:
        json.dump(data, out, ensure_ascii=False, indent=2)
        out.write("\n")
        name = out.name
    os.replace(name, path)


def read_json(path: Path, default: object) -> object:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def run_command(argv: list[str], cwd: Path, timeout: int, output: Path | None = None) -> tuple[int, str]:
    try:
        completed = subprocess.run(argv, cwd=cwd, text=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, timeout=timeout, check=False)
        result = completed.stdout
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(result, encoding="utf-8")
        return completed.returncode, result
    except subprocess.TimeoutExpired as exc:
        result = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        if output:
            output.write_text(result + "\nTIMEOUT\n", encoding="utf-8")
        return 124, result + "\nTIMEOUT\n"


def load_config() -> dict:
    config = read_json(CONFIG, {})
    if not isinstance(config, dict) or not isinstance(config.get("phases"), list):
        raise ValueError("scheduler.json must contain a phases array")
    seen = set()
    for phase in config["phases"]:
        if not isinstance(phase, dict) or not isinstance(phase.get("id"), str) or not phase["id"]:
            raise ValueError("each phase needs a nonempty id")
        if phase["id"] in seen:
            raise ValueError("duplicate phase id: " + phase["id"])
        seen.add(phase["id"])
        if phase.get("level") not in LEVELS:
            raise ValueError("invalid level for " + phase["id"])
        prompt = phase.get("prompt_file")
        if not isinstance(prompt, str) or Path(prompt).is_absolute() or ".." in Path(prompt).parts:
            raise ValueError("unsafe prompt_file for " + phase["id"])
        if not isinstance(phase.get("tests", []), list):
            raise ValueError("tests must be a list")
    return config


def git(*args: str) -> tuple[int, str]:
    return run_command(["git", *args], ROOT, 60)


def build_codex_command(phase: dict, codex: str) -> list[str]:
    model, effort = LEVELS[phase["level"]]
    return [codex, "exec", "--json", "--model", model,
            "--config", f"model_reasoning_effort={effort}",
            "--sandbox", "workspace-write", "--approve-for-me", "--cd", str(ROOT), "-"]


def classify_failure(output: str) -> str:
    if QUOTA_RE.search(output):
        return "quota_wait"
    if AUTH_RE.search(output):
        return "auth_required"
    return "failed"


def status() -> int:
    config = load_config()
    state = read_json(STATE, {"completed": [], "attempts": []})
    completed = set(state.get("completed", []))
    print(json.dumps({"root": str(ROOT), "completed": sorted(completed),
                      "next": next((p["id"] for p in config["phases"] if p["id"] not in completed), None),
                      "last_attempt": (state.get("attempts") or [None])[-1]}, ensure_ascii=False, indent=2))
    return 0


def attempt(dry_run: bool = False, codex_override: str | None = None) -> int:
    config = load_config()
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("another run is active", file=sys.stderr)
            return 3
        state = read_json(STATE, {"completed": [], "attempts": []})
        phase = next((p for p in config["phases"] if p["id"] not in state.get("completed", [])), None)
        if phase is None:
            print("No pending phases. Add the architecture and phase plan to scheduler.json.")
            return 0
        prompt_path = ROOT / phase["prompt_file"]
        if not prompt_path.is_file():
            print(f"missing prompt: {prompt_path}", file=sys.stderr)
            return 2
        codex = codex_override or config.get("codex_bin") or shutil.which("codex")
        if not codex:
            print("codex CLI not found", file=sys.stderr)
            return 2
        command = build_codex_command(phase, codex)
        if dry_run:
            print(json.dumps({"phase": phase["id"], "command": command,
                              "tests": phase.get("tests", [])}, ensure_ascii=False, indent=2))
            return 0
        code, logged_in = run_command([codex, "login", "status"], ROOT, 30)
        if code != 0 or "Logged in" not in logged_in:
            print("Codex ChatGPT login is unavailable; no API-key fallback", file=sys.stderr)
            return 4
        start = now()
        run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + phase["id"]
        log = LOG_DIR / (run_id + ".jsonl")
        prompt = ("Work only on phase " + phase["id"] + ". Read scheduler.json and the project progress documents. "
                  "Implement this phase, run relevant checks, and summarize changes and remaining risks. "
                  "Do not change scheduler state or create git commits.\n\n" + prompt_path.read_text(encoding="utf-8"))
        try:
            completed = subprocess.run(command, cwd=ROOT, input=prompt, text=True,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       timeout=int(config.get("run_timeout_seconds", 14400)), check=False)
            output, code = completed.stdout, completed.returncode
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            output += "\nTIMEOUT\n"
            code = 124
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log.write_text(output, encoding="utf-8")
        result = "completed" if code == 0 else classify_failure(output)
        if code == 0:
            for test in phase.get("tests", []):
                if not isinstance(test, list) or not test or not all(isinstance(x, str) for x in test):
                    result = "invalid_test"
                    break
                test_code, test_output = run_command(test, ROOT, int(config.get("test_timeout_seconds", 1800)),
                                                     LOG_DIR / (run_id + ".test.log"))
                if test_code:
                    result = "test_failed"
                    break
        entry = {"phase": phase["id"], "started": start, "finished": now(),
                 "model": LEVELS[phase["level"]][0], "effort": LEVELS[phase["level"]][1],
                 "result": result, "exit_code": code, "log": str(log.relative_to(ROOT))}
        state.setdefault("attempts", []).append(entry)
        if result == "completed":
            state.setdefault("completed", []).append(phase["id"])
        atomic_json(STATE, state)
        if result == "completed":
            git("add", "-A")
            commit_code, commit_output = git("commit", "-m", "Complete phase " + phase["id"])
            if commit_code != 0:
                entry["result"] = "commit_failed"
                state["completed"].remove(phase["id"])
                atomic_json(STATE, state)
                print(commit_output, file=sys.stderr)
                return 5
        print(json.dumps(entry, ensure_ascii=False))
        return 0 if result == "completed" else (75 if result == "quota_wait" else 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    run = sub.add_parser("run")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--codex-bin")
    args = parser.parse_args()
    try:
        return status() if args.command == "status" else attempt(args.dry_run, args.codex_bin)
    except (ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
