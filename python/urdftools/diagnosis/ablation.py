"""D01: one-variable CAD leg ablation and externally reported retest.

Real build123d/OCP B-rep mass properties; no RL training or hardware claims.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from urdftools.modeling.core import build_part
from urdftools.cad.mass_properties import calculate_solid_mass_properties
from urdftools.results.compare import compare_conditions, compare_success

ID = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")


class AblationError(ValueError):
    pass


def _positive(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise AblationError(f"{name} must be finite and positive")
    return float(value)


def _fmt(x):
    return format(float(x), ".15g")


def _part(length, width, thickness, density):
    recipe = {"profile": {"kind": "rectangle", "width_mm": length, "height_mm": width},
              "operation": {"kind": "extrude", "distance_mm": thickness}}
    solid = build_part(recipe)
    mass = calculate_solid_mass_properties(solid.wrapped, density, name="leg")
    if mass["status"] != "known":
        raise AblationError("CAD solid has no exact physical properties")
    lm = length / 1000
    com = [mass["center_of_mass_m"][0] + lm / 2,
           mass["center_of_mass_m"][1], mass["center_of_mass_m"][2]]
    root = ET.Element("robot", name="d01_parametric_leg")
    base = ET.SubElement(root, "link", name="base")
    inertial = ET.SubElement(base, "inertial")
    ET.SubElement(inertial, "mass", value="1")
    ET.SubElement(inertial, "inertia", ixx="0.01", iyy="0.01", izz="0.01", ixy="0", ixz="0", iyz="0")
    leg = ET.SubElement(root, "link", name="leg")
    inertial = ET.SubElement(leg, "inertial")
    ET.SubElement(inertial, "origin", xyz=" ".join(map(_fmt, com)), rpy="0 0 0")
    ET.SubElement(inertial, "mass", value=_fmt(mass["mass_kg"]))
    I = mass["inertia_com_kg_m2"]
    ET.SubElement(inertial, "inertia", ixx=_fmt(I[0][0]), ixy=_fmt(I[0][1]),
                  ixz=_fmt(I[0][2]), iyy=_fmt(I[1][1]), iyz=_fmt(I[1][2]), izz=_fmt(I[2][2]))
    for kind in ("visual", "collision"):
        element = ET.SubElement(leg, kind)
        ET.SubElement(element, "origin", xyz=f"{_fmt(lm/2)} 0 {_fmt(thickness/2000)}", rpy="0 0 0")
        ET.SubElement(ET.SubElement(element, "geometry"), "box",
                      size=" ".join(map(_fmt, (lm, width/1000, thickness/1000))))
    hip = ET.SubElement(root, "joint", name="hip", type="revolute")
    ET.SubElement(hip, "parent", link="base")
    ET.SubElement(hip, "child", link="leg")
    ET.SubElement(hip, "origin", xyz="0 0 0", rpy="0 0 0")
    ET.SubElement(hip, "axis", xyz="0 1 0")
    ET.SubElement(hip, "limit", lower="-1", upper="1", effort="10", velocity="3")
    ET.SubElement(root, "link", name="foot_frame")
    foot = ET.SubElement(root, "joint", name="distal_frame", type="fixed")
    ET.SubElement(foot, "parent", link="leg")
    ET.SubElement(foot, "child", link="foot_frame")
    ET.SubElement(foot, "origin", xyz=f"{_fmt(lm)} 0 0", rpy="0 0 0")
    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return {"urdf_xml": xml.decode(), "urdf_sha256": hashlib.sha256(xml).hexdigest(),
            "length_m": lm, "mass_kg": mass["mass_kg"], "volume_m3": mass["volume_m3"],
            "com_link_m": com, "inertia_com_kg_m2": I,
            "hip_frame_parent_xyz_m": [0, 0, 0], "distal_frame_leg_xyz_m": [lm, 0, 0],
            "cad_to_link_translation_m": [lm/2, 0, 0], "cad_recipe": recipe,
            "density_kg_m3": density}


def propose_leg_length(case_id, evidence_ids, *, length_mm, variant_length_mm,
                       width_mm, thickness_mm, density_kg_m3, protocol, train_seeds, eval_seeds):
    if not isinstance(case_id, str) or not ID.fullmatch(case_id):
        raise AblationError("Invalid case_id")
    if not isinstance(evidence_ids, list) or not evidence_ids or len(evidence_ids) > 32 or (
        any(not isinstance(e, str) or not ID.fullmatch(e) for e in evidence_ids)
    ) or len(set(evidence_ids)) != len(evidence_ids):
        raise AblationError("Unique diagnosis evidence IDs required")
    length = _positive(length_mm, "length_mm")
    changed = _positive(variant_length_mm, "variant_length_mm")
    width = _positive(width_mm, "width_mm")
    thickness = _positive(thickness_mm, "thickness_mm")
    density = _positive(density_kg_m3, "density_kg_m3")
    if math.isclose(length, changed) or not .5 <= changed/length <= 1.5:
        raise AblationError("Variant length must differ and be within 0.5x..1.5x")
    for name, seeds in (("train", train_seeds), ("eval", eval_seeds)):
        if not isinstance(seeds, list) or not seeds or len(seeds) > 256 or (
            any(type(v) is not int or v < 0 for v in seeds)
        ) or len(set(seeds)) != len(seeds):
            raise AblationError(f"Invalid {name} seeds")
    if len(train_seeds) < 3 or set(train_seeds) & set(eval_seeds):
        raise AblationError("Need 3+ independent training seeds and held-out evaluation seeds")
    if not isinstance(protocol, dict) or compare_conditions(protocol, protocol)["status"] != "matched":
        raise AblationError("Complete comparison protocol required")
    if protocol.get("paired_seed_design") is not True:
        raise AblationError("Paired training seed design required")
    return {"schema_version": 1, "case_id": case_id, "status": "proposed",
            "source_evidence_ids": list(evidence_ids),
            "single_variable": {"part": "leg", "parameter": "length",
                                "baseline_mm": length, "variant_mm": changed,
                                "unchanged_width_mm": width, "unchanged_thickness_mm": thickness,
                                "unchanged_density_kg_m3": density},
            "baseline": _part(length, width, thickness, density),
            "variant": _part(changed, width, thickness, density),
            "external_retest": {"protocol": copy.deepcopy(protocol),
                                "train_seeds": sorted(train_seeds),
                                "heldout_eval_seeds": sorted(eval_seeds),
                                "execution": "external_only_not_executed"},
            "limitations": ["Parametric synthetic leg, not user's physical robot",
                            "Static CAD intervention does not prove RL or hardware causality"]}


def _read_retest(path, expected_hash, plan):
    raw = Path(path).read_bytes()
    if len(raw) > 4*1024*1024:
        raise AblationError("Retest file too large")
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise AblationError("Invalid retest JSON") from exc
    required = {"schema_version", "origin", "verification", "review_evidence_id",
                "model_sha256", "protocol", "train_runs", "evaluation_seeds"}
    if not isinstance(doc, dict) or set(doc) != required or doc["schema_version"] != 1:
        raise AblationError("Versioned retest schema required")
    if doc["model_sha256"] != expected_hash:
        raise AblationError("Retest model SHA does not match CAD URDF")
    if doc["origin"] not in ("user_upload", "public_import", "synthetic_fixture") or doc["verification"] not in (
        "unverified", "schema_valid", "protocol_reviewed", "verified_reference"
    ):
        raise AblationError("Invalid provenance")
    review = doc["review_evidence_id"]
    if not isinstance(review, str) or (review and not ID.fullmatch(review)):
        raise AblationError("Invalid review evidence ID")
    if doc["evaluation_seeds"] != plan["external_retest"]["heldout_eval_seeds"]:
        raise AblationError("Held-out evaluation seeds differ")
    runs = doc["train_runs"]
    if not isinstance(runs, list) or any(not isinstance(row, dict) for row in runs) or sorted(
        row.get("train_seed") for row in runs
    ) != plan["external_retest"]["train_seeds"]:
        raise AblationError("Training seeds differ from preregistration")
    return doc, hashlib.sha256(raw).hexdigest()


def assess_external_retest(plan, baseline_path, variant_path, *, verified_source_hashes=None):
    """Read on-disk files and compare independent-seed results.

    Self-declared review metadata never unlocks observed_local_effect. The
    trusted caller must independently supply both reviewed source SHA-256s;
    without a verified importer/audit source the outcome stays proposed.
    """
    if not isinstance(plan, dict) or plan.get("status") != "proposed" or plan.get("schema_version") != 1:
        raise AblationError("Preregistered proposal required")
    base, bsha = _read_retest(baseline_path, plan["baseline"]["urdf_sha256"], plan)
    changed, csha = _read_retest(variant_path, plan["variant"]["urdf_sha256"], plan)
    expected = plan["external_retest"]["protocol"]
    comparison = compare_success(base["protocol"], changed["protocol"],
                                 base["train_runs"], changed["train_runs"])
    reasons = []
    if any(compare_conditions(expected, doc["protocol"])["status"] != "matched" for doc in (base, changed)):
        reasons.append("Protocol differs from preregistration")
    if comparison["comparability"]["status"] != "matched":
        reasons.append("Incomparable protocols")
    if any(doc["origin"] == "synthetic_fixture" for doc in (base, changed)):
        reasons.append("Synthetic fixture cannot establish external effect")
    if any(doc["verification"] not in ("protocol_reviewed", "verified_reference") or
           not doc["review_evidence_id"] for doc in (base, changed)):
        reasons.append("Independent review evidence missing")
    if not isinstance(verified_source_hashes, (set, frozenset)) or not {bsha, csha} <= verified_source_hashes:
        reasons.append("Trusted importer review attestation missing")
    if any(row["status"] != "completed" for doc in (base, changed) for row in doc["train_runs"]):
        reasons.append("Failed or missing training seed")
    status = "observed_local_effect" if not reasons and comparison["status"] == "compared" else "proposed"
    return {"schema_version": 1, "case_id": plan["case_id"], "status": status,
            "baseline_source_sha256": bsha, "variant_source_sha256": csha,
            "review_evidence_ids": [base["review_evidence_id"], changed["review_evidence_id"]],
            "comparison": comparison, "reasons": reasons,
            "claim_scope": "externally reported protocol-local effect; never physical hardware causality"
            if status == "observed_local_effect" else "no verified local intervention effect"}
