#!/usr/bin/env python3
"""Local desktop bridge for immutable external result bundles; never runs training."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from urdftools.reference.registry import ModelRegistry
from urdftools.results.catalog import ResultCatalog
from urdftools.results.jobs import ImportFailure, ImportQueue, digest
from urdftools.results.workflow import ResultWorkflow
from urdftools.results.native_run import prepare_native


def inventory(source: Path, manifest: dict) -> dict:
    if not isinstance(manifest, dict) or set(manifest) != {"bundle_id", "robot_hash", "files", "model"}:
        raise ImportFailure("Bundle manifest requires bundle_id, robot_hash, files and model")
    model = manifest["model"]
    if not isinstance(model, dict) or set(model) != {"path", "name", "version", "category", "origin", "license"}:
        raise ImportFailure("Model provenance fields are incomplete")
    name = model["path"]
    files = manifest["files"]
    if not isinstance(name, str) or not isinstance(files, list):
        raise ImportFailure("Invalid model path or file inventory")
    listed = {item.get("path"): item for item in files if isinstance(item, dict)}
    if name not in listed or "experiment.json" not in listed or "evidence.json" not in listed:
        raise ImportFailure("Model, experiment.json and evidence.json must be listed in bundle inventory")
    if not name.endswith(".urdf"):
        raise ImportFailure("Model asset must be URDF")
    for field in ("name", "version", "category", "origin"):
        if not isinstance(model[field], str) or not model[field].strip():
            raise ImportFailure(f"Missing model {field}")
    if model["origin"] == "public_import" and (not isinstance(model["license"], str) or not model["license"].strip()):
        raise ImportFailure("Public model requires explicit license")
    # Enqueue performs path/symlink/size checks; verify source bytes before registry write.
    asset = source / name
    if asset.is_symlink() or not asset.is_file() or not asset.resolve().is_relative_to(source):
        raise ImportFailure("Unsafe model path")
    if asset.stat().st_size != listed[name].get("size") or digest(asset) != listed[name].get("sha256") or digest(asset) != manifest["robot_hash"]:
        raise ImportFailure("Model bytes disagree with signed inventory or robot identity")
    return model


def import_bundle(store: Path, source: Path) -> dict:
    source = source.resolve(strict=True)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    model = inventory(source, manifest)
    with ImportQueue(store / "results") as queue, ModelRegistry(store / "models") as registry:
        job = queue.enqueue(source, {key: manifest[key] for key in ("bundle_id", "robot_hash", "files")})
        owner = "desktop-" + job
        status = queue.status(job)["status"]
        if status != "completed":
            claimed = queue.claim(owner)
            if claimed != job:
                raise ImportFailure("Result import is already running; retry after it finishes")
            while queue.step(job, owner) != "completed":
                pass
        catalog = ResultCatalog(queue)
        result = catalog.import_experiment(job)
        registered = registry.import_file(source / model["path"], name=model["name"], version=model["version"],
                                          category=model["category"], origin=model["origin"],
                                          license_id=model["license"], expected_sha256=manifest["robot_hash"])
        association = catalog.link_model(result["run_id"], registered["id"], registry)
        evidence = ResultWorkflow(queue).ingest(result["run_id"], job)
        return {"status": "imported", "bundle_id": manifest["bundle_id"], "run_id": result["run_id"],
                "rows": result["rows"], "origin": queue.db.execute("SELECT origin FROM experiments WHERE run_id=?", (result["run_id"],)).fetchone()[0],
                "model": association, "evidence": evidence, "reference_performance": False}


def import_native_run(store: Path, source: Path, algorithm: str, videos: Path | None) -> dict:
    with tempfile.TemporaryDirectory(prefix="urdftools-native-") as temporary:
        report = prepare_native(source, Path(temporary), algorithm, videos)
        with ImportQueue(store / "results") as queue:
            ResultCatalog(queue)
            prior = queue.db.execute("SELECT run_id FROM experiments WHERE run_id=?", (report["run_id"],)).fetchone()
            if prior:
                return {"status": "already_imported", "run_id": prior["run_id"], "native_source": report}
        result = import_bundle(store, Path(temporary))
        result["native_source"] = report
        return result


def list_runs(store: Path) -> dict:
    with ImportQueue(store / "results") as queue:
        ResultCatalog(queue)
        ResultWorkflow(queue)
        queue.db.execute("""CREATE TABLE IF NOT EXISTS result_projects(
          run_id TEXT PRIMARY KEY, display_name TEXT NOT NULL,
          is_standard INTEGER NOT NULL DEFAULT 0 CHECK(is_standard IN (0,1)))""")
        rows = queue.db.execute("""SELECT e.run_id,e.algorithm,e.protocol,e.origin,e.robot_hash,e.metadata_json,
                                 count(m.row_index) AS metrics, x.run_id AS evidence_run,
                                 p.display_name,p.is_standard,r.model_name FROM experiments e
                                 LEFT JOIN scalar_metrics m ON m.run_id=e.run_id
                                 LEFT JOIN result_evidence x ON x.run_id=e.run_id
                                 LEFT JOIN result_projects p ON p.run_id=e.run_id
                                 LEFT JOIN result_models r ON r.run_id=e.run_id
                                 GROUP BY e.run_id ORDER BY e.rowid DESC""").fetchall()
        return {"runs": [{"run_id": row["run_id"], "algorithm": row["algorithm"], "protocol": row["protocol"],
                          "origin": row["origin"], "robot_hash": row["robot_hash"], "metrics": row["metrics"],
                          "category": json.loads(row["metadata_json"])["robot_category"],
                          "has_evidence": row["evidence_run"] is not None,
                          "model_name": row["model_name"] or row["run_id"],
                          "display_name": row["display_name"] or row["model_name"] or row["run_id"],
                          "is_standard": bool(row["is_standard"])} for row in rows],
                "verified_reference_count": 0}


def update_project(store: Path, run_id: str, name: str, standard: bool) -> dict:
    name = name.strip()
    if not name or len(name) > 120 or any(ord(ch) < 32 for ch in name):
        raise ImportFailure("Project name must contain 1–120 printable characters")
    with ImportQueue(store / "results") as queue:
        ResultCatalog(queue)
        ResultWorkflow(queue)
        queue.db.execute("""CREATE TABLE IF NOT EXISTS result_projects(
          run_id TEXT PRIMARY KEY, display_name TEXT NOT NULL,
          is_standard INTEGER NOT NULL DEFAULT 0 CHECK(is_standard IN (0,1)))""")
        if queue.db.execute("SELECT 1 FROM experiments WHERE run_id=?", (run_id,)).fetchone() is None:
            raise ImportFailure("Unknown project run")
        queue.db.execute("""INSERT INTO result_projects(run_id,display_name,is_standard) VALUES(?,?,?)
          ON CONFLICT(run_id) DO UPDATE SET display_name=excluded.display_name,is_standard=excluded.is_standard""",
                         (run_id, name, int(standard)))
        return {"run_id": run_id, "display_name": name, "is_standard": standard}


def metric_series(store: Path, run_id: str) -> dict:
    with ImportQueue(store / "results") as queue:
        ResultCatalog(queue)
        if queue.db.execute("SELECT 1 FROM experiments WHERE run_id=?", (run_id,)).fetchone() is None:
            raise ImportFailure("Unknown project run")
        names = [row[0] for row in queue.db.execute(
            "SELECT metric FROM scalar_metrics WHERE run_id=? GROUP BY metric ORDER BY metric LIMIT 16", (run_id,))]
        series = []
        for name in names:
            count = queue.db.execute("SELECT count(*) FROM scalar_metrics WHERE run_id=? AND metric=?", (run_id, name)).fetchone()[0]
            stride = max(1, (count + 399) // 400)
            rows = queue.db.execute("""SELECT step,value,unit FROM scalar_metrics
                WHERE run_id=? AND metric=? ORDER BY step,row_index""", (run_id, name))
            points = []
            unit = ""
            for index, row in enumerate(rows):
                if index == 0:
                    unit = row["unit"]
                if index % stride == 0:
                    points.append([row["step"], row["value"]])
            series.append({"metric": name, "unit": unit, "points": points})
        return {"run_id": run_id, "series": series}


def scene_assets(store: Path, run_id: str) -> dict:
    with ImportQueue(store / "results") as queue:
        row = queue.db.execute("SELECT job_id FROM experiments WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise ImportFailure("Unknown project run")
        manifest = json.loads(queue.status(row["job_id"])["manifest"])
        model_path = next((item["path"] for item in manifest["files"]
                           if item["sha256"] == manifest["robot_hash"] and item["path"].lower().endswith(".urdf")), None)
        if model_path is None:
            raise ImportFailure("Project has no indexed URDF")
        assets = [{"path": item["path"], "sha256": item["sha256"], "size": item["size"]}
                  for item in manifest["files"] if item["path"].lower().endswith(
                      (".urdf", ".obj", ".stl", ".dae", ".png", ".jpg", ".jpeg", ".bmp"))]
        return {"run_id": run_id, "model_path": model_path, "assets": assets}


def pair_records(store: Path, candidate_id: str) -> dict:
    with ImportQueue(store / "results") as queue:
        queue.db.execute("""CREATE TABLE IF NOT EXISTS result_pair_jobs(
          candidate_id TEXT NOT NULL, reference_id TEXT NOT NULL,
          request_id TEXT, mode TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(candidate_id,reference_id))""")
        rows = queue.db.execute("""SELECT candidate_id,reference_id,request_id,mode
            FROM result_pair_jobs WHERE candidate_id=? ORDER BY updated_at DESC,reference_id""",
            (candidate_id,)).fetchall()
        return {"candidate_id": candidate_id, "pairs": [dict(row) for row in rows]}


def save_pair_record(store: Path, candidate_id: str, reference_id: str,
                     request_id: str | None, mode: str | None) -> dict:
    if candidate_id == reference_id or (request_id is not None and
       (len(request_id) != 32 or any(ch not in "0123456789abcdef" for ch in request_id))):
        raise ImportFailure("Invalid result pair or agent request")
    if mode not in {None, "webcodex", "cli"}:
        raise ImportFailure("Invalid agent mode")
    with ImportQueue(store / "results") as queue:
        ResultCatalog(queue)
        ResultWorkflow(queue)
        algorithms = queue.db.execute("""SELECT run_id,algorithm FROM experiments
            WHERE run_id IN (?,?)""", (candidate_id, reference_id)).fetchall()
        by_id = {row["run_id"]: row["algorithm"] for row in algorithms}
        if candidate_id not in by_id or reference_id not in by_id or by_id[candidate_id] != by_id[reference_id]:
            raise ImportFailure("Both projects must have the same algorithm")
        queue.db.execute("""CREATE TABLE IF NOT EXISTS result_pair_jobs(
          candidate_id TEXT NOT NULL, reference_id TEXT NOT NULL,
          request_id TEXT, mode TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(candidate_id,reference_id))""")
        queue.db.execute("""INSERT INTO result_pair_jobs(candidate_id,reference_id,request_id,mode)
            VALUES(?,?,?,?) ON CONFLICT(candidate_id,reference_id) DO UPDATE SET
            request_id=excluded.request_id,mode=excluded.mode,updated_at=CURRENT_TIMESTAMP""",
            (candidate_id, reference_id, request_id, mode))
        return {"candidate_id": candidate_id, "reference_id": reference_id,
                "request_id": request_id, "mode": mode}


def compare_runs(store: Path, reference_id: str, candidate_id: str) -> dict:
    with ImportQueue(store / "results") as queue:
        return ResultWorkflow(queue).compare(reference_id, candidate_id)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("import", "import-native", "list", "compare", "project", "series", "scene", "pairs", "save-pair"))
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--algorithm")
    parser.add_argument("--videos", type=Path)
    parser.add_argument("--reference")
    parser.add_argument("--candidate")
    parser.add_argument("--run-id")
    parser.add_argument("--name")
    parser.add_argument("--standard", action="store_true")
    parser.add_argument("--request-id")
    parser.add_argument("--mode", choices=("webcodex", "cli"))
    args = parser.parse_args()
    if args.action in {"import", "import-native"} and args.source is None:
        parser.error("import requires --source")
    if args.action == "import-native" and not args.algorithm:
        parser.error("import-native requires --algorithm")
    if args.action == "compare" and (not args.reference or not args.candidate):
        parser.error("compare requires --reference and --candidate")
    if args.action in {"project", "series", "scene"} and not args.run_id:
        parser.error("project, series and scene require --run-id")
    if args.action == "project" and args.name is None:
        parser.error("project requires --name")
    if args.action == "pairs" and not args.candidate:
        parser.error("pairs requires --candidate")
    if args.action == "save-pair" and (not args.candidate or not args.reference):
        parser.error("save-pair requires --candidate and --reference")
    result = (import_bundle(args.store, args.source) if args.action == "import" else
              import_native_run(args.store, args.source, args.algorithm, args.videos) if args.action == "import-native" else
              compare_runs(args.store, args.reference, args.candidate) if args.action == "compare" else
              update_project(args.store, args.run_id, args.name, args.standard) if args.action == "project" else
              metric_series(args.store, args.run_id) if args.action == "series" else
              scene_assets(args.store, args.run_id) if args.action == "scene" else
              pair_records(args.store, args.candidate) if args.action == "pairs" else
              save_pair_record(args.store, args.candidate, args.reference, args.request_id, args.mode)
              if args.action == "save-pair" else list_runs(args.store))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
