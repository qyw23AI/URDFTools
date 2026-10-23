#!/usr/bin/env python3
"""E02 real MuJoCo CPU mass matrix / gravity cross-check, never runs training."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from urdftools.evaluation.dynamics import PlanarArm

ARM = PlanarArm()
POSES = [(0.0, 0.0), (0.7, -0.4), (-0.9, 0.5), (0.3, 1.1)]


def make_robot(path: Path, wrong_elbow_frame=False, fixed_imu=False):
    root = ET.Element("robot", name="synthetic_two_link_dynamics")
    ET.SubElement(root, "link", name="base")
    for name, mass, length, width, com in (
        ("link1", ARM.mass1_kg, 0.4, 0.08, ARM.com1_m),
        ("link2", ARM.mass2_kg, 0.3, 0.1, ARM.com2_m),
    ):
        link = ET.SubElement(root, "link", name=name)
        inertial = ET.SubElement(link, "inertial")
        ET.SubElement(inertial, "origin", xyz=f"0 0 {-com}", rpy="0 0 0")
        ET.SubElement(inertial, "mass", value=str(mass))
        ixx = mass * (width**2 + length**2) / 12
        iyy = ixx
        izz = mass * (2 * width**2) / 12
        ET.SubElement(inertial, "inertia", ixx=str(ixx), ixy="0", ixz="0",
                      iyy=str(iyy), iyz="0", izz=str(izz))
        visual = ET.SubElement(link, "visual")
        ET.SubElement(visual, "origin", xyz=f"0 0 {-com}", rpy="0 0 0")
        ET.SubElement(ET.SubElement(visual, "geometry"), "box",
                      size=f"{width} {width} {length}")
    for name, parent, child, z in (
        ("shoulder", "base", "link1", 0.0),
        ("elbow", "link1", "link2", ARM.length1_m if wrong_elbow_frame else -ARM.length1_m),
    ):
        joint = ET.SubElement(root, "joint", name=name, type="revolute")
        ET.SubElement(joint, "parent", link=parent)
        ET.SubElement(joint, "child", link=child)
        ET.SubElement(joint, "origin", xyz=f"0 0 {z}", rpy="0 0 0")
        ET.SubElement(joint, "axis", xyz="0 1 0")
        ET.SubElement(joint, "limit", lower="-2", upper="2", effort="10", velocity="3")
    if fixed_imu:
        ET.SubElement(root, "link", name="imu_frame")
        joint = ET.SubElement(root, "joint", name="imu_mount", type="fixed")
        ET.SubElement(joint, "parent", link="link2")
        ET.SubElement(joint, "child", link="imu_frame")
        ET.SubElement(joint, "origin", xyz="0 0 0.06", rpy="0 0 0")
    ET.indent(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_urdf(path: Path):
    model = mujoco.MjModel.from_xml_path(str(path))
    assert (model.nq, model.nv) == (2, 2), (path, model.nq, model.nv)
    np.testing.assert_allclose(model.opt.gravity, [0, 0, -9.81], atol=1e-12)
    data = mujoco.MjData(model)
    findings = []
    for q1, q2 in POSES:
        mujoco.mj_resetData(model, data)
        data.qpos[:] = (q1, q2)
        data.qvel[:] = 0
        mujoco.mj_forward(model, data)
        mass_matrix = np.zeros((2, 2))
        mujoco.mj_fullM(model, data, mass_matrix)
        expected_mass = np.array(ARM.mass_matrix(q1, q2))
        expected_bias = np.array(ARM.gravity_generalized(q1, q2))
        findings.append({
            "q_rad": [q1, q2],
            "mass_matrix_kg_m2": mass_matrix.tolist(),
            "analytic_mass_matrix_kg_m2": expected_mass.tolist(),
            "gravity_n_m": data.qfrc_bias.tolist(),
            "analytic_gravity_n_m": expected_bias.tolist(),
            "mass_error_max": float(np.max(np.abs(mass_matrix - expected_mass))),
            "gravity_error_max": float(np.max(np.abs(data.qfrc_bias - expected_bias))),
            "evidence": "MuJoCo mj_fullM, mj_forward(qvel=0) versus independent analytic 2R model",
        })
    return {"source": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "engine": f"mujoco-{mujoco.__version__}", "nq": model.nq, "nv": model.nv,
            "cases": findings,
            "max_mass_error": max(p["mass_error_max"] for p in findings),
            "max_gravity_error": max(p["gravity_error_max"] for p in findings)}


def main():
    path = ROOT / "artifacts/E02"
    normal = path / "two_link.urdf"
    wrong = path / "two_link_bad_elbow_frame.urdf"
    fixed = path / "two_link_fixed_sensor.urdf"
    make_robot(normal)
    make_robot(wrong, wrong_elbow_frame=True)
    make_robot(fixed, fixed_imu=True)
    nominal = evaluate_urdf(normal)
    bad = evaluate_urdf(wrong)
    with_fixed = evaluate_urdf(fixed)
    tolerance_mass = 1e-8
    tolerance_gravity = 1e-8
    assert nominal["max_mass_error"] < tolerance_mass, nominal
    assert nominal["max_gravity_error"] < tolerance_gravity, nominal
    assert with_fixed["max_mass_error"] < tolerance_mass, with_fixed
    assert with_fixed["max_gravity_error"] < tolerance_gravity, with_fixed
    assert bad["max_mass_error"] > 1e-2, bad
    assert bad["max_gravity_error"] > 1e-2, bad
    report = {
        "status": "passed", "origin": "synthetic_fixture",
        "reference": "independent planar two-link Lagrangian kinetic/potential energy",
        "normal": nominal, "wrong_joint_frame": bad, "fixed_massless_sensor": with_fixed,
        "limits": "This numerical cross-check does not validate any physical robot or RL policy.",
    }
    (path / "dynamics-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "passed", "poses": len(POSES), "models": 3,
                      "normal_mass_error": nominal["max_mass_error"],
                      "normal_gravity_error": nominal["max_gravity_error"],
                      "bad_frame_mass_error": bad["max_mass_error"],
                      "bad_frame_gravity_error": bad["max_gravity_error"],
                      "fixed_frame_mass_error": with_fixed["max_mass_error"],
                      "artifact": "artifacts/E02/dynamics-report.json"}))


if __name__ == "__main__":
    main()
