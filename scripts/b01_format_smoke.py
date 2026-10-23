#!/usr/bin/env python3
"""Generate and parse actual CSV, JSON, Parquet and TensorBoard scalar files."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
import pyarrow as pa
import pyarrow.parquet as pq
from tensorboard.compat.proto.event_pb2 import Event
from tensorboard.compat.proto.summary_pb2 import Summary
from tensorboard.summary.writer.event_file_writer import EventFileWriter
from urdftools.results.catalog import ResultCatalog
from urdftools.results.jobs import ImportFailure, ImportQueue


def put(source: Path, name: str, data: bytes):
    path = source / name
    path.write_bytes(data)
    return {"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    with tempfile.TemporaryDirectory(prefix="urdftools-b01-") as folder:
        root = Path(folder)
        with ImportQueue(root / "store") as queue:
            catalog = ResultCatalog(queue)
            formats = {}
            for format_name in ("csv", "json", "parquet", "tensorboard"):
                source = root / format_name
                source.mkdir()
                if format_name == "csv":
                    raw = b"metric,step,value,wall_time\nsuccess,12,0.75,123.25\n"
                    filename = "metrics.csv"
                elif format_name == "json":
                    raw = json.dumps([{"metric": "success", "step": 12, "value": 0.75, "wall_time": 123.25}]).encode()
                    filename = "metrics.json"
                elif format_name == "parquet":
                    buffer = io.BytesIO()
                    pq.write_table(pa.table({"metric": ["success"], "step": [12], "value": [0.75], "wall_time": [123.25]}), buffer)
                    raw = buffer.getvalue()
                    filename = "metrics.parquet"
                else:
                    event_dir = source / "events"
                    event_dir.mkdir()
                    writer = EventFileWriter(str(event_dir))
                    writer.add_event(Event(wall_time=123.25, step=12,
                                           summary=Summary(value=[Summary.Value(tag="success", simple_value=0.75)])))
                    writer.flush()
                    writer.close()
                    raw = next(event_dir.iterdir()).read_bytes()
                    filename = "events.tfevents"
                inventory = [put(source, filename, raw)]
                experiment = {"schema_version": 1, "run_id": f"run-{format_name}", "robot_hash": "a" * 64,
                              "robot_category": "quadruped", "origin": "synthetic_fixture", "algorithm": "external-test",
                              "algorithm_version": "1", "algorithm_commit": None, "protocol": "smoke-1",
                              "protocol_version": "1", "license": "CC0-1.0", "engine": "fixture",
                              "metrics": [{"path": filename, "format": format_name, "units": {"success": "ratio"}}]}
                inventory.append(put(source, "experiment.json", json.dumps(experiment).encode()))
                job = queue.enqueue(source, {"bundle_id": f"bundle-{format_name}", "robot_hash": "a" * 64, "files": inventory})
                assert queue.claim(format_name) == job
                while queue.step(job, format_name) != "completed":
                    pass
                result = catalog.import_experiment(job)
                assert result == {"run_id": f"run-{format_name}", "rows": 1, "status": "imported", "missing_fields": ["algorithm_commit"]}, result
                record = queue.db.execute("SELECT step,value,wall_time,unit FROM scalar_metrics WHERE run_id=?", (result["run_id"],)).fetchone()
                assert (record["step"], record["value"], record["wall_time"], record["unit"]) == (12, 0.75, 123.25, "ratio"), dict(record)
                assert catalog.import_experiment(job)["status"] == "already_imported"
                formats[format_name] = {"step": record["step"], "value": record["value"], "wall_time": record["wall_time"]}
            assert queue.db.execute("SELECT count(*) FROM experiments").fetchone()[0] == 4
            assert queue.db.execute("SELECT count(*) FROM scalar_metrics").fetchone()[0] == 4
            print(json.dumps({"status": "passed", "formats": formats, "runs": 4, "rows": 4}))


if __name__ == "__main__":
    main()
