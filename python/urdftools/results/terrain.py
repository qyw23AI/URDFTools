"""External terrain/push protocol and grouped outcome checks."""
from __future__ import annotations

import math

from .jobs import ImportFailure

KINDS = {"slope", "step", "obstacle", "rough", "flat"}


def validate_protocol(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ImportFailure("Terrain protocol object required")
    required = {"terrain_kind", "terrain_version", "scale_mode", "terrain_size", "terrain_size_unit", "push_force_n",
                "push_duration_s", "train_seeds", "test_seeds", "success_definition"}
    if not required.issubset(value):
        raise ImportFailure("Incomplete terrain protocol")
    if value["terrain_kind"] not in KINDS or not isinstance(value["terrain_version"], str) or not value["terrain_version"]:
        raise ImportFailure("Terrain kind/version required")
    if value["scale_mode"] not in {"physical_m", "leg_normalized"}:
        raise ImportFailure("Physical and normalized scale must be separate")
    expected_unit = "deg" if value["terrain_kind"] == "slope" else "none" if value["terrain_kind"] == "flat" else "m" if value["scale_mode"] == "physical_m" else "leg_ratio"
    if value["terrain_size_unit"] != expected_unit:
        raise ImportFailure("Terrain size unit does not match kind and scale mode")
    for field in ("terrain_size", "push_force_n", "push_duration_s"):
        if type(value[field]) not in (int, float) or not math.isfinite(value[field]) or value[field] < 0:
            raise ImportFailure(f"Invalid {field}")
    if not isinstance(value["success_definition"], str) or not value["success_definition"].strip():
        raise ImportFailure("Explicit success definition required")
    for field in ("train_seeds", "test_seeds"):
        seeds = value[field]
        if not isinstance(seeds, list) or not seeds or any(type(s) is not int or s < 0 for s in seeds) or len(seeds) != len(set(seeds)):
            raise ImportFailure("Nonempty unique integer seeds required")
    if set(value["train_seeds"]) & set(value["test_seeds"]):
        raise ImportFailure("Train/test terrain seed leakage")
    if value["scale_mode"] == "leg_normalized":
        length = value.get("leg_length_m")
        if type(length) not in (int, float) or not math.isfinite(length) or length <= 0:
            raise ImportFailure("Leg normalized protocol requires measured leg length")
    if value["terrain_kind"] == "flat" and value["terrain_size"] != 0:
        raise ImportFailure("Flat terrain size must be zero")
    return dict(value)


def compare_protocols(reference: dict, candidate: dict) -> dict:
    reasons = []
    for label, protocol in (("reference", reference), ("candidate", candidate)):
        try:
            validate_protocol(protocol)
        except ImportFailure as exc:
            reasons.append({"field": label, "reason": str(exc), "severity": "incomparable"})
    if reasons:
        return {"status": "incomparable", "reasons": reasons}
    for field in ("terrain_kind", "terrain_version", "scale_mode", "terrain_size_unit", "success_definition"):
        if reference[field] != candidate[field]:
            reasons.append({"field": field, "reference": reference[field], "candidate": candidate[field], "severity": "incomparable"})
    for field in ("terrain_size", "push_force_n", "push_duration_s"):
        if not math.isclose(reference[field], candidate[field], rel_tol=0, abs_tol=1e-12):
            reasons.append({"field": field, "reference": reference[field], "candidate": candidate[field], "severity": "conditional"})
    if reference["scale_mode"] == "leg_normalized" and candidate["scale_mode"] == "leg_normalized" and reference["leg_length_m"] != candidate["leg_length_m"]:
        reasons.append({"field": "leg_length_m", "reference": reference["leg_length_m"],
                        "candidate": candidate["leg_length_m"], "severity": "context"})
    if set(reference["test_seeds"]) != set(candidate["test_seeds"]):
        reasons.append({"field": "test_seeds", "severity": "conditional", "reason": "Evaluation seeds differ"})
    status = "incomparable" if any(r["severity"] == "incomparable" for r in reasons) else "conditional" if any(r["severity"] == "conditional" for r in reasons) else "matched"
    return {"status": status, "reasons": reasons}


def summarize_episodes(protocol: dict, episodes: list[dict]) -> dict:
    protocol = validate_protocol(protocol)
    if not isinstance(episodes, list) or not episodes:
        raise ImportFailure("At least one evaluation episode required")
    allowed = set(protocol["test_seeds"])
    groups = {}
    seen = set()
    for episode in episodes:
        if not isinstance(episode, dict) or set(episode) != {"episode_id", "seed", "success", "terrain_kind", "terrain_version"}:
            raise ImportFailure("Episode fields invalid")
        if type(episode["seed"]) is not int or episode["seed"] not in allowed:
            raise ImportFailure("Episode seed not in held-out test split")
        if type(episode["success"]) is not bool:
            raise ImportFailure("Success must be observed boolean")
        if episode["terrain_kind"] != protocol["terrain_kind"] or episode["terrain_version"] != protocol["terrain_version"]:
            raise ImportFailure("Episode terrain differs from protocol")
        if not isinstance(episode["episode_id"], str) or not episode["episode_id"] or episode["episode_id"] in seen:
            raise ImportFailure("Duplicate or missing episode ID")
        seen.add(episode["episode_id"])
        key = (episode["terrain_kind"], episode["terrain_version"])
        group = groups.setdefault(key, {"episodes": 0, "successes": 0})
        group["episodes"] += 1
        group["successes"] += episode["success"]
    return {"scale_mode": protocol["scale_mode"], "groups": [
        {"terrain_kind": kind, "terrain_version": version, **group,
         "success_rate": group["successes"]/group["episodes"]}
        for (kind, version), group in sorted(groups.items())]}
