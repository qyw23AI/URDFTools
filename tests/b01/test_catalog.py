import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from urdftools.results.catalog import ResultCatalog
from urdftools.results.jobs import ImportFailure, ImportQueue


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def imported(self, bundle="b1", run="r1", raw=b"metric,step,value,wall_time\nsuccess,2,0.5,10\n", units=None, version=1, format_name="csv"):
        source = self.root / bundle
        source.mkdir()
        (source / "metrics.csv").write_bytes(raw)
        info = {"schema_version": version, "run_id": run, "origin": "synthetic_fixture", "robot_category": "quadruped",
                "license": "CC0-1.0", "engine": "fixture", "algorithm_version": "1", "algorithm_commit": None,
                "protocol_version": "1",
                "metrics": [{"path": "metrics.csv", "format": format_name, "units": units if units is not None else {"success": "ratio"}}]}
        if version == 0:
            info.update(robot_sha256="a" * 64, name="algo", task="task")
        else:
            info.update(robot_hash="a" * 64, algorithm="algo", protocol="task")
        (source / "experiment.json").write_text(json.dumps(info))
        files = [{"path": p.name, "size": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                 for p in sorted(source.iterdir())]
        with ImportQueue(self.root / "store") as queue:
            job = queue.enqueue(source, {"bundle_id": bundle, "robot_hash": "a" * 64, "files": files})
            self.assertEqual(queue.claim("worker"), job)
            while queue.step(job, "worker") != "completed":
                pass
        return job

    def test_legacy_schema_preserves_raw(self):
        job = self.imported(version=0)
        with ImportQueue(self.root / "store") as queue:
            self.assertEqual(ResultCatalog(queue).import_experiment(job)["rows"], 1)
            record = queue.db.execute("SELECT schema_version,source_schema_version,algorithm,protocol FROM experiments").fetchone()
            self.assertEqual(tuple(record), (1, 0, "algo", "task"))
            sha = queue.db.execute("SELECT sha FROM job_assets WHERE path='experiment.json'").fetchone()[0]
            self.assertEqual(json.loads((queue.blobs / sha[:2] / sha).read_text())["schema_version"], 0)

    def test_invalid_rows_and_asset_rollback(self):
        bad = self.imported(raw=b"metric,step,value,wall_time\nsuccess,2,NaN,10\n")
        with ImportQueue(self.root / "store") as queue:
            catalog = ResultCatalog(queue)
            with self.assertRaises(ImportFailure):
                catalog.import_experiment(bad)
            self.assertEqual(queue.db.execute("SELECT count(*) FROM experiments").fetchone()[0], 0)
        missing = self.imported(bundle="b2", run="r2", units={"other": "ratio"})
        with ImportQueue(self.root / "store") as queue:
            catalog = ResultCatalog(queue)
            with self.assertRaises(ImportFailure):
                catalog.import_experiment(missing)
            sha = queue.db.execute("SELECT sha FROM job_assets WHERE job_id=? AND path='metrics.csv'", (missing,)).fetchone()[0]
            (queue.blobs / sha[:2] / sha).write_bytes(b"tampered")
            with self.assertRaises(ImportFailure):
                catalog.import_experiment(missing)
            self.assertEqual(queue.db.execute("SELECT count(*) FROM scalar_metrics").fetchone()[0], 0)

    def test_duplicate_run_across_bundles(self):
        first = self.imported()
        second = self.imported(bundle="b2")
        with ImportQueue(self.root / "store") as queue:
            catalog = ResultCatalog(queue)
            self.assertEqual(catalog.import_experiment(first)["status"], "imported")
            with self.assertRaises(ImportFailure):
                catalog.import_experiment(second)
            self.assertEqual(queue.db.execute("SELECT count(*) FROM experiments").fetchone()[0], 1)

    def test_checkpoint_format_never_deserialized_and_missing_context_recorded(self):
        job = self.imported(format_name="pickle")
        with ImportQueue(self.root / "store") as queue:
            with self.assertRaises(ImportFailure):
                ResultCatalog(queue).import_experiment(job)
        other = self.imported(bundle="b2", run="r2")
        with ImportQueue(self.root / "store") as queue:
            result = ResultCatalog(queue).import_experiment(other)
            self.assertEqual(result["missing_fields"], ["algorithm_commit"])
            missing = json.loads(queue.db.execute("SELECT missing_json FROM experiments WHERE run_id='r2'").fetchone()[0])
            self.assertEqual(missing, ["algorithm_commit"])


if __name__ == "__main__":
    unittest.main()
