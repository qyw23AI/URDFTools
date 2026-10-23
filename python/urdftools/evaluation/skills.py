"""Safe local skill registry and numerical evaluation; manifests never execute code."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import statistics

from urdftools.evaluation.static import symmetric_eigenvalues

TOOLS = {"inertia_tensor", "coordinate_frame", "contact_force", "sample_statistics", "quadruped_urdf", "humanoid_urdf"}
IDENT = re.compile(r"[a-z][a-z0-9_]{1,63}\Z")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")


class SkillError(ValueError):
    pass


def fields(obj, required, optional=()):
    if not isinstance(obj, dict) or not set(required) <= obj.keys() or not obj.keys() <= set(required) | set(optional):
        raise SkillError("missing or undeclared fields")


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1e90:
        raise SkillError("finite bounded number required")
    return float(value)


def matrix(value):
    if not isinstance(value, list) or len(value) != 3 or any(not isinstance(r, list) or len(r) != 3 for r in value):
        raise SkillError("expected 3x3 matrix")
    return [[number(v) for v in row] for row in value]


def validate_manifest(m):
    fields(m, ("schema_version", "id", "version", "source", "description", "rules"))
    if type(m["schema_version"]) is not int or m["schema_version"] != 1:
        raise SkillError("unsupported schema")
    if not isinstance(m["id"], str) or not IDENT.fullmatch(m["id"]):
        raise SkillError("invalid skill id")
    if not isinstance(m["version"], str) or not VERSION.fullmatch(m["version"]):
        raise SkillError("invalid version")
    if any(not isinstance(m[k], str) or not 1 <= len(m[k]) <= 2000 for k in ("source", "description")):
        raise SkillError("source and description required")
    if not isinstance(m["rules"], list) or not 1 <= len(m["rules"]) <= 64:
        raise SkillError("nonempty bounded rules required")
    ids = set()
    for rule in m["rules"]:
        fields(rule, ("id", "tool", "config"))
        if not isinstance(rule["id"], str) or not IDENT.fullmatch(rule["id"]) or rule["id"] in ids:
            raise SkillError("invalid or duplicate rule")
        ids.add(rule["id"])
        if not isinstance(rule["tool"], str) or rule["tool"] not in TOOLS:
            raise SkillError("unapproved tool")
        fields(rule["config"], (), ("tolerance", "minimum_samples"))
        cfg = rule["config"]
        if "tolerance" in cfg and (rule["tool"] not in {"inertia_tensor", "coordinate_frame"} or
                                    not 0 < number(cfg["tolerance"]) <= .1):
            raise SkillError("invalid tolerance")
        if "minimum_samples" in cfg and (rule["tool"] != "sample_statistics" or
                type(cfg["minimum_samples"]) is not int or not 2 <= cfg["minimum_samples"] <= 10000):
            raise SkillError("invalid minimum_samples")
    return m


def discover_skills(root):
    root = Path(root).resolve()
    if not root.is_dir():
        raise SkillError("skill root missing")
    found = {}
    for category in ("builtin", "local"):
        parent = root / category
        if parent.is_symlink():
            raise SkillError("symlink category refused")
        if not parent.exists():
            continue
        for folder in sorted(parent.iterdir()):
            if folder.is_symlink():
                raise SkillError("symlink skill refused")
            if not folder.is_dir():
                continue
            manifest = folder / "manifest.json"
            if manifest.is_symlink():
                raise SkillError("symlink manifest refused")
            if not manifest.is_file():
                continue
            if manifest.stat().st_size > 65536:
                raise SkillError("oversized manifest")
            raw = manifest.read_bytes()
            try:
                m = validate_manifest(json.loads(raw))
            except (ValueError, UnicodeError) as exc:
                raise SkillError(f"invalid manifest {manifest}: {exc}") from exc
            if folder.name != m["id"] or m["id"] in found:
                raise SkillError("directory mismatch or duplicate skill")
            found[m["id"]] = {"manifest": m, "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                              "category": category, "path": str(manifest)}
    return found


def evaluate(tool, data, config):
    if tool == "humanoid_urdf":
        fields(data, ("urdf_xml",), ("contact_trace",))
        from urdftools.evaluation.humanoid import evaluate_humanoid_xml
        try:
            return evaluate_humanoid_xml(data["urdf_xml"], data.get("contact_trace"))
        except (ValueError, TypeError, OverflowError) as exc:
            raise SkillError(f"invalid humanoid URDF: {exc}") from exc
    if tool == "quadruped_urdf":
        fields(data, ("urdf_xml",), ("contact_trace",))
        from urdftools.evaluation.quadruped import evaluate_quadruped_xml
        try:
            return evaluate_quadruped_xml(data["urdf_xml"], data.get("contact_trace"))
        except (ValueError, TypeError, OverflowError) as exc:
            raise SkillError(f"invalid quadruped URDF: {exc}") from exc
    if tool == "inertia_tensor":
        fields(data, ("tensor_kg_m2",))
        a = matrix(data["tensor_kg_m2"])
        scale = max(1e-16, *(abs(v) for row in a for v in row))
        tol = config.get("tolerance", 1e-8) * scale
        if any(abs(a[i][j]-a[j][i]) > tol for i in range(3) for j in range(3)):
            return {"passed": False, "reason": "nonsymmetric"}
        try:
            eig = symmetric_eigenvalues(a)
        except (ValueError, OverflowError) as exc:
            raise SkillError("inertia eigensolver failed") from exc
        if not all(math.isfinite(x) for x in eig):
            raise SkillError("nonfinite principal moment")
        reason = ("negative_principal_moment" if eig[0] < -tol else
                  "triangle_inequality" if eig[2] > eig[0]+eig[1]+tol else "ok")
        return {"passed": reason == "ok", "reason": reason,
                "principal_moments_kg_m2": list(eig)}
    if tool == "coordinate_frame":
        fields(data, ("rotation",))
        a = matrix(data["rotation"])
        orth = max(abs(sum(a[k][i]*a[k][j] for k in range(3))-(i == j))
                   for i in range(3) for j in range(3))
        det = (a[0][0]*(a[1][1]*a[2][2]-a[1][2]*a[2][1])
               - a[0][1]*(a[1][0]*a[2][2]-a[1][2]*a[2][0])
               + a[0][2]*(a[1][0]*a[2][1]-a[1][1]*a[2][0]))
        ok = orth <= config.get("tolerance", 1e-8) and abs(det-1) <= config.get("tolerance", 1e-8)
        return {"passed": ok, "reason": "ok" if ok else "invalid_rotation",
                "orthogonality_error": orth, "determinant": det}
    if tool == "contact_force":
        fields(data, ("normal_force_n", "tangential_force_n", "friction_coefficient"), ("penetration_m",))
        n, t, mu = (number(data[k]) for k in ("normal_force_n", "tangential_force_n", "friction_coefficient"))
        d = number(data.get("penetration_m", 0))
        if mu < 0 or d < 0:
            raise SkillError("negative friction or penetration")
        margin = mu*n-abs(t)
        ok = n >= 0 and margin >= -1e-10
        return {"passed": ok, "reason": "ok" if ok else "friction_cone_violation",
                "friction_margin_n": margin}
    if tool == "sample_statistics":
        fields(data, ("samples",))
        v = data["samples"]
        if not isinstance(v, list) or len(v) > 10000:
            raise SkillError("invalid samples")
        if len(v) < config.get("minimum_samples", 2):
            return {"passed": False, "reason": "insufficient_samples", "count": len(v)}
        v = [number(x) for x in v]
        mean, std = statistics.fmean(v), statistics.stdev(v)
        if not all(map(math.isfinite, (mean, std))):
            raise SkillError("statistical overflow")
        ci = 1.96*std/math.sqrt(len(v))
        return {"passed": True, "reason": "ok", "count": len(v), "mean": mean,
                "sample_std": std, "normal_approx_95ci": [mean-ci, mean+ci],
                "caveat": "descriptive normal approximation; no significance or RL claim"}
    raise SkillError("unapproved tool")


def run_skill(skill, inputs):
    m = validate_manifest(skill["manifest"])
    if not isinstance(inputs, dict) or set(inputs) != {r["id"] for r in m["rules"]}:
        raise SkillError("exactly one input per rule required")
    results = []
    for r in m["rules"]:
        if not isinstance(inputs[r["id"]], dict):
            raise SkillError("rule input must be an object")
        results.append({"rule_id": r["id"], "tool": r["tool"],
                        **evaluate(r["tool"], inputs[r["id"]], r["config"])})
    return {"skill_id": m["id"], "skill_version": m["version"],
            "manifest_sha256": skill["manifest_sha256"], "results": results,
            "passed": all(r["passed"] for r in results)}
