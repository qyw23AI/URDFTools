#!/usr/bin/env python3
"""Q00 process-boundary cancellation, restart and permission-denial regression."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from accept_phase import ROOT
sys.path.insert(0, str(ROOT/"python"))


def main():
    archive = ROOT/"artifacts/C03/desktop/robot.zip"
    assert archive.is_file(), "Run Q00 STEP desktop export before recovery test"
    with tempfile.TemporaryDirectory(prefix="q00-resilience-", dir=ROOT/".tools") as folder:
        work = Path(folder)
        store = work/"imports"
        store.mkdir()
        env = dict(os.environ, PYTHONPATH=str(ROOT/"python"))
        cmd = [sys.executable, "-m", "urdftools.importers", str(store)]
        # Cancel a pending, incomplete IPC request; it must not publish any import.
        worker = subprocess.Popen(cmd, cwd=ROOT, env=env, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        assert worker.stdin is not None
        worker.stdin.write('{"action":"import","source":')
        worker.stdin.flush()
        worker.terminate()
        worker.communicate(timeout=10)
        assert not list(store.iterdir()), "Cancelled incomplete request left import state"
        # A different process must be able to import and subsequently select the
        # exact persisted operation; no in-memory service object is reused.
        def request(payload):
            done = subprocess.run(cmd, cwd=ROOT, env=env, input=json.dumps(payload),
                                  capture_output=True, text=True, timeout=40)
            assert done.returncode == 0, done.stderr
            return json.loads(done.stdout)
        created = request({"action": "import", "source": str(archive)})
        assert created["status"] == "ready" and created["selected_model"]
        restored = request({"action": "select", "operation_id": created["operation_id"],
                            "model": created["selected_model"]})
        assert restored["status"] == "ready"
        assert restored["operation_id"] == created["operation_id"]
        # An unreadable source is not silently accepted, and the source is restored.
        denied = work/"denied.urdf"
        denied.write_bytes(b'<robot name="private"><link name="root"/></robot>')
        denied.chmod(0)
        try:
            from urdftools.importers import ImportService
            refused = ImportService(work/"denials").ingest(denied)
            assert refused["status"] == "failed", refused
        finally:
            denied.chmod(0o600)
        result = {"status": "passed", "cancelled_incomplete_ipc_no_publish": True,
                  "process_restart_and_persisted_select": True,
                  "permission_denial_rejected": True,
                  "limitations": ["Cancellation checked before complete IPC request, not a mid-copy interrupt.",
                                  "No hardware or RL training is exercised."]}
        output = ROOT/"artifacts/Q00"
        output.mkdir(parents=True, exist_ok=True)
        (output/"resilience.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
