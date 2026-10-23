"""Pinned Unitree G1/H1 source and installed skill smoke; negatives are synthetic."""
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"python"))
from urdftools.evaluation.skills import discover_skills, run_skill

models = {
    "g1": ("tests/fixtures/S06/reference_models/g1_description/g1_29dof.urdf",
           "e1dc89366bf96aa33ba4ef211884f6d81320ddd2ac6f8b1ad82986e64008be31"),
    "h1": ("tests/fixtures/R02/h1_description/urdf/h1.urdf",
           "ebd495cba7887406c406b8441a5e2dd712f8da91dcb60e7b099cbfa3adf2efa5"),
}
skill = discover_skills(ROOT/"skills")["humanoid_structure"]
results = {}
for name, (relpath, expected_hash) in models.items():
    raw = (ROOT/relpath).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected_hash
    report = run_skill(skill, {"humanoid_scan": {"urdf_xml": raw.decode()}})
    result = report["results"][0]
    assert report["passed"] and result["counts"]["fail"] == 0
    assert result["counts"]["unknown"] >= 2
    assert result["profile"] == name
    assert any(c["rule_id"]=="actuated_dof" and c["observed"]==(29 if name=="g1" else 19)
               for c in result["checks"])
    results[name] = {
        "source_kind": "pinned_vendor_urdf",
        "source_sha256": result["source_sha256"],
        "skill_manifest_sha256": report["manifest_sha256"],
        "counts": result["counts"],
        "declared_mass": next(c["observed"] for c in result["checks"] if c["rule_id"]=="declared_mass_sum"),
        "unknown_rules": [c["rule_id"] for c in result["checks"] if c["status"]=="unknown"],
    }
root = ET.fromstring((ROOT/models["h1"][0]).read_bytes())
link = root.find("./link[@name='right_ankle_link']")
for collision in list(link.findall("collision")):
    link.remove(collision)
mutant = run_skill(skill, {"humanoid_scan": {"urdf_xml": ET.tostring(root, encoding="unicode")}})
assert not mutant["passed"]
assert any(c["rule_id"]=="sole_collision" and c["object"]=="right_ankle_link" and c["status"]=="fail"
           for c in mutant["results"][0]["checks"])
results["synthetic_mutation"] = {
    "source_kind": "synthetic_fixture",
    "mutation": "H1 right ankle sole collision removed in memory",
    "counts": mutant["results"][0]["counts"],
}
out = ROOT/"artifacts/K02/humanoid-report.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({
    "source": "Unitree pinned G1/H1 original URDF; synthetic in-memory negative only",
    "models": results,
    "limitations": "No measured robot contact forces, motor calibration, true mass or dynamic gait",
}, indent=2)+"\n")
print(json.dumps({"models": results, "report": str(out.relative_to(ROOT))}, indent=2))
