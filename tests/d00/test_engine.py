import hashlib
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from urdftools.diagnosis.engine import DiagnosisError, diagnose
from urdftools.results.compare import compare_success

A1 = ROOT / "tests/fixtures/S06/a1_description/a1.urdf"
G1 = ROOT / "tests/fixtures/S06/reference_models/g1_description/g1_29dof.urdf"
TERRAIN = {"terrain_kind": "step", "terrain_version": "v1", "scale_mode": "physical_m",
           "terrain_size": 0.2, "terrain_size_unit": "m", "push_force_n": 0,
           "push_duration_s": 0, "train_seeds": [1, 2, 3], "test_seeds": [101, 102],
           "success_definition": "cross without fall"}
PROTOCOL = {"robot_category": "quadruped", "algorithm": "ppo", "algorithm_version": "1",
            "protocol": "stairs", "protocol_version": "1", "reward_sha256": "a"*64,
            "track": "fixed_recipe", "recipe_sha256": "b"*64, "budget_steps": 100000,
            "paired_seed_design": True, "terrain": TERRAIN}


def seed(index, successes):
    return {"train_seed": index, "status": "completed", "episodes": successes}


def comparison(protocol=PROTOCOL, candidate_protocol=PROTOCOL):
    ref = [seed(1,[True,True]), seed(2,[True,False]), seed(3,[True,True])]
    own = [seed(1,[True,False]), seed(2,[False,False]), seed(3,[True,False])]
    return {"reference_run_id": "a1-fixture", "candidate_run_id": "own-fixture", "fixture_only": True,
            "comparison": compare_success(protocol, candidate_protocol, ref, own)}


def case(xml=A1.read_text(), *, compare=None, observations=None, category="quadruped"):
    return {"case_id": "case-1", "category": category, "urdf_xml": xml,
            "comparison": compare, "observations": observations or []}


class DiagnosisTests(unittest.TestCase):
    def test_no_training_data_retains_unknown_and_all_competing_factors(self):
        report = diagnose(case())
        self.assertEqual(report["symptom"], "insufficient_data")
        self.assertEqual(len(report["candidate_causes"]), 5)
        self.assertTrue(all(not item["causal_claim"] and not item["urdf_design_fault_confirmed"]
                            for item in report["candidate_causes"]))
        self.assertEqual(report["skill_summary"]["source_sha256"], hashlib.sha256(A1.read_bytes()).hexdigest())
        humanoid = diagnose(case(G1.read_text(), category="humanoid"))
        self.assertEqual(humanoid["skill_summary"]["counts"]["fail"], 0)

    def test_fixture_underperformance_does_not_become_mechanical_cause(self):
        report = diagnose(case(compare=comparison()))
        self.assertEqual(report["symptom"], "fixture_difference_only")
        self.assertFalse(report["performance_is_real_observation"])
        mechanical = next(item for item in report["candidate_causes"] if item["id"] == "mechanical_design")
        self.assertEqual(mechanical["status"], "needs_evidence")
        self.assertFalse(mechanical["support_evidence_ids"])
        self.assertTrue(report["comparison_matched"])

    def test_real_mujoco_controller_contrast_and_collision_mutation(self):
        probe_path = ROOT / "artifacts/E04/probe-report.json"
        probe = json.loads(probe_path.read_text())
        stable = probe["joint_step_stable"]["final_tracking_error_rad"]
        unstable = probe["controller_negative_damping"]["final_tracking_error_rad"]
        self.assertGreater(unstable, stable * 1000)
        observation = {"id": "e04-control", "kind": "controller_gain_effect",
                       "source_sha256": hashlib.sha256(probe_path.read_bytes()).hexdigest(),
                       "source_kind": "simulation", "object": "two_link.shoulder",
                       "status": "observed", "value": unstable-stable, "unit": "rad"}
        root = ET.fromstring(A1.read_bytes())
        foot = root.find("./link[@name='FL_foot']")
        for collision in list(foot.findall("collision")):
            foot.remove(collision)
        report = diagnose(case(ET.tostring(root, encoding="unicode"), compare=comparison(),
                               observations=[observation]))
        by_id = {item["id"]: item for item in report["candidate_causes"]}
        self.assertEqual(by_id["collision_or_contact"]["status"], "local_description_issue")
        self.assertEqual(by_id["actuator_or_controller"]["status"], "supported_hypothesis")
        self.assertEqual(by_id["mechanical_design"]["status"], "needs_evidence")
        self.assertIn("e04-control", by_id["actuator_or_controller"]["support_evidence_ids"])
        ids = {item["id"] for item in report["evidence"]}
        self.assertTrue(all(set(item["support_evidence_ids"] + item["counter_evidence_ids"]) <= ids
                            for item in report["candidate_causes"]))

    def test_incomparable_reward_and_invalid_provenance(self):
        changed = dict(PROTOCOL, reward_sha256="c"*64)
        report = diagnose(case(compare=comparison(candidate_protocol=changed)))
        self.assertEqual(report["symptom"], "protocol_not_comparable")
        self.assertFalse(report["performance_is_real_observation"])
        bad = case(observations=[{"id": "bad", "kind": "tracking_error", "source_sha256": "invalid",
                                  "source_kind": "simulation", "object": "joint", "status": "observed",
                                  "value": 1.0, "unit": "rad"}])
        with self.assertRaises(DiagnosisError):
            diagnose(bad)


if __name__ == "__main__":
    unittest.main()
