#!/usr/bin/env python3
"""Real CAD solid recomputation and synthetic external result negative gate."""
import json
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"python"))
from urdftools.diagnosis.ablation import propose_leg_length, assess_external_retest

TERRAIN = {"terrain_kind":"step","terrain_version":"v1","scale_mode":"physical_m",
           "terrain_size":0.2,"terrain_size_unit":"m","push_force_n":0,
           "push_duration_s":0,"train_seeds":[1,2,3],"test_seeds":[101,102],
           "success_definition":"cross without fall"}
PROTOCOL = {"robot_category":"quadruped","algorithm":"ppo","algorithm_version":"1",
            "protocol":"stairs","protocol_version":"1","reward_sha256":"a"*64,
            "track":"fixed_recipe","recipe_sha256":"b"*64,"budget_steps":100000,
            "paired_seed_design":True,"terrain":TERRAIN}

p = propose_leg_length("d01-smoke", ["evidence:d00"], length_mm=100,
                       variant_length_mm=120, width_mm=20, thickness_mm=10,
                       density_kg_m3=2700, protocol=PROTOCOL,
                       train_seeds=[1,2,3], eval_seeds=[101,102])
def summary(part, success):
    return {"schema_version":1,"origin":"synthetic_fixture","verification":"schema_valid",
            "review_evidence_id":"","model_sha256":part["urdf_sha256"],
            "protocol":PROTOCOL,"evaluation_seeds":[101,102],
            "train_runs":[{"train_seed":seed,"status":"completed",
                           "episodes":[success,success]} for seed in [1,2,3]]}

with tempfile.TemporaryDirectory() as d:
    left, right = Path(d)/"baseline.json", Path(d)/"variant.json"
    left.write_text(json.dumps(summary(p["baseline"],True)))
    right.write_text(json.dumps(summary(p["variant"],False)))
    outcome = assess_external_retest(p,left,right)
    assert outcome["status"] == "proposed"
    assert p["baseline"]["mass_kg"] < p["variant"]["mass_kg"]
    assert ET.fromstring(p["variant"]["urdf_xml"]).find("./joint[@name='distal_frame']") is not None
    dest = ROOT/"artifacts"/"D01"
    dest.mkdir(parents=True,exist_ok=True)
    (dest/"parametric-leg-report.json").write_text(json.dumps(
        {"plan":p,"fixture_comparison":outcome},ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"baseline_mass_kg":p["baseline"]["mass_kg"],
                      "variant_mass_kg":p["variant"]["mass_kg"],
                      "baseline_iyy":p["baseline"]["inertia_com_kg_m2"][1][1],
                      "variant_iyy":p["variant"]["inertia_com_kg_m2"][1][1],
                      "fixture_status":outcome["status"],
                      "output":str(dest/"parametric-leg-report.json")}))
