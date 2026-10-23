"""Normalize scalar results from an already completed external import."""
from __future__ import annotations

import csv
import io
import json
import math
from pathlib import PurePosixPath

from .jobs import ImportFailure, ImportQueue, digest


class ResultCatalog:
    def __init__(self, queue: ImportQueue):
        self.queue = queue
        queue.db.executescript("""
        CREATE TABLE IF NOT EXISTS experiments(
          run_id TEXT PRIMARY KEY,job_id TEXT UNIQUE NOT NULL,robot_hash TEXT NOT NULL,
          algorithm TEXT NOT NULL,protocol TEXT NOT NULL,origin TEXT NOT NULL,
          schema_version INTEGER NOT NULL,source_schema_version INTEGER NOT NULL,
          source_sha TEXT NOT NULL,metadata_json TEXT NOT NULL,missing_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS scalar_metrics(
          run_id TEXT NOT NULL,metric TEXT NOT NULL,step INTEGER NOT NULL,value REAL NOT NULL,
          wall_time REAL,unit TEXT NOT NULL,source_sha TEXT NOT NULL,row_index INTEGER NOT NULL,
          PRIMARY KEY(run_id,source_sha,row_index));
        CREATE TABLE IF NOT EXISTS result_models(
          run_id TEXT PRIMARY KEY,model_id TEXT NOT NULL,model_sha TEXT NOT NULL,
          model_name TEXT NOT NULL,model_version TEXT NOT NULL,model_origin TEXT NOT NULL);
        """)

    def link_model(self, run_id: str, model_id: str, registry) -> dict:
        """Associate a completed external run with an exact pinned URDF asset."""
        row = self.queue.db.execute("SELECT robot_hash,metadata_json FROM experiments WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise ImportFailure("Unknown external run")
        model = registry.get(model_id)
        if row["robot_hash"] != model["sha256"] or json.loads(row["metadata_json"])["robot_category"] != model["category"]:
            raise ImportFailure("Robot hash or category does not match registry model")
        prior = self.queue.db.execute("SELECT model_id FROM result_models WHERE run_id=?", (run_id,)).fetchone()
        if prior is not None and prior["model_id"] != model_id:
            raise ImportFailure("Run already bound to another model")
        self.queue.db.execute("INSERT OR IGNORE INTO result_models VALUES(?,?,?,?,?,?)",
                              (run_id, model_id, model["sha256"], model["name"], model["version"], model["origin"]))
        return {"run_id": run_id, "model_id": model_id, "model_sha": model["sha256"],
                "model_name": model["name"], "model_version": model["version"], "origin": model["origin"],
                "reference_performance": False}

    @staticmethod
    def _rows(format_name: str, raw: bytes):
        if format_name == "csv":
            for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")):
                yield row
        elif format_name == "json":
            value = json.loads(raw)
            if not isinstance(value, list):
                raise ImportFailure("JSON metrics must be a list")
            yield from value
        elif format_name == "parquet":
            import pyarrow as pa
            import pyarrow.parquet as pq
            table = pq.read_table(pa.BufferReader(raw), columns=["metric", "step", "value", "wall_time"])
            yield from table.to_pylist()
        elif format_name == "tensorboard":
            import tempfile
            from pathlib import Path
            from tensorboard.backend.event_processing.event_file_loader import LegacyEventFileLoader
            # TensorBoard reader expects a path; private temporary file is removed after parsing.
            with tempfile.TemporaryDirectory(prefix="urdftools-events-") as folder:
                event_file = Path(folder) / "events.out.tfevents"
                event_file.write_bytes(raw)
                for event in LegacyEventFileLoader(str(event_file)).Load():
                    if event.HasField("summary"):
                        for scalar in event.summary.value:
                            if scalar.HasField("simple_value"):
                                yield {"metric": scalar.tag, "step": event.step,
                                       "value": scalar.simple_value, "wall_time": event.wall_time}
        else:
            raise ImportFailure("Unsupported metric format")

    def import_experiment(self, job_id: str) -> dict:
        job = self.queue.status(job_id)
        if job["status"] != "completed":
            raise ImportFailure("Import job must complete before result parsing")
        inventory = {item["path"]: item for item in json.loads(job["manifest"])["files"]}
        if "experiment.json" not in inventory:
            raise ImportFailure("Missing experiment.json")

        def asset(name):
            item = inventory.get(name)
            if item is None:
                raise ImportFailure("Metric file missing from immutable inventory")
            path = self.queue.blobs / item["sha256"][:2] / item["sha256"]
            if not path.is_file() or path.stat().st_size != item["size"] or digest(path) != item["sha256"]:
                raise ImportFailure("Raw asset hash mismatch")
            return path.read_bytes(), item["sha256"]

        raw_manifest, manifest_sha = asset("experiment.json")
        try:
            info = json.loads(raw_manifest)
        except (ValueError, UnicodeError) as exc:
            raise ImportFailure("Invalid experiment manifest") from exc
        if not isinstance(info, dict):
            raise ImportFailure("Invalid experiment manifest")
        source_schema_version = info.get("schema_version")
        if source_schema_version == 0:
            # Documented legacy fixture fields; raw v0 bytes remain in CAS.
            info = dict(info, schema_version=1, robot_hash=info.get("robot_sha256"),
                        algorithm=info.get("name"), protocol=info.get("task"))
        elif source_schema_version != 1:
            raise ImportFailure("Unsupported experiment schema")
        run_id = info.get("run_id")
        if not isinstance(run_id, str) or not run_id or len(run_id) > 160:
            raise ImportFailure("Invalid run ID")
        if info.get("robot_hash") != json.loads(job["manifest"])["robot_hash"]:
            raise ImportFailure("Robot hash disagrees with import job")
        if info.get("origin") not in {"user_upload", "public_import", "synthetic_fixture"}:
            raise ImportFailure("Unknown provenance")
        if info.get("robot_category") not in {"quadruped", "humanoid", "manipulator", "wheeled", "other"}:
            raise ImportFailure("Robot category required")
        for field in ("algorithm", "protocol"):
            if not isinstance(info.get(field), str) or not info[field].strip():
                raise ImportFailure(f"Missing {field}")
        optional_metadata = ("algorithm_version", "algorithm_commit", "protocol_version", "license", "engine")
        for field in optional_metadata:
            if info.get(field) is not None and (not isinstance(info[field], str) or not info[field].strip()):
                raise ImportFailure(f"Invalid {field}")
        missing = [field for field in optional_metadata if info.get(field) is None]
        metadata = {field: info.get(field) for field in optional_metadata}
        metadata["robot_category"] = info["robot_category"]
        specs = info.get("metrics")
        if not isinstance(specs, list) or not specs:
            raise ImportFailure("No metric files")
        rows = []
        for spec in specs:
            if not isinstance(spec, dict) or set(spec) != {"path", "format", "units"}:
                raise ImportFailure("Metric source requires path, format, units")
            name, format_name, units = spec["path"], spec["format"], spec["units"]
            if not isinstance(name, str) or name == "experiment.json" or name not in inventory:
                raise ImportFailure("Unknown metric source")
            if not isinstance(units, dict) or not units or any(not isinstance(k, str) or not isinstance(v, str) or not v for k, v in units.items()):
                raise ImportFailure("Explicit metric units required")
            raw, sha = asset(name)
            if len(raw) > 64 * 1024 * 1024:
                raise ImportFailure("Metric source exceeds 64 MiB reader limit")
            if format_name not in {"csv", "json", "parquet", "tensorboard"}:
                raise ImportFailure("Unsupported metric format; checkpoints are never deserialized")
            for n, row in enumerate(self._rows(format_name, raw)):
                if not isinstance(row, dict):
                    raise ImportFailure("Metric row must be an object")
                tag = row.get("metric")
                if not isinstance(tag, str) or tag not in units:
                    raise ImportFailure("Unknown metric or unit")
                step = row.get("step")
                if isinstance(step, str) and step.isdecimal():
                    step = int(step)
                if type(step) is not int or step < 0:
                    raise ImportFailure("Invalid step")
                try:
                    value = float(row["value"])
                    wall = row.get("wall_time")
                    wall = None if wall in (None, "") else float(wall)
                except (KeyError, TypeError, ValueError) as exc:
                    raise ImportFailure("Invalid scalar") from exc
                if not math.isfinite(value) or (wall is not None and not math.isfinite(wall)):
                    raise ImportFailure("Non-finite scalar or time")
                rows.append((run_id, tag, step, value, wall, units[tag], sha, n))
                if len(rows) > 2_000_000:
                    raise ImportFailure("Metric row limit exceeded")
        db = self.queue.db
        db.execute("BEGIN IMMEDIATE")
        try:
            existing = db.execute("SELECT job_id FROM experiments WHERE run_id=?", (run_id,)).fetchone()
            if existing:
                if existing["job_id"] != job_id:
                    raise ImportFailure("Run ID already belongs to another bundle")
                db.execute("ROLLBACK")
                return {"run_id": run_id, "rows": db.execute("SELECT count(*) FROM scalar_metrics WHERE run_id=?", (run_id,)).fetchone()[0], "status": "already_imported"}
            db.execute("INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (run_id, job_id, info["robot_hash"], info["algorithm"], info["protocol"], info["origin"],
                        1, source_schema_version, manifest_sha, json.dumps(metadata, sort_keys=True), json.dumps(missing)))
            db.executemany("INSERT INTO scalar_metrics VALUES(?,?,?,?,?,?,?,?)", rows)
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        return {"run_id": run_id, "rows": len(rows), "status": "imported", "missing_fields": missing}
