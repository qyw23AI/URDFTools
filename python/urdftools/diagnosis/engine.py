"""Deterministic symptom → evidence → competing cause → test graph.

This module never infers URDF causation from a low RL score alone.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

from urdftools.evaluation.humanoid import evaluate_humanoid_xml
from urdftools.evaluation.quadruped import evaluate_quadruped_xml

ID = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")


class DiagnosisError(ValueError):
    pass


CAUSES = {
    "export_or_description": {
        "label": "URDF 导出或描述错误",
        "rules": {"joint_axis", "joint_range", "kinematic_tree", "leg_chain", "unique_names", "inertia_tensor"},
        "observations": {"export_mapping_error", "cad_urdf_mass_mismatch"},
        "action": "对照 CAD 零件和原始 URDF 的 frame、关节轴、质量及惯量，重新导出后复测。",
    },
    "collision_or_contact": {
        "label": "碰撞代理或接触配置",
        "rules": {"foot_collision", "foot_contact", "quasistatic_com_projection"},
        "observations": {"measured_foot_slip", "contact_parameter_mismatch"},
        "action": "核对足底碰撞体与接触参数，在相同控制器和地形下做无训练接触探测。",
    },
    "actuator_or_controller": {
        "label": "执行器或控制器配置",
        "rules": set(),
        "observations": {"actuator_saturation", "controller_gain_effect", "tracking_error"},
        "action": "固定 URDF，逐项核对动作映射、PD 增益、速度转矩限制和控制频率。",
    },
    "algorithm_or_budget": {
        "label": "算法、奖励或训练预算",
        "rules": set(),
        "observations": {"algorithm_budget_mismatch", "reward_mismatch", "seed_instability"},
        "action": "保持机械配置，统一奖励、训练预算、独立种子和测试集后重新导入外部结果。",
    },
    "mechanical_design": {
        "label": "机械几何或质量分布设计",
        "rules": set(),
        "observations": {"measured_design_variant_effect", "measured_cad_mass_distribution"},
        "action": "提出一个带单位的单变量 CAD 修改，复算惯量并在相同外部协议下复验。",
    },
}

OBSERVATION_KINDS = set().union(*(spec["observations"] for spec in CAUSES.values()))


def _safe_id(value: str, label: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise DiagnosisError(f"Invalid {label}")
    return value


def _skill_evidence(xml: str, category: str) -> tuple[list[dict], dict]:
    report = evaluate_quadruped_xml(xml) if category == "quadruped" else evaluate_humanoid_xml(xml)
    evidence = []
    for check in report["checks"]:
        if check["status"] == "pass":
            continue
        key = f'{report["source_sha256"]}:{check["rule_id"]}:{check["object"]}'
        evidence.append({"id": "skill:" + hashlib.sha256(key.encode()).hexdigest()[:20],
                         "kind": "skill_check", "rule": check["rule_id"], "status": check["status"],
                         "object": check["object"], "source_sha256": report["source_sha256"],
                         "source_kind": "caller_supplied_urdf", "rule_version": report["rule_version"],
                         "observed": check["observed"], "note": check["note"]})
    return evidence, {"rule_version": report["rule_version"], "source_sha256": report["source_sha256"],
                      "counts": report["counts"]}


def diagnose(case: dict) -> dict:
    if not isinstance(case, dict) or set(case) != {"case_id", "category", "urdf_xml", "comparison", "observations"}:
        raise DiagnosisError("Case requires id, category, URDF, comparison and observations")
    case_id = _safe_id(case["case_id"], "case id")
    category = case["category"]
    if category not in ("quadruped", "humanoid") or not isinstance(case["urdf_xml"], str):
        raise DiagnosisError("Supported quadruped or humanoid URDF required")
    evidence, skill_summary = _skill_evidence(case["urdf_xml"], category)
    observations = case["observations"]
    if not isinstance(observations, list) or len(observations) > 128:
        raise DiagnosisError("Bounded observation list required")
    seen = {item["id"] for item in evidence}
    for item in observations:
        if not isinstance(item, dict) or set(item) != {"id", "kind", "source_sha256", "source_kind", "object", "status", "value", "unit"}:
            raise DiagnosisError("Observation provenance and measured value required")
        eid = _safe_id(item["id"], "evidence id")
        if eid in seen or item["kind"] not in OBSERVATION_KINDS or item["status"] not in ("observed", "contradicted", "unknown"):
            raise DiagnosisError("Duplicate or unsupported evidence")
        if item["source_kind"] not in ("synthetic_fixture", "simulation", "external_experiment", "measured"):
            raise DiagnosisError("Observation source kind required")
        if not isinstance(item["source_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["source_sha256"]):
            raise DiagnosisError("Observation source SHA-256 required")
        if not isinstance(item["object"], str) or not item["object"] or not isinstance(item["unit"], str) or not item["unit"]:
            raise DiagnosisError("Observation object and unit required")
        if isinstance(item["value"], (int, float)) and (isinstance(item["value"], bool) or not math.isfinite(item["value"])):
            raise DiagnosisError("Finite numeric observation required")
        evidence.append(dict(item)); seen.add(eid)
    comparison = case["comparison"]
    comparable = False
    underperformed = False
    fixture_only = False
    if comparison is not None:
        if not isinstance(comparison, dict) or not {"reference_run_id", "candidate_run_id", "fixture_only", "comparison"} <= comparison.keys():
            raise DiagnosisError("B08 comparison identity required")
        for field in ("reference_run_id", "candidate_run_id"):
            _safe_id(comparison[field], field)
        c = comparison["comparison"]
        if not isinstance(c, dict) or not isinstance(c.get("comparability"), dict):
            raise DiagnosisError("Invalid comparison result")
        status = c["comparability"].get("status")
        if status not in ("matched", "conditional", "incomparable", "insufficient_data"):
            raise DiagnosisError("Unknown comparison status")
        fixture_only = comparison["fixture_only"] is True
        comparable = status == "matched"
        delta = c.get("difference")
        underperformed = comparable and type(delta) in (int, float) and math.isfinite(delta) and delta < 0
        key = f'{case_id}:{comparison["reference_run_id"]}:{comparison["candidate_run_id"]}'
        evidence.append({"id": "comparison:" + hashlib.sha256(key.encode()).hexdigest()[:20],
                         "kind": "external_comparison", "status": status, "difference": delta if comparable else None,
                         "reference_run_id": comparison["reference_run_id"],
                         "candidate_run_id": comparison["candidate_run_id"], "fixture_only": fixture_only,
                         "reasons": c["comparability"].get("reasons", [])})
    symptom = ("lower_external_performance" if underperformed and not fixture_only else
               "fixture_difference_only" if underperformed else
               "protocol_not_comparable" if comparison is not None and not comparable else
               "insufficient_data")
    evidence_by_id = {item["id"]: item for item in evidence}
    candidates = []
    edges = []
    for item in evidence:
        if item["kind"] == "external_comparison":
            edges.append({"from": item["id"], "to": "symptom", "relation": "qualifies"})
    for cause, spec in CAUSES.items():
        supporting = [e["id"] for e in evidence if
                      e["kind"] == "skill_check" and e["rule"] in spec["rules"] and e["status"] == "fail" or
                      e["kind"] in spec["observations"] and e["status"] == "observed"]
        counter = [e["id"] for e in evidence if e["kind"] in spec["observations"] and e["status"] == "contradicted"]
        direct_issue = any(evidence_by_id[eid]["kind"] == "skill_check" for eid in supporting)
        status = "local_description_issue" if direct_issue else "supported_hypothesis" if supporting else "needs_evidence"
        candidate = {"id": cause, "label": spec["label"], "status": status,
                     "support_evidence_ids": supporting, "counter_evidence_ids": counter,
                     "missing_data": [] if supporting else ["需要该因素的直接测量或受控变体"],
                     "confidence_basis": "直接静态规则失败，仅证明局部描述问题" if direct_issue else
                                         "有来源明确的观测，尚不能证明因果" if supporting else "只有症状或缺少直接证据",
                     "verification_action": spec["action"],
                     "causal_claim": False, "urdf_design_fault_confirmed": False}
        candidates.append(candidate)
        edges.append({"from": "symptom", "to": cause, "relation": "consider"})
        for eid in supporting:
            edges.append({"from": eid, "to": cause, "relation": "supports"})
        for eid in counter:
            edges.append({"from": eid, "to": cause, "relation": "contradicts"})
        edges.append({"from": cause, "to": f"action:{cause}", "relation": "verify_with"})
    return {"schema_version": 1, "case_id": case_id, "category": category,
            "symptom": symptom, "performance_is_real_observation": underperformed and not fixture_only,
            "comparison_matched": comparable, "skill_summary": skill_summary,
            "evidence": evidence, "candidate_causes": candidates, "edges": edges,
            "limits": ["相关性不证明机械因果", "URDF 结构检查不证明强化学习可训练性",
                       "fixture 结果不能作为真实参考成绩"] if fixture_only else
                      ["相关性不证明机械因果", "URDF 结构检查不证明强化学习可训练性"]}
