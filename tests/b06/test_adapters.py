import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from tensorboard.compat.proto.event_pb2 import Event
from tensorboard.compat.proto.summary_pb2 import Summary
from tensorboard.summary.writer.event_file_writer import EventFileWriter
from urdftools.results.adapters import adapt_log, export_unified_csv, export_mlflow_local, import_mlflow_local
from urdftools.results.catalog import ResultCatalog
from urdftools.results.jobs import ImportFailure, ImportQueue


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _import_to_b01(self, name, adapted):
        source = self.root / name
        source.mkdir()
        units = {r["metric"]: "score" for r in adapted["rows"]}
        info = {"schema_version": 1, "run_id": name, "robot_hash": "a"*64,
                "robot_category": "quadruped", "origin": "synthetic_fixture", "algorithm": "external-log",
                "protocol": "smoke", "metrics": [{"path": "normalized.csv", "format": "csv", "units": units}]}
        (source / "experiment.json").write_text(json.dumps(info))
        (source / "normalized.csv").write_bytes(export_unified_csv(adapted))
        inventory = [{"path": p.name, "size": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                     for p in sorted(source.iterdir())]
        with ImportQueue(self.root / "store") as queue:
            job = queue.enqueue(source, {"bundle_id": name, "robot_hash": "a"*64, "files": inventory})
            self.assertEqual(queue.claim(name), job)
            while queue.step(job, name) != "completed": pass
            report = ResultCatalog(queue).import_experiment(job)
            self.assertEqual(report["rows"], len(adapted["rows"]))
            return [tuple(row) for row in queue.db.execute("SELECT metric,step,value FROM scalar_metrics WHERE run_id=? ORDER BY row_index", (name,))]

    def test_sb3_csv_and_rsl_tensorboard_end_to_end(self):
        sb3 = b"time/total_timesteps,rollout/ep_rew_mean,rollout/ep_len_mean,train/custom\n100,2.5,12,99\n"
        adapted = adapt_log("sb3-csv-v1", sb3)
        self.assertEqual(adapted["unmapped_fields"], ["train/custom"])
        self.assertEqual(self._import_to_b01("sb3", adapted), [("episode_reward_mean", 100, 2.5), ("episode_length_mean", 100, 12.0)])
        logs = self.root / "events"
        logs.mkdir()
        isaac_logs = self.root / "isaac-events"
        isaac_logs.mkdir()
        writer = EventFileWriter(str(logs))
        writer.add_event(Event(wall_time=123.25, step=20,
                               summary=Summary(value=[Summary.Value(tag="Train/mean_reward", simple_value=3.5),
                                                      Summary.Value(tag="ignored/loss", simple_value=9)])))
        writer.flush(); writer.close()
        adapted = adapt_log("rsl-tensorboard-v1", next(logs.iterdir()).read_bytes())
        self.assertEqual(adapted["unmapped_fields"], ["ignored/loss"])
        self.assertEqual(self._import_to_b01("rsl", adapted), [("episode_reward_mean", 20, 3.5)])
        writer = EventFileWriter(str(isaac_logs))
        writer.add_event(Event(wall_time=124, step=21,
                               summary=Summary(value=[Summary.Value(tag="Metrics/success_rate", simple_value=0.5)])))
        writer.flush(); writer.close()
        isaac = adapt_log("isaaclab-tensorboard-v1", next(isaac_logs.iterdir()).read_bytes())
        self.assertEqual(self._import_to_b01("isaac", isaac), [("success_rate", 21, 0.5)])

    def test_mlflow_local_roundtrip_and_unsupported_version(self):
        rows = [{"metric": "reward", "step": 2, "value": 0.75, "wall_time": 123.25}]
        export_mlflow_local(rows, self.root / "mlruns")
        self.assertEqual(import_mlflow_local(self.root / "mlruns")["rows"], rows)
        with self.assertRaises(ImportFailure):
            adapt_log("sb3-csv-v0", b"x")
        with self.assertRaises(ImportFailure):
            import_mlflow_local(self.root / "mlruns", version="future")
        with self.assertRaises(ImportFailure):
            export_mlflow_local([dict(rows[0], metric="../escape")], self.root / "bad")


if __name__ == "__main__":
    unittest.main()
