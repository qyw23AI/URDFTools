"""K01 pinned real vendor URDF audit; mutations are test-only, never source writes."""
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"python"))
from urdftools.evaluation.skills import discover_skills, run_skill

vendor = json.loads((ROOT/"tests/fixtures/S06/reference_models.json").read_text())
go2 = vendor["models"]["go2"]
paths = {"a1": ROOT/"tests/fixtures/S06/a1_description/a1.urdf",
         "go2": ROOT/go2["fixture_dir"]/go2["urdf_path"]}
catalog = discover_skills(ROOT/"skills")
skill = catalog["quadruped_structure"]
results = {}
for name, path in paths.items():
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "b5feb8464ed82f6f6ac1905e915d5177b887e6f338e0f8f810da35fd4395a607"
        if name=="a1" else go2["fixture_urdf_sha256"])
    report = run_skill(skill, {"quadruped_scan": {"urdf_xml": raw.decode()}})
    result = report["results"][0]
    assert report["passed"] and result["counts"]["fail"]==0
    assert result["counts"]["unknown"]>=2
    assert next(x for x in result["checks"] if x["rule_id"]=="actuated_dof")["observed"]==12
    results[name] = {"source_sha256": result["source_sha256"],
                     "skill_manifest_sha256": report["manifest_sha256"],
                     "counts": result["counts"],
                     "footprint": next(x["observed"] for x in result["checks"]
                                       if x["rule_id"]=="nominal_foot_spread"),
                     "unknown": [x["rule_id"] for x in result["checks"] if x["status"]=="unknown"]}
# Explicit mutation: remove one real foot collision from an in-memory copy.
tree = ET.fromstring(paths["go2"].read_bytes())
foot = tree.find("./link[@name='FL_foot']")
for collision in list(foot.findall("collision")):
    foot.remove(collision)
mutated = run_skill(skill, {"quadruped_scan": {"urdf_xml": ET.tostring(tree, encoding="unicode")}})
assert not mutated["passed"]
assert any(x["rule_id"]=="foot_collision" and x["object"]=="FL_foot" and x["status"]=="fail"
           for x in mutated["results"][0]["checks"])
results["synthetic_mutation"] = {"type": "remove_FL_foot_collision",
                                 "counts": mutated["results"][0]["counts"],
                                 "source_kind": "synthetic_fixture"}
out = ROOT/"artifacts/K01/quadruped-report.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"source": "Unitree pinned URDF; in-memory negative mutation synthetic",
                           "models": results,
                           "limitations": "No hardware verification, motor curves, contact trajectories or gait"}, indent=2)+"\n")
print(json.dumps({"models": results, "report": str(out.relative_to(ROOT))}, indent=2))
