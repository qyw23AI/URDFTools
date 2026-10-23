"""Conservative comparison of external runs; training seeds are sampling units."""
from __future__ import annotations

import math
import random
from statistics import mean

from .jobs import ImportFailure
from .terrain import compare_protocols


REQUIRED = {"robot_category", "algorithm", "algorithm_version", "protocol", "protocol_version",
            "reward_sha256", "track", "recipe_sha256", "budget_steps", "terrain"}


def compare_conditions(reference: dict, candidate: dict) -> dict:
    reasons = []
    for label, item in (("reference", reference), ("candidate", candidate)):
        if not isinstance(item, dict) or not REQUIRED.issubset(item):
            reasons.append({"field": label, "reason": "Incomplete comparison protocol", "severity": "incomparable"})
            continue
        if item["track"] not in {"fixed_recipe", "bounded_tuning"} or type(item["budget_steps"]) is not int or item["budget_steps"] <= 0:
            reasons.append({"field": label, "reason": "Invalid track or budget", "severity": "incomparable"})
    if reasons:
        return {"status": "incomparable", "reasons": reasons}
    for label, item in (("reference", reference), ("candidate", candidate)):
        for field in ("robot_category", "algorithm", "algorithm_version", "protocol", "protocol_version", "reward_sha256", "recipe_sha256"):
            if not isinstance(item[field], str) or not item[field].strip():
                reasons.append({"field": f"{label}.{field}", "severity": "incomparable", "reason": "Missing comparison identity"})
    for field in ("robot_category", "algorithm", "algorithm_version", "protocol", "protocol_version",
                  "reward_sha256", "track", "budget_steps"):
        if reference[field] != candidate[field]:
            reasons.append({"field": field, "reference": reference[field], "candidate": candidate[field],
                            "severity": "incomparable"})
    if reference["track"] == "fixed_recipe" and reference["recipe_sha256"] != candidate["recipe_sha256"]:
        reasons.append({"field": "recipe_sha256", "severity": "incomparable", "reason": "Fixed recipes differ"})
    if reference["track"] == "bounded_tuning" and reference.get("search_budget") != candidate.get("search_budget"):
        reasons.append({"field": "search_budget", "severity": "incomparable", "reason": "Tuning budgets differ"})
    if reference.get("paired_seed_design", False) != candidate.get("paired_seed_design", False):
        reasons.append({"field": "paired_seed_design", "severity": "incomparable", "reason": "Seed pairing design differs"})
    terrain = compare_protocols(reference["terrain"], candidate["terrain"])
    reasons.extend(terrain["reasons"])
    status = "incomparable" if any(r["severity"] == "incomparable" for r in reasons) else "conditional" if any(r["severity"] == "conditional" for r in reasons) else "matched"
    return {"status": status, "reasons": reasons}


def _seed_scores(runs: list[dict]) -> tuple[dict[int, float], dict]:
    if not isinstance(runs, list) or not runs:
        raise ImportFailure("Independent training runs required")
    scores = {}
    counts = {"training_failed": 0, "missing": 0, "completed": 0, "episodes": 0}
    for item in runs:
        if not isinstance(item, dict) or set(item) != {"train_seed", "status", "episodes"}:
            raise ImportFailure("Run requires train_seed, status and episodes")
        seed = item["train_seed"]
        if type(seed) is not int or seed < 0 or seed in scores or item["status"] not in {"completed", "training_failed", "missing"}:
            raise ImportFailure("Invalid or repeated training seed/status")
        episodes = item["episodes"]
        if item["status"] == "completed":
            if not isinstance(episodes, list) or not episodes or any(type(v) is not bool for v in episodes):
                raise ImportFailure("Completed run needs observed boolean evaluation episodes")
            scores[seed] = sum(episodes)/len(episodes)
            counts["completed"] += 1
            counts["episodes"] += len(episodes)
        elif item["status"] == "training_failed":
            if episodes != []:
                raise ImportFailure("Failed training has no evaluated episodes")
            scores[seed] = 0.0
            counts["training_failed"] += 1
        else:
            if episodes != []:
                raise ImportFailure("Missing run has no observed episodes")
            scores[seed] = math.nan
            counts["missing"] += 1
    return scores, counts


def _percentile(values: list[float], q: float) -> float:
    values = sorted(values)
    location = (len(values)-1)*q
    lo = math.floor(location)
    hi = math.ceil(location)
    return values[lo] + (values[hi]-values[lo])*(location-lo)


def compare_success(reference_protocol: dict, candidate_protocol: dict,
                    reference_runs: list[dict], candidate_runs: list[dict],
                    *, bootstrap_samples: int = 2000) -> dict:
    condition = compare_conditions(reference_protocol, candidate_protocol)
    reference, ref_counts = _seed_scores(reference_runs)
    candidate, cand_counts = _seed_scores(candidate_runs)
    result = {"comparability": condition, "reference_counts": ref_counts, "candidate_counts": cand_counts,
              "sampling_unit": "independent_training_seed", "reference_mean": None,
              "candidate_mean": None, "difference": None, "confidence_interval_95": None,
              "status": "incomparable" if condition["status"] == "incomparable" else "insufficient_data"}
    if condition["status"] == "incomparable" or ref_counts["missing"] or cand_counts["missing"]:
        return result
    if not reference or not candidate:
        return result
    ref_values, cand_values = list(reference.values()), list(candidate.values())
    result["reference_mean"] = mean(ref_values)
    result["candidate_mean"] = mean(cand_values)
    result["difference"] = result["candidate_mean"] - result["reference_mean"]
    result["status"] = "compared" if min(len(ref_values), len(cand_values)) >= 2 else "single_seed_descriptive"
    if min(len(ref_values), len(cand_values)) < 3:
        return result
    if type(bootstrap_samples) is not int or not 100 <= bootstrap_samples <= 10000:
        raise ValueError("bootstrap_samples must be 100..10000")
    randomizer = random.Random(20261023)
    samples = []
    if reference_protocol.get("paired_seed_design") is True and candidate_protocol.get("paired_seed_design") is True and set(reference) == set(candidate):
        differences = [candidate[seed]-reference[seed] for seed in sorted(reference)]
        for _ in range(bootstrap_samples):
            samples.append(mean(randomizer.choices(differences, k=len(differences))))
        method = "paired_seed_bootstrap"
    else:
        for _ in range(bootstrap_samples):
            samples.append(mean(randomizer.choices(cand_values, k=len(cand_values))) -
                           mean(randomizer.choices(ref_values, k=len(ref_values))))
        method = "independent_seed_bootstrap"
    result["confidence_interval_95"] = [_percentile(samples, 0.025), _percentile(samples, 0.975)]
    result["interval_method"] = method
    return result
