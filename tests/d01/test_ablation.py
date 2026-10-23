import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from urdftools.diagnosis.ablation import AblationError, propose_leg_length, assess_external_retest

TERRAIN = {"terrain_kind": "step", "terrain_version": "v1", "scale_mode": "physical_m",
           "terrain_size": 0.2, "terrain_size_unit": "m", "push_force_n": 0,
           "push_duration_s": 0, "train_seeds": [1, 2, 3], "test_seeds": [101, 102],
           "success_definition": "cross without fall"}
PROTOCOL = {"robot_category": "quadruped", "algorithm": "ppo", "algorithm_version": "1",
            "protocol": "stairs", "protocol_version": "1", "reward_sha256": "a"*64,
            "track": "fixed_recipe", "recipe_sha256": "b"*64, "budget_steps": 100000,
            "paired_seed_design": True, "terrain": TERRAIN}


def plan():
    return propose_leg_length("case-d01", ["skill:abc", "comparison:xyz"],
        length_mm=100, variant_length_mm=120, width_mm=20, thickness_mm=10,
        density_kg_m3=2700, protocol=PROTOCOL,
        train_seeds=[1, 2, 3], eval_seeds=[101, 102])


def result(model_sha, *, origin="synthetic_fixture", verification="schema_valid",
           review="", protocol=None, wins=(1, 1, 1)):
    return {"schema_version": 1, "origin": origin, "verification": verification,
            "review_evidence_id": review, "model_sha256": model_sha,
            "protocol": copy.deepcopy(protocol or PROTOCOL),
            "train_runs": [{"train_seed": s, "status": "completed",
                            "episodes": [bool(w), bool(w)]}
                           for s, w in zip([1, 2, 3], wins)],
            "evaluation_seeds": [101, 102]}


def compare_files(p, base, changed, *, attest=False):
    with tempfile.TemporaryDirectory() as temp:
        left, right = Path(temp)/"baseline.json", Path(temp)/"variant.json"
        left.write_text(json.dumps(base))
        right.write_text(json.dumps(changed))
        trusted = {hashlib.sha256(path.read_bytes()).hexdigest() for path in (left, right)} if attest else None
        return assess_external_retest(p, left, right, verified_source_hashes=trusted)


class D01Tests(unittest.TestCase):
    def test_real_cad_mass_inertia_and_joint_frames(self):
        p = plan()
        a, b = p["baseline"], p["variant"]
        self.assertEqual(p["status"], "proposed")
        self.assertAlmostEqual(a["mass_kg"], .1*.02*.01*2700, places=9)
        self.assertAlmostEqual(b["mass_kg"], .12*.02*.01*2700, places=9)
        self.assertAlmostEqual(a["inertia_com_kg_m2"][1][1],
                               a["mass_kg"]*(.1**2+.01**2)/12, places=10)
        self.assertGreater(b["inertia_com_kg_m2"][1][1],
                           a["inertia_com_kg_m2"][1][1]*1.7)
        for part in (a, b):
            root = ET.fromstring(part["urdf_xml"])
            self.assertEqual(len(root.findall("joint")), 2)
            self.assertAlmostEqual(float(root.find("./joint[@name='distal_frame']/origin").get("xyz").split()[0]),
                                   part["length_m"])
            self.assertAlmostEqual(float(root.find("./link[@name='leg']/inertial/origin").get("xyz").split()[0]),
                                   part["length_m"]/2)
            self.assertAlmostEqual(float(root.find("./link[@name='leg']/inertial/mass").get("value")),
                                   part["mass_kg"])
        self.assertNotEqual(a["urdf_sha256"], b["urdf_sha256"])

    def test_fixture_never_observed(self):
        p = plan()
        r = compare_files(p, result(p["baseline"]["urdf_sha256"]),
                          result(p["variant"]["urdf_sha256"], wins=(0, 0, 0)))
        self.assertEqual(r["status"], "proposed")
        self.assertIn("Synthetic fixture", " ".join(r["reasons"]))
        self.assertAlmostEqual(r["comparison"]["difference"], -1)

    def test_reviewed_external_local_effect_not_hardware(self):
        p = plan()
        b = result(p["baseline"]["urdf_sha256"], origin="user_upload",
                   verification="protocol_reviewed", review="review:base")
        v = result(p["variant"]["urdf_sha256"], origin="user_upload",
                   verification="protocol_reviewed", review="review:variant", wins=(0, 0, 1))
        self.assertEqual(compare_files(p, b, v)["status"], "proposed")
        # Simulated trusted-importer attestation tests the gate, not real robot evidence.
        r = compare_files(p, b, v, attest=True)
        self.assertEqual(r["status"], "observed_local_effect")
        self.assertEqual(r["comparison"]["interval_method"], "paired_seed_bootstrap")
        self.assertIn("never physical hardware causality", r["claim_scope"])

    def test_reward_conflict_missing_review(self):
        p = plan()
        b = result(p["baseline"]["urdf_sha256"], origin="user_upload",
                   verification="protocol_reviewed", review="review:base")
        v = result(p["variant"]["urdf_sha256"], origin="user_upload",
                   verification="schema_valid")
        v["protocol"]["reward_sha256"] = "f"*64
        r = compare_files(p, b, v)
        self.assertEqual(r["status"], "proposed")
        self.assertEqual(r["comparison"]["comparability"]["status"], "incomparable")

    def test_hash_seed_geometry_rejection(self):
        p = plan()
        b = result(p["baseline"]["urdf_sha256"])
        v = result(p["variant"]["urdf_sha256"])
        v["model_sha256"] = "0"*64
        with self.assertRaisesRegex(AblationError, "SHA"):
            compare_files(p, b, v)
        with self.assertRaisesRegex(AblationError, "length"):
            propose_leg_length("x", ["e"], length_mm=100, variant_length_mm=100,
                               width_mm=20, thickness_mm=10, density_kg_m3=2700,
                               protocol=PROTOCOL, train_seeds=[1, 2, 3], eval_seeds=[101])
        with self.assertRaisesRegex(AblationError, "held-out"):
            propose_leg_length("x", ["e"], length_mm=100, variant_length_mm=120,
                               width_mm=20, thickness_mm=10, density_kg_m3=2700,
                               protocol=PROTOCOL, train_seeds=[1, 2, 3], eval_seeds=[2])


if __name__ == "__main__":
    unittest.main()
