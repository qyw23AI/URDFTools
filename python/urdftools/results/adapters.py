"""Versioned offline adapters for common external training logs."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from pathlib import Path

from .jobs import ImportFailure

MAPPINGS = {
    "sb3-csv-v1": {"time/total_timesteps": "step", "rollout/ep_rew_mean": "episode_reward_mean",
                   "rollout/ep_len_mean": "episode_length_mean", "time/fps": "fps"},
    "rsl-tensorboard-v1": {"Train/mean_reward": "episode_reward_mean", "Train/mean_episode_length": "episode_length_mean"},
    "isaaclab-tensorboard-v1": {"Train/mean_reward": "episode_reward_mean", "Metrics/success_rate": "success_rate"},
}


def _number(value, field):
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ImportFailure(f"Invalid {field}") from exc
    if not math.isfinite(out):
        raise ImportFailure(f"Non-finite {field}")
    return out


def adapt_log(version: str, raw: bytes) -> dict:
    """Return B01 metric rows plus an explicit list of source fields not mapped."""
    if version not in MAPPINGS:
        raise ImportFailure("Unsupported adapter version")
    mapping = MAPPINGS[version]
    rows, lost = [], set()
    if version == "sb3-csv-v1":
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        if not reader.fieldnames or "time/total_timesteps" not in reader.fieldnames:
            raise ImportFailure("SB3 total timesteps column required")
        for source in reader:
            step = source.get("time/total_timesteps")
            if step is None or not step.isdecimal():
                raise ImportFailure("Invalid SB3 timestep")
            step = int(step)
            for field, value in source.items():
                if field == "time/total_timesteps" or value in (None, ""):
                    continue
                target = mapping.get(field)
                if target is None:
                    lost.add(field)
                    continue
                rows.append({"metric": target, "step": step, "value": _number(value, field), "wall_time": None})
    else:
        from .catalog import ResultCatalog
        for source in ResultCatalog._rows("tensorboard", raw):
            target = mapping.get(source["metric"])
            if target is None:
                lost.add(source["metric"])
                continue
            rows.append({"metric": target, "step": source["step"],
                         "value": _number(source["value"], target), "wall_time": source["wall_time"]})
    if not rows:
        raise ImportFailure("No supported scalar fields in external log")
    return {"adapter_version": version, "rows": rows, "unmapped_fields": sorted(lost),
            "source_bytes": len(raw), "source_sha256": hashlib.sha256(raw).hexdigest()}


def export_unified_csv(adapted: dict) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=["metric", "step", "value", "wall_time"], lineterminator="\n")
    writer.writeheader()
    writer.writerows(adapted["rows"])
    return output.getvalue().encode()


def export_mlflow_local(rows: list[dict], destination: str | Path) -> dict:
    """Write a bounded local MLflow metrics-file exchange, never contact a server."""
    destination = Path(destination)
    groups = {}
    for row in rows:
        tag = row.get("metric")
        if not isinstance(tag, str) or not tag or tag in {".", ".."} or "/" in tag or "\\" in tag:
            raise ImportFailure("Unsafe MLflow metric name")
        step = row.get("step")
        if type(step) is not int or step < 0:
            raise ImportFailure("Invalid MLflow step")
        value = _number(row.get("value"), "MLflow metric")
        wall = row.get("wall_time")
        if wall is None:
            raise ImportFailure("MLflow export requires a wall timestamp")
        timestamp_ms = round(_number(wall, "wall time")*1000)
        groups.setdefault(tag, []).append(f"{timestamp_ms} {value:.17g} {step}\n")
    if not groups:
        raise ImportFailure("No local metrics to export")
    destination.mkdir(parents=True, exist_ok=False)
    metrics = destination / "metrics"
    metrics.mkdir()
    for tag, lines in groups.items():
        (metrics / tag).write_text("".join(lines))
    return {"metrics": len(groups), "rows": len(rows), "format": "mlflow-local-metrics-v1"}


def import_mlflow_local(source: str | Path, *, version: str = "mlflow-local-metrics-v1") -> dict:
    if version != "mlflow-local-metrics-v1":
        raise ImportFailure("Unsupported MLflow local format version")
    metrics = Path(source) / "metrics"
    if not metrics.is_dir():
        raise ImportFailure("Missing local metrics directory")
    rows = []
    for path in sorted(metrics.iterdir()):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            raise ImportFailure("Invalid local metric file")
        for line in path.read_text().splitlines():
            fields = line.split()
            if len(fields) != 3 or not fields[0].isdecimal() or not fields[2].isdecimal():
                raise ImportFailure("Invalid MLflow metric record")
            rows.append({"metric": path.name, "step": int(fields[2]),
                         "value": _number(fields[1], "MLflow value"), "wall_time": int(fields[0])/1000})
    if not rows:
        raise ImportFailure("No local MLflow scalar records")
    return {"adapter_version": version, "rows": rows, "unmapped_fields": []}
