"""Adapt completed MyHIMLoco/WMP training folders into the immutable result format.

Only files produced by training are read. Checkpoints are never deserialized.
Missing evaluation outcomes remain missing rather than being inferred from rewards.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from .jobs import ImportFailure, digest


def _identity(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def _model_from_config(source: Path, config: dict) -> Path:
    asset = config.get("env", {}).get("asset", {}).get("file", "")
    if not isinstance(asset, str) or "/resources/robots/" not in asset:
        raise ImportFailure("Cannot locate URDF from config.json; choose a training directory with env.asset.file")
    suffix = asset.split("/resources/robots/", 1)[1]
    for root in source.parents:
        for prefix in (root / "resources/robots", root / "legged_gym/resources/robots",
                       root / "GettingHimLoco/legged_gym/resources/robots"):
            candidate = prefix / suffix
            if candidate.is_file():
                return candidate.resolve()
    raise ImportFailure(f"URDF named in config.json was not found: {suffix}")


def _copy_model(urdf: Path, destination: Path) -> str:
    try:
        root = ET.parse(urdf).getroot()
    except ET.ParseError as exc:
        raise ImportFailure("Invalid URDF XML") from exc
    target = destination / "robot/urdf" / urdf.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(urdf, target)
    for mesh in root.findall(".//mesh"):
        name = mesh.get("filename", "")
        if not name or name.startswith("package://") or Path(name).is_absolute():
            continue
        origin = (urdf.parent / name).resolve()
        if not origin.is_file() or not origin.is_relative_to(urdf.parent.parent):
            raise ImportFailure(f"URDF mesh is unavailable or outside robot assets: {name}")
        relative = origin.relative_to(urdf.parent.parent)
        copied = destination / "robot" / relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, copied)
    return target.relative_to(destination).as_posix()


def prepare_native(source: Path, destination: Path, algorithm: str, video_dir: Path | None = None) -> dict:
    source = source.resolve(strict=True)
    if not source.is_dir() or not 1 <= len(algorithm.strip()) <= 80 or any(ord(ch) < 32 for ch in algorithm):
        raise ImportFailure("Training directory and algorithm name are required")
    config_path = source / "config.json"
    if not config_path.is_file() or config_path.stat().st_size > 16 * 1024 * 1024:
        raise ImportFailure("Training directory needs a readable config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("env"), dict):
        raise ImportFailure("Unsupported training configuration")
    event_files = sorted(source.glob("events.out.tfevents.*"))
    event_files = [file for file in event_files if file.is_file() and 0 < file.stat().st_size <= 64 * 1024 * 1024]
    if not event_files:
        raise ImportFailure("Training directory needs a TensorBoard events.out.tfevents.* file (up to 64 MiB)")
    urdf = _model_from_config(source, config)
    model_path = _copy_model(urdf, destination)
    shutil.copyfile(config_path, destination / "config.json")
    metrics = []
    for index, event in enumerate(event_files[:8]):
        name = f"metrics/events_{index}.tfevents"
        (destination / "metrics").mkdir(exist_ok=True)
        shutil.copyfile(event, destination / name)
        # The importer requires explicit units. TensorBoard tags are discovered
        # from the source file; unknown units are displayed as dimensionless.
        from tensorboard.backend.event_processing.event_file_loader import LegacyEventFileLoader
        tags = set()
        for item in LegacyEventFileLoader(str(event)).Load():
            if item.HasField("summary"):
                tags.update(value.tag for value in item.summary.value if value.HasField("simple_value"))
        if tags:
            metrics.append({"path": name, "format": "tensorboard",
                            "units": {tag: "未标注" for tag in sorted(tags)}})
    if not metrics:
        raise ImportFailure("TensorBoard event files contain no scalar metrics")
    args = config.get("args", {})
    train = config.get("train", {})
    seed = args.get("seed", train.get("seed", config["env"].get("seed")))
    seed_runs = [{"train_seed": seed, "status": "missing", "episodes": []}] if type(seed) is int and seed >= 0 else []
    videos = []
    roots = [source]
    if video_dir is not None:
        video_dir = video_dir.resolve(strict=True)
        if not video_dir.is_dir():
            raise ImportFailure("Video directory is unavailable")
        roots.insert(0, video_dir)
    for root in roots:
        clips = sorted(root.glob("checkpoint_videos/**/preview.mp4")) or sorted(root.glob("**/preview.mp4"))
        for clip in clips[-4:]:
            if not clip.is_file() or not 0 < clip.stat().st_size <= 128 * 1024 ** 2:
                continue
            name = f"videos/{len(videos)}_{clip.parent.name}.mp4"
            (destination / "videos").mkdir(exist_ok=True)
            shutil.copyfile(clip, destination / name)
            videos.append({"path": name, "episode_id": clip.parent.name, "camera": "training_preview",
                           "experiment_offset_s": 0.0, "declared_fps": None, "events": []})
        if videos:
            break
    algorithm = algorithm.strip()
    robot_hash = digest(destination / model_path)
    config_sha = digest(destination / "config.json")
    auxiliary = {}
    for name in ("gait_metrics.json", "validation.json", "progress.json", "evaluation.json", "run_manifest.json"):
        original = source / name
        if original.is_file() and not original.is_symlink() and original.stat().st_size <= 4 * 1024 * 1024:
            copied = destination / name
            shutil.copyfile(original, copied)
            auxiliary[name] = digest(copied)
    run_id = f"{algorithm.lower().replace(' ', '_')}-{source.name}-{config_sha[:12]}"[:160]
    protocol_name = str(args.get("task") or args.get("terrain") or args.get("stage") or source.parent.name)
    info = {"schema_version": 1, "run_id": run_id, "robot_hash": robot_hash,
            "origin": "user_upload", "robot_category": "quadruped", "algorithm": algorithm,
            "protocol": protocol_name, "engine": "IsaacLab", "metrics": metrics}
    # The training config does not define held-out test seeds or observed episode
    # success. Keep the comparison protocol incomplete until those are supplied.
    evidence = {"schema_version": 1, "protocol": {"source_config_sha256": config_sha,
                "reward_sha256": _identity(config["env"].get("rewards")),
                "train_sha256": _identity(train), "evaluation_status": "not_mapped_to_success",
                "auxiliary_sha256": auxiliary},
                "seed_runs": seed_runs, "videos": videos}
    (destination / "experiment.json").write_text(json.dumps(info, ensure_ascii=False))
    (destination / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False))
    files = []
    for file in sorted(destination.rglob("*")):
        if file.is_file():
            files.append({"path": file.relative_to(destination).as_posix(), "size": file.stat().st_size,
                          "sha256": digest(file)})
    manifest = {"bundle_id": "native-" + _identity([run_id, config_sha, robot_hash])[:32],
                "robot_hash": robot_hash, "files": files,
                "model": {"path": model_path, "name": urdf.stem, "version": config_sha[:12],
                          "category": "quadruped", "origin": "user_upload", "license": None}}
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    return {"run_id": run_id, "source": str(source), "model": str(urdf),
            "events": len(metrics), "videos": len(videos), "evaluation": "missing"}
