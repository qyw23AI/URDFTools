#!/usr/bin/env python3
"""Kill a real worker after a durable chunk, then resume without duplicate run."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from urdftools.results.jobs import ImportQueue

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="urdftools-b00-") as folder:
        root = Path(folder)
        source = root / "external-experiment"
        source.mkdir()
        sample = source / "metrics.csv"
        data = (b"step,success\n" + b"100,1\n" * 100000)
        sample.write_bytes(data)
        manifest = {"bundle_id": "external-test-1", "robot_hash": "a" * 64,
                    "files": [{"path": sample.name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}]}
        store = root / "database"
        with ImportQueue(store) as queue:
            job = queue.enqueue(source, manifest)
        command = [sys.executable, str(ROOT / "scripts/b00_worker.py"), str(store), "--owner", "first", "--chunk-size", "1000", "--pause-seconds", "0.1"]
        worker = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                with ImportQueue(store) as queue:
                    if queue.status(job)["offset"] >= 1000:
                        break
                time.sleep(0.02)
            else:
                raise RuntimeError("Worker did not write first checkpoint")
        finally:
            worker.kill()
            worker.communicate(timeout=5)
        with ImportQueue(store) as queue:
            checkpoint = queue.status(job)["offset"]
            assert checkpoint >= 1000 and queue.status(job)["status"] == "running"
            assert queue.db.execute("SELECT count(*) FROM runs").fetchone()[0] == 0
            queue.db.execute("UPDATE jobs SET lease_until=0 WHERE id=?", (job,))
        resumed = subprocess.run([sys.executable, str(ROOT / "scripts/b00_worker.py"), str(store), "--owner", "second", "--chunk-size", "65536"], capture_output=True, text=True, timeout=30)
        if resumed.returncode:
            raise RuntimeError(resumed.stdout + resumed.stderr)
        with ImportQueue(store) as queue:
            assert queue.status(job)["status"] == "completed"
            assert queue.db.execute("SELECT count(*) FROM runs").fetchone()[0] == 1
            assert queue.db.execute("SELECT count(*) FROM job_assets").fetchone()[0] == 1
            blob = queue.blobs / manifest["files"][0]["sha256"][:2] / manifest["files"][0]["sha256"]
            assert blob.read_bytes() == data
            assert queue.enqueue(source, manifest) == job
        print(json.dumps({"status": "passed", "killed_worker_checkpoint": checkpoint,
                          "resumed_status": "completed", "runs": 1, "assets": 1}))


if __name__ == "__main__":
    main()
