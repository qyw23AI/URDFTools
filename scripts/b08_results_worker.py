#!/usr/bin/env python3
"""Local desktop bridge for immutable external result bundles; never runs training."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from urdftools.reference.registry import ModelRegistry
from urdftools.results.catalog import ResultCatalog
from urdftools.results.jobs import ImportFailure, ImportQueue, digest
from urdftools.results.workflow import ResultWorkflow


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


def list_runs(store: Path) -> dict:
    with ImportQueue(store / "results") as queue:
        ResultCatalog(queue)
        ResultWorkflow(queue)
        rows = queue.db.execute("""SELECT e.run_id,e.algorithm,e.protocol,e.origin,e.robot_hash,e.metadata_json,
                                 count(m.row_index) AS metrics, x.run_id AS evidence_run FROM experiments e
                                 LEFT JOIN scalar_metrics m ON m.run_id=e.run_id
                                 LEFT JOIN result_evidence x ON x.run_id=e.run_id
                                 GROUP BY e.run_id ORDER BY e.rowid DESC""").fetchall()
        return {"runs": [{"run_id": row["run_id"], "algorithm": row["algorithm"], "protocol": row["protocol"],
                          "origin": row["origin"], "robot_hash": row["robot_hash"], "metrics": row["metrics"],
                          "category": json.loads(row["metadata_json"])["robot_category"],
                          "has_evidence": row["evidence_run"] is not None} for row in rows],
                "verified_reference_count": 0}


def compare_runs(store: Path, reference_id: str, candidate_id: str) -> dict:
    with ImportQueue(store / "results") as queue:
        return ResultWorkflow(queue).compare(reference_id, candidate_id)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("import", "list", "compare"))
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--reference")
    parser.add_argument("--candidate")
    args = parser.parse_args()
    if args.action == "import" and args.source is None:
        parser.error("import requires --source")
    if args.action == "compare" and (not args.reference or not args.candidate):
        parser.error("compare requires --reference and --candidate")
    result = (import_bundle(args.store, args.source) if args.action == "import" else
              compare_runs(args.store, args.reference, args.candidate) if args.action == "compare" else list_runs(args.store))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
