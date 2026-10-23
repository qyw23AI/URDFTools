import hashlib
import os
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))

from urdftools.results.jobs import ImportFailure, ImportQueue, digest


class ImportJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.source = root / "source"
        self.source.mkdir()
        (self.source / "metric.csv").write_bytes(b"step,reward\n1,2\n")
        self.data = b"ab12" * 1024
        (self.source / "video.bin").write_bytes(self.data)
        self.manifest = {"bundle_id": "trial-1", "robot_hash": "a" * 64,
                         "files": [{"path": p.name, "size": p.stat().st_size, "sha256": digest(p)}
                                   for p in sorted(self.source.iterdir())]}
        self.store = root / "store"

    def test_crash_resume_and_no_duplicate_run(self):
        with ImportQueue(self.store) as queue:
            job = queue.enqueue(self.source, self.manifest)
            self.assertEqual(queue.enqueue(self.source, self.manifest), job)
            self.assertEqual(queue.claim("worker-a", 0.05), job)
            queue.step(job, "worker-a", 10)
            self.assertGreater(queue.status(job)["offset"], 0)
            self.assertIsNone(queue.claim("worker-b"))
            queue.db.execute("UPDATE jobs SET lease_until=0 WHERE id=?", (job,))
        with ImportQueue(self.store) as queue:
            self.assertEqual(queue.claim("worker-b"), job)
            while queue.step(job, "worker-b", 127) != "completed":
                pass
            self.assertEqual(queue.status(job)["status"], "completed")
            self.assertEqual(queue.db.execute("SELECT count(*) FROM runs").fetchone()[0], 1)
            self.assertEqual(queue.db.execute("SELECT count(*) FROM job_assets").fetchone()[0], 2)
            self.assertEqual(queue.blobs.joinpath(digest(self.source / "video.bin")[:2], digest(self.source / "video.bin")).read_bytes(), self.data)
            self.assertIsNone(queue.claim("worker-c"))

    def test_robot_identity_conflict_and_path_rejection(self):
        with ImportQueue(self.store) as queue:
            queue.enqueue(self.source, self.manifest)
            changed = dict(self.manifest, robot_hash="b" * 64)
            with self.assertRaises(ImportFailure):
                queue.enqueue(self.source, changed)
            bad = dict(self.manifest, bundle_id="escape", files=[dict(self.manifest["files"][0], path="../escape")])
            with self.assertRaises(ImportFailure):
                queue.enqueue(self.source, bad)
            link = self.source / "linked.csv"
            link.symlink_to(self.source / "metric.csv")
            linked = dict(self.manifest, bundle_id="link", files=[dict(self.manifest["files"][0], path=link.name)])
            with self.assertRaises(ImportFailure):
                queue.enqueue(self.source, linked)

    def test_bad_file_never_publishes_run_and_cancellation(self):
        with ImportQueue(self.store) as queue:
            job = queue.enqueue(self.source, self.manifest)
            self.assertEqual(queue.claim("worker"), job)
            (self.source / "video.bin").write_bytes(b"changed")
            with self.assertRaises(ImportFailure):
                while queue.step(job, "worker", 100) != "completed":
                    pass
            self.assertEqual(queue.db.execute("SELECT count(*) FROM runs").fetchone()[0], 0)
            queue.cancel(job)
            self.assertEqual(queue.status(job)["status"], "cancelled")
            self.assertIsNone(queue.claim("other"))


if __name__ == "__main__":
    unittest.main()
