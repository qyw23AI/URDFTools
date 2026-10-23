#!/usr/bin/env python3
"""R01 pinned Unitree A1/Go2: full source bundle verification + explicit collision-only MuJoCo copies."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET

import mujoco

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"python"))
from urdftools.importers.service import ImportService
from urdftools.reference.registry import ModelRegistry

SOURCE=ROOT/"tests/fixtures/S06"
STAMP=json.loads((SOURCE/"manifest.json").read_text())
GO2_STAMP=json.loads((SOURCE/"reference_models.json").read_text())
COMMIT=STAMP["source_commit"]
SPECS={
 "a1":{"folder":SOURCE/"a1_description","urdf":"a1.urdf",
       "expected_sha256":STAMP["models"]["unitree_a1"]["urdf_sha256"],
       "links":23,"joints":22,"active":12,
       "license":SOURCE/"a1_description/LICENSE"},
 "go2":{"folder":SOURCE/"reference_models/go2_description","urdf":"urdf/go2_description.urdf",
        "expected_sha256":GO2_STAMP["models"]["go2"]["source_urdf_sha256"],
        "links":42,"joints":41,"active":12,
        "license":SOURCE/"UNITREE_LICENSE"},
}


def analyze(label: str, dest: Path) -> dict:
    spec=SPECS[label]
    original=spec["folder"]/spec["urdf"]
    raw=original.read_bytes()
    sha=hashlib.sha256(raw).hexdigest()
    assert sha==spec["expected_sha256"],(label,sha)
    lic_bytes=spec["license"].read_bytes()
    lic_sha=hashlib.sha256(lic_bytes).hexdigest()
    assert b"BSD 3-Clause" in lic_bytes
    root=ET.fromstring(raw)
    assert len(root.findall("link"))==spec["links"]
    assert len(root.findall("joint"))==spec["joints"]
    movable=[j.get("name") for j in root.findall("joint") if j.get("type")!="fixed"]
    assert len(movable)==spec["active"]
    # Validate all original referenced meshes via the product's real ingestion pipeline.
    with tempfile.TemporaryDirectory(prefix=f"r01-import-{label}-") as folder:
        imported=ImportService(Path(folder)/"imports").ingest(spec["folder"])
        assert imported["status"]=="ready", imported
        assert len(imported["models"])==1
        assert imported["models"][0]["status"]=="ready"
        asset_count=len(imported["assets"])
        assert asset_count>=7
    # Original file is always retained. If the engine rejects unsupported visual syntax,
    # derive a collision/inertia-only URDF and list every dropped <visual>.
    raw_error=None
    try:
        raw_model=mujoco.MjModel.from_xml_path(str(original))
    except ValueError as exc:
        raw_error=str(exc).splitlines()[0]
        raw_model=None
    dropped=[]
    model_path=original
    if raw_model is None:
        derived=ET.fromstring(raw)
        for link in derived.findall("link"):
            for visual in link.findall("visual"):
                link.remove(visual)
                dropped.append({"link":link.get("name"),"kind":"visual",
                                "reason":"MuJoCo native parser could not load source URDF visual element"})
        assert dropped, raw_error
        model_path=dest/(label+"_collision_inertia_only.urdf")
        model_path.write_bytes(ET.tostring(derived,encoding="utf-8",xml_declaration=True))
    model=mujoco.MjModel.from_xml_path(str(model_path))
    assert model.nv==spec["active"],(label,model.nv)
    model_joint_names={mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_JOINT,i)
                       for i in range(model.njnt)}
    assert set(movable)==model_joint_names, (label, sorted(set(movable)-model_joint_names))
    mappings={j:{"mujoco_joint":j,"status":"preserved"} for j in movable}
    model_source_sha=hashlib.sha256(model_path.read_bytes()).hexdigest()
    assert original.read_bytes()==raw, "source vendor URDF mutated"
    return {
        "model":label,"source_repository":STAMP["source_repository"],
        "source_commit":COMMIT,"source":str(original.relative_to(ROOT)),
        "source_sha256":sha,"source_links":spec["links"],"source_joints":spec["joints"],
        "source_1d_dof":spec["active"],"source_asset_count":asset_count,
        "license":"BSD-3-Clause","license_file":str(spec["license"].relative_to(ROOT)),
        "license_sha256":lic_sha,"packaged_in_distribution":False,
        "engine":"MuJoCo","engine_version":mujoco.__version__,
        "engine_original_source_status":"compiled" if raw_model is not None else "rejected",
        "engine_original_source_error":raw_error,
        "simulation_derived_file":str(model_path.relative_to(ROOT) if model_path.is_relative_to(ROOT) else model_path),
        "simulation_derived_sha256":model_source_sha,
        "removed_visual_elements":dropped,"mass_kg_in_engine":float(model.body_mass.sum()),
        "compiled_dof":model.nv,"mappings":mappings,
        "contact_profile":"unknown","actuator_profile":"unknown",
        "source_hardware_calibration":"unverified",
        "loss_notice":"Unmodified source used for viewer; collision-only derivative loses visual assets."
                      if dropped else "Original URDF accepted by native engine; fixed-root fusion still applies.",
        "training_ready":False,
    }


def main():
    dest=ROOT/"artifacts/R01"
    dest.mkdir(parents=True,exist_ok=True)
    results={label:analyze(label,dest) for label in SPECS}
    # Register canonical source URDF only, without pretending cached mesh assets are bundled.
    with tempfile.TemporaryDirectory(prefix="r01-register-") as temp:
        with ModelRegistry(Path(temp)/"models") as reg:
            for label,spec in SPECS.items():
                data=results[label]
                registered=reg.import_file(spec["folder"]/spec["urdf"],
                                            name="unitree-"+label,version=COMMIT[:12],
                                            category="quadruped",origin="public_import",
                                            source_uri=STAMP["source_repository"]+"@"+COMMIT,
                                            license_id="BSD-3-Clause",
                                            expected_sha256=data["source_sha256"])
                assert not registered["bundling_permitted"] and not registered["reference_performance"]
                data["registry_id"]=registered["id"]
    report={"status":"passed","origin":"upstream_open_source_reference_model",
            "pinned_commit":COMMIT,"models":results,
            "limits":"No original files rewritten, no motor curves or independent hardware calibration."}
    (dest/"vendor-model-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"status":"passed","models":list(results),"dof":[results[v]["compiled_dof"] for v in results],
                      "go2_visual_elements_dropped":len(results["go2"]["removed_visual_elements"]),
                      "artifacts":"artifacts/R01/vendor-model-report.json"}))


if __name__=="__main__":
    main()
