#!/usr/bin/env python3
"""R02: verify pinned Unitree G1/H1 source bundles, humanoid joint maps and MuJoCo compilation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET

import mujoco

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from urdftools.importers.service import ImportService
from urdftools.reference.registry import ModelRegistry

FIXTURES = ROOT / "tests/fixtures"
G1_MANIFEST = json.loads((FIXTURES / "S06/reference_models.json").read_text())
H1_MANIFEST = json.loads((FIXTURES / "R02/h1_source_manifest.json").read_text())
COMMIT = "5994d4faef0a9cadd3287f8de0199a67eeb2a259"
assert G1_MANIFEST["commit"] == H1_MANIFEST["source_commit"] == COMMIT
LICENSE = FIXTURES / "R02/UNITREE_LICENSE"
SPECS = {
    "g1": {
        "folder": FIXTURES / "S06/reference_models/g1_description",
        "urdf": "g1_29dof.urdf",
        "sha256": G1_MANIFEST["models"]["g1"]["source_urdf_sha256"],
        "links": 40, "joints": 39, "dof": 29,
        "leg_dof": 12, "arm_dof": 14, "trunk_dof": 3,
    },
    "h1": {
        "folder": FIXTURES / "R02/h1_description",
        "urdf": "urdf/h1.urdf",
        "sha256": "ebd495cba7887406c406b8441a5e2dd712f8da91dcb60e7b099cbfa3adf2efa5",
        "links": 25, "joints": 24, "dof": 19,
        "leg_dof": 10, "arm_dof": 8, "trunk_dof": 1,
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_source(label: str) -> dict:
    """Parse and verify immutable vendor data before attempting engine conversion."""
    spec = SPECS[label]
    original = spec["folder"] / spec["urdf"]
    raw = original.read_bytes()
    assert len(raw) <= 4 * 1024 * 1024
    assert b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper()
    assert hashlib.sha256(raw).hexdigest() == spec["sha256"]
    assert sha256(LICENSE) == H1_MANIFEST["license_sha256"]
    assert b"BSD 3-Clause" in LICENSE.read_bytes()
    root = ET.fromstring(raw)
    links = root.findall("link")
    joints = root.findall("joint")
    assert len(links) == spec["links"] and len(joints) == spec["joints"]
    movable = [j for j in joints if j.get("type") not in ("fixed",)]
    names = [j.get("name") for j in movable]
    assert len(movable) == spec["dof"] and len(names) == len(set(names))
    leg = [name for name in names if name.startswith(("left_hip_", "right_hip_", "left_knee_", "right_knee_", "left_ankle_", "right_ankle_"))]
    arm = [name for name in names if name.startswith(("left_shoulder_", "right_shoulder_", "left_elbow_", "right_elbow_", "left_wrist_", "right_wrist_"))]
    trunk = [name for name in names if name.startswith(("waist_", "torso_"))]
    assert (len(leg), len(arm), len(trunk)) == (spec["leg_dof"], spec["arm_dof"], spec["trunk_dof"])
    assert len(leg) + len(arm) + len(trunk) == len(names)
    assert all(j.get("type") in ("revolute", "continuous", "prismatic") for j in movable)
    for joint in movable:
        limit = joint.find("limit")
        assert limit is not None, joint.get("name")
        assert float(limit.get("effort", "0")) > 0 and float(limit.get("velocity", "0")) > 0
    if label == "h1":
        for file in H1_MANIFEST["files"]:
            asset = spec["folder"] / file["path"]
            assert asset.is_file() and asset.stat().st_size == file["size"], file["path"]
            assert sha256(asset) == file["sha256"], file["path"]
    else:
        for file in G1_MANIFEST["models"]["g1"]["fixture_files"]:
            asset = spec["folder"] / file["path"]
            assert asset.is_file() and asset.stat().st_size == file["size"], file["path"]
            assert sha256(asset) == file["sha256"], file["path"]
    return {"source_sha256": spec["sha256"], "source_links": len(links),
            "source_joints": len(joints), "source_1d_dof": len(names),
            "joint_names": names, "joint_groups": {"legs": leg, "arms": arm, "trunk": trunk},
            "visual_elements": len(root.findall(".//visual")),
            "collision_elements": len(root.findall(".//collision")),
            "root": root, "original": original, "raw": raw}


def analyze(label: str, dest: Path) -> dict:
    src = inspect_source(label)
    spec = SPECS[label]
    with tempfile.TemporaryDirectory(prefix=f"r02-import-{label}-") as folder:
        imported = ImportService(Path(folder) / "imports").ingest(spec["folder"])
        assert imported["status"] == "ready", imported
        assert len(imported["models"]) == 1
        assert imported["models"][0]["status"] == "ready"
        assets = len(imported["assets"])
        assert assets >= 15, (label, assets)
    error = None
    dropped = []
    collision_mesh_rewrites = []
    try:
        model = mujoco.MjModel.from_xml_path(str(src["original"]))
    except (ValueError, RuntimeError) as exc:
        error = str(exc).splitlines()[0]
        model = None
    compiled_path = src["original"]
    if model is None:
        # Never rewrite the original URDF; collision/inertial semantics remain intact.
        derived = ET.fromstring(src["raw"])
        for link in derived.findall("link"):
            for visual in list(link.findall("visual")):
                link.remove(visual)
                dropped.append(link.get("name"))
        assert dropped, error
        assert len(derived.findall(".//collision")) == src["collision_elements"]
        # MuJoCo's <compiler meshdir> would duplicate meshes/ in vendor G1.
        # Keep every collision, but rebase mesh filenames to the derivative's directory.
        for compiler in derived.findall("./mujoco/compiler"):
            compiler.attrib.pop("meshdir", None)
        for mesh in derived.findall(".//collision//mesh"):
            original_name = mesh.get("filename", "")
            relative = Path(original_name)
            assert not relative.is_absolute() and ".." not in relative.parts
            asset = spec["folder"] / relative
            assert asset.is_file(), original_name
            rebased = os.path.relpath(asset, dest)
            mesh.set("filename", rebased)
            collision_mesh_rewrites.append({"source": original_name, "derived": rebased})
        compiled_path = dest / f"{label}_collision_inertia_only.urdf"
        compiled_path.write_bytes(ET.tostring(derived, encoding="utf-8", xml_declaration=True))
        model = mujoco.MjModel.from_xml_path(str(compiled_path))
    assert model.nv == spec["dof"], (label, model.nv)
    compiled_names = {mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i)
                      for i in range(model.njnt)}
    assert compiled_names == set(src["joint_names"]), (label, compiled_names ^ set(src["joint_names"]))
    assert sha256(src["original"]) == spec["sha256"]
    return {
        "model": label, "source_repository": G1_MANIFEST["repository"],
        "source_commit": COMMIT, "source": str(src["original"].relative_to(ROOT)),
        "source_sha256": src["source_sha256"], "source_links": src["source_links"],
        "source_joints": src["source_joints"], "source_1d_dof": src["source_1d_dof"],
        "joint_groups": src["joint_groups"], "source_asset_count": assets,
        "source_visual_count": src["visual_elements"],
        "source_collision_count": src["collision_elements"],
        "license": "BSD-3-Clause", "license_sha256": sha256(LICENSE),
        "packaged_in_distribution": False,
        "engine": "MuJoCo", "engine_version": mujoco.__version__,
        "engine_original_source_status": "compiled" if error is None else "rejected",
        "engine_original_source_error": error,
        "simulation_derived_file": str(compiled_path.relative_to(ROOT)),
        "simulation_derived_sha256": sha256(compiled_path),
        "removed_visual_links": dropped, "collision_mesh_path_rewrites": collision_mesh_rewrites,
        "collision_elements_preserved": True,
        "compiled_dof": model.nv, "compiled_joint_names": sorted(compiled_names),
        "mass_kg_in_engine": float(model.body_mass.sum()),
        "actuator_profile": "unknown", "contact_profile": "unknown",
        "source_hardware_calibration": "unverified", "training_ready": False,
        "loss_notice": "Removed visual nodes in a separate simulation-only copy; vendor meshes retained for viewer."
                       if dropped else "Original URDF compiled; fixed-root body fusion may affect mass.",
    }


def main() -> None:
    dest = ROOT / "artifacts/R02"
    dest.mkdir(parents=True, exist_ok=True)
    results = {label: analyze(label, dest) for label in SPECS}
    with tempfile.TemporaryDirectory(prefix="r02-register-") as tmp:
        with ModelRegistry(Path(tmp) / "models") as registry:
            for label, spec in SPECS.items():
                entry = registry.import_file(spec["folder"] / spec["urdf"],
                    name="unitree-" + label, version=COMMIT[:12], category="humanoid",
                    origin="public_import", source_uri=G1_MANIFEST["repository"] + "@" + COMMIT,
                    license_id="BSD-3-Clause", expected_sha256=results[label]["source_sha256"])
                assert not entry["bundling_permitted"] and not entry["reference_performance"]
                results[label]["registry_id"] = entry["id"]
    report = {"status": "passed", "origin": "upstream_open_source_reference_model",
              "pinned_commit": COMMIT, "models": results,
              "limits": "Static source structure and MuJoCo compilation only; no hardware, gait, actuator or training verification."}
    (dest / "vendor-model-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "passed", "models": list(results),
        "dof": {name: item["compiled_dof"] for name, item in results.items()},
        "visual_losses": {name: len(item["removed_visual_links"]) for name, item in results.items()},
        "artifact": "artifacts/R02/vendor-model-report.json"}))


if __name__ == "__main__":
    main()
