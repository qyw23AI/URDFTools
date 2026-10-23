"""Auditable MuJoCo URDF compilation with explicit DOF/body/loss provenance."""
from __future__ import annotations

import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco

from .static import scan_urdf

SINGLE_DOF = {"continuous", "prismatic", "revolute"}
# Do not infer missing actuator/contact profiles, or silently repair bad inertias.


def compile_report(path: str | Path) -> dict:
    path = Path(path)
    raw = path.read_bytes()
    hash_value = hashlib.sha256(raw).hexdigest()
    root = ET.fromstring(raw)
    if root.tag != "robot":
        raise ValueError("URDF robot root required")
    links = root.findall("link")
    joints = root.findall("joint")
    source_masses = {}
    for link in links:
        name = link.get("name")
        mass_node = link.find("./inertial/mass")
        if mass_node is not None and mass_node.get("value") is not None:
            source_masses[name] = float(mass_node.get("value"))
        else:
            source_masses[name] = None
    parents = {j.find("child").get("link") for j in joints if j.find("child") is not None}
    roots = [link.get("name") for link in links if link.get("name") not in parents]

    result = {
        "source_file": str(path), "source_sha256": hash_value,
        "engine": "MuJoCo", "engine_version": mujoco.__version__,
        "compiler": {
            "adapter": "mujoco.MjModel.from_xml_path/native URDF",
            "source_modifications": [],
            "inertia_repairs": "none",
            "balanceinertia": "not enabled by URDFTools",
            "contact_profile": "not provided: engine defaults",
            "actuator_profile": "not provided: URDF limits are not motor curves",
            "free_base": False,
        },
        "source": {
            "links": len(links), "joints": len(joints),
            "dof_1d_joints": sum(j.get("type") in SINGLE_DOF for j in joints),
            "roots": roots, "total_declared_mass_kg": (
                sum(m for m in source_masses.values() if m is not None)
                if all(m is not None for m in source_masses.values()) else None
            ),
        },
    }
    semantic = scan_urdf(path)
    fatal = [f for f in semantic["findings"] if f["severity"] == "error"]
    if fatal:
        result["preflight_failures"] = fatal
        result["status"] = "rejected"
        result["reason"] = "Static physical/URDF preflight detected errors; no balancing or clamping performed."
        return result
    try:
        model = mujoco.MjModel.from_xml_path(str(path))
    except ValueError as exc:
        result["status"] = "rejected"
        result["reason"] = str(exc).splitlines()[0]
        return result

    compiled_bodies = {
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i): {
            "body_id": i, "mass_kg": float(model.body_mass[i]),
        } for i in range(1, model.nbody)
    }
    compiled_joints = {
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i): {
            "joint_id": i,
            "qpos_address": int(model.jnt_qposadr[i]),
            "dof_address": int(model.jnt_dofadr[i]),
        } for i in range(model.njnt)
    }
    link_mapping = {
        name: ({
            "compiled_body": name,
            "status": "preserved",
            "mass_kg": body["mass_kg"],
        } if (body := compiled_bodies.get(name)) is not None else {
            "compiled_body": None,
            "status": "not_independent_body",
            "original_mass_kg": source_masses[name],
        })
        for name in source_masses
    }
    joint_mapping = {
        j.get("name"): ({
            "compiled_joint": j.get("name"),
            "status": "preserved",
            **compiled_joints[j.get("name")],
        } if j.get("name") in compiled_joints else {
            "compiled_joint": None,
            "status": "fixed_or_fused" if j.get("type") == "fixed" else "missing_in_engine",
        })
        for j in joints
    }
    expected_dof = sum(j.get("type") in SINGLE_DOF for j in joints)
    compiled_mass = float(model.body_mass.sum())
    source_mass = result["source"]["total_declared_mass_kg"]
    losses = []
    for name, info in link_mapping.items():
        if info["status"] == "not_independent_body":
            losses.append({
                "kind": "link_not_standalone", "source_link": name,
                "original_mass_kg": source_masses[name],
                "may_be_fused_or_ignored": True,
            })
    for joint in joints:
        name = joint.get("name")
        if name not in compiled_joints:
            losses.append({"kind": "joint_removed_or_fused", "source_joint": name,
                           "joint_type": joint.get("type")})
    if expected_dof != model.nv:
        losses.append({"kind": "dof_mismatch", "source": expected_dof, "compiled": model.nv})
    if source_mass is not None and abs(source_mass - compiled_mass) > 1e-9:
        losses.append({
            "kind": "source_vs_compiled_mass_difference",
            "declared_kg": source_mass, "compiled_kg": compiled_mass,
            "delta_kg": source_mass - compiled_mass,
            "note": "Fixed-base roots may be excluded by MuJoCo; no floating base added.",
        })
    result.update({
        "status": "compiled_with_losses" if losses else "compiled",
        "compiled": {
            "nbody_including_world": model.nbody, "njnt": model.njnt,
            "nq": model.nq, "nv": model.nv, "body_mass_sum_kg": compiled_mass,
        },
        "link_mapping": link_mapping, "joint_mapping": joint_mapping,
        "losses": losses, "training_ready": False,
    })
    return result
