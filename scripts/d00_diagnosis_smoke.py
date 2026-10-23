#!/usr/bin/env python3
"""Real B08 import + K01/K02 skill + E04 probe evidence through D00 engine."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "scripts"), str(ROOT / "tests/b08")]
from b08_results_worker import compare_runs, import_bundle
from test_desktop_bundle import DesktopBundleTests
from urdftools.diagnosis.engine import diagnose


def main():
    output = ROOT / "artifacts/D00"
    output.mkdir(parents=True, exist_ok=True)
    probe_path = ROOT / "artifacts/E04/probe-report.json"
    probe = json.loads(probe_path.read_text())
    with tempfile.TemporaryDirectory(prefix="d00-", dir=ROOT / ".tools") as temporary:
        fixtures = DesktopBundleTests()
        fixtures.root = Path(temporary)
        store = fixtures.root / "store"
        for role in ("standard", "user"):
            import_bundle(store, fixtures.bundle("quadruped", role))
        comparison = compare_runs(store, "quadruped-standard", "quadruped-user")
        report = diagnose({"case_id": "d00-a1-external-fixture", "category": "quadruped",
                           "urdf_xml": (ROOT / "tests/fixtures/S06/a1_description/a1.urdf").read_text(),
                           "comparison": comparison,
                           "observations": [{"id": "e04-pd-contrast", "kind": "controller_gain_effect",
                               "source_sha256": hashlib.sha256(probe_path.read_bytes()).hexdigest(),
                               "source_kind": "simulation", "object": "two_link.shoulder",
                               "status": "observed", "value": probe["controller_negative_damping"]["final_tracking_error_rad"] -
                               probe["joint_step_stable"]["final_tracking_error_rad"], "unit": "rad"}]})
    causes = {item["id"]: item for item in report["candidate_causes"]}
    if (report["symptom"] != "fixture_difference_only" or causes["mechanical_design"]["status"] != "needs_evidence" or
            causes["actuator_or_controller"]["status"] != "supported_hypothesis" or
            any(item["causal_claim"] for item in causes.values())):
        raise AssertionError("Evidence scope or competing causes incorrect")
    (output / "diagnosis-graph.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "passed", "symptom": report["symptom"],
                      "evidence": len(report["evidence"]), "causes": len(report["candidate_causes"]),
                      "mechanical_status": causes["mechanical_design"]["status"],
                      "controller_status": causes["actuator_or_controller"]["status"],
                      "source_sha256": report["skill_summary"]["source_sha256"]}))


if __name__ == "__main__":
    main()
