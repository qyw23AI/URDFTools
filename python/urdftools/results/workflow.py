"""Persist and compare externally produced protocol, seed and video evidence."""
from __future__ import annotations

import json
from pathlib import PurePosixPath

from .compare import compare_success
from .jobs import ImportFailure, ImportQueue, digest
from .media import inspect_video, locate_metric_event


class ResultWorkflow:
    def __init__(self, queue: ImportQueue):
        self.queue = queue
        queue.db.execute("""CREATE TABLE IF NOT EXISTS result_evidence(
          run_id TEXT PRIMARY KEY, source_sha TEXT NOT NULL,
          protocol_json TEXT NOT NULL, seed_runs_json TEXT NOT NULL,
          media_json TEXT NOT NULL)""")

    def ingest(self, run_id: str, job_id: str) -> dict:
        job = self.queue.status(job_id)
        if job["status"] != "completed":
            raise ImportFailure("Completed import required")
        asset_rows = self.queue.db.execute("SELECT path,sha FROM job_assets WHERE job_id=?", (job_id,)).fetchall()
        assets = {row["path"]: row["sha"] for row in asset_rows}
        if "evidence.json" not in assets:
            raise ImportFailure("evidence.json required for protocol and media comparison")
        def blob(name: str):
            if not isinstance(name, str) or PurePosixPath(name).is_absolute() or name not in assets:
                raise ImportFailure("Unlisted evidence asset")
            sha = assets[name]
            path = self.queue.blobs / sha[:2] / sha
            if not path.is_file() or digest(path) != sha:
                raise ImportFailure("Evidence asset SHA mismatch")
            return path, sha
        source, source_sha = blob("evidence.json")
        if source.stat().st_size > 1024 * 1024:
            raise ImportFailure("Evidence description too large")
        evidence = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(evidence, dict) or set(evidence) != {"schema_version", "protocol", "seed_runs", "videos"} or evidence["schema_version"] != 1:
            raise ImportFailure("Invalid evidence schema")
        protocol = evidence["protocol"]
        if not isinstance(protocol, dict):
            raise ImportFailure("Comparison protocol required")
        row = self.queue.db.execute("SELECT metadata_json,job_id FROM experiments WHERE run_id=?", (run_id,)).fetchone()
        if row is None or row["job_id"] != job_id:
            raise ImportFailure("Run not bound to this import job")
        info = json.loads(row["metadata_json"])
        if protocol.get("robot_category") != info["robot_category"]:
            raise ImportFailure("Protocol category differs from imported robot")
        if not isinstance(evidence["seed_runs"], list) or not evidence["seed_runs"]:
            raise ImportFailure("Independent seed outcomes required")
        # The comparison engine validates protocol and seed outcomes; self-compare has no ranking side effect.
        compare_success(protocol, protocol, evidence["seed_runs"], evidence["seed_runs"])
        videos = evidence["videos"]
        if not isinstance(videos, list) or len(videos) > 32:
            raise ImportFailure("Bounded video list required")
        media = []
        for item in videos:
            if not isinstance(item, dict) or set(item) != {"path", "episode_id", "camera", "experiment_offset_s", "declared_fps", "events"}:
                raise ImportFailure("Invalid video descriptor")
            path, sha = blob(item["path"])
            report = inspect_video(path, episode_id=item["episode_id"], camera=item["camera"],
                                   experiment_offset_s=item["experiment_offset_s"], declared_fps=item["declared_fps"])
            if not isinstance(item["events"], list) or len(item["events"]) > 10000:
                raise ImportFailure("Invalid video events")
            events = [locate_metric_event(report, **event) for event in item["events"]]
            media.append({"path": item["path"], "source_sha256": sha, "video": report, "events": events})
        db = self.queue.db
        db.execute("BEGIN IMMEDIATE")
        try:
            existing = db.execute("SELECT source_sha FROM result_evidence WHERE run_id=?", (run_id,)).fetchone()
            if existing and existing["source_sha"] != source_sha:
                raise ImportFailure("Run evidence changed after import")
            db.execute("INSERT OR IGNORE INTO result_evidence VALUES(?,?,?,?,?)",
                       (run_id, source_sha, json.dumps(protocol, sort_keys=True),
                        json.dumps(evidence["seed_runs"], sort_keys=True), json.dumps(media, sort_keys=True)))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        return {"run_id": run_id, "source_sha256": source_sha, "videos": len(media)}

    def detail(self, run_id: str) -> dict:
        row = self.queue.db.execute("SELECT * FROM result_evidence WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise ImportFailure("Run has no indexed evidence")
        return {"run_id": run_id, "source_sha256": row["source_sha"],
                "protocol": json.loads(row["protocol_json"]), "seed_runs": json.loads(row["seed_runs_json"]),
                "media": json.loads(row["media_json"])}

    def compare(self, reference_id: str, candidate_id: str) -> dict:
        if reference_id == candidate_id:
            raise ImportFailure("Choose different reference and candidate runs")
        reference = self.detail(reference_id)
        candidate = self.detail(candidate_id)
        result = compare_success(reference["protocol"], candidate["protocol"],
                                 reference["seed_runs"], candidate["seed_runs"])
        origins = self.queue.db.execute("SELECT run_id,origin FROM experiments WHERE run_id IN (?,?)",
                                        (reference_id, candidate_id)).fetchall()
        by_id = {row["run_id"]: row["origin"] for row in origins}
        return {"reference_run_id": reference_id, "candidate_run_id": candidate_id,
                "reference_origin": by_id[reference_id], "candidate_origin": by_id[candidate_id],
                "fixture_only": any(origin == "synthetic_fixture" for origin in by_id.values()),
                "comparison": result, "reference_media": reference["media"], "candidate_media": candidate["media"]}
