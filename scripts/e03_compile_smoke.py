#!/usr/bin/env python3
"""Independent nine-model E03 actual MuJoCo compile/audit workflow."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from urdftools.evaluation.compile import compile_report

folder=ROOT/"tests/fixtures/E00"
manifest=json.loads((folder/"manifest.json").read_text())
records={}
for case in manifest["cases"]:
    path=folder/case["file"]
    record=compile_report(path)
    assert record["source_sha256"]==hashlib.sha256(path.read_bytes()).hexdigest()
    status=record["status"]
    assert status in {"compiled","compiled_with_losses","rejected"}, (case["file"],status)
    if case["file"] in ("humanoid_negative_inertia.urdf","humanoid_triangle_violation.urdf",
                        "quadruped_zero_axis.urdf"):
        assert status=="rejected",record
    else:
        assert status!="rejected",record
    records[case["file"]]=record

for filename,dof,mass in (("quadruped_valid.urdf",8,3.2),
                          ("humanoid_valid.urdf",4,7.0)):
    result=records[filename]
    assert result["compiled"]["nv"]==dof
    assert abs(result["compiled"]["body_mass_sum_kg"]-mass)<1e-10
    assert result["link_mapping"]["torso"]["status"]=="not_independent_body"

artifact=ROOT/"artifacts/E03"
artifact.mkdir(parents=True,exist_ok=True)
report={"status":"passed","source":"synthetic_fixture","model_count":len(records),
        "results":records,"no_training_claim":True}
(artifact/"compile-map-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"status":"passed","models":len(records),"accepted":sum(r["status"]!="rejected" for r in records.values()),
                  "rejected":sum(r["status"]=="rejected" for r in records.values()),
                  "mapped_quad_dof":records["quadruped_valid.urdf"]["compiled"]["nv"],
                  "mapped_humanoid_dof":records["humanoid_valid.urdf"]["compiled"]["nv"],
                  "artifact":"artifacts/E03/compile-map-report.json"}))
