"""K02 pinned vendor URDF tests and explicitly synthetic negative mutations."""
import copy
import hashlib
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"python"))
from urdftools.evaluation.humanoid import evaluate_humanoid_xml
from urdftools.evaluation.skills import discover_skills, run_skill, SkillError

PATHS = {
    "g1": ROOT/"tests/fixtures/S06/reference_models/g1_description/g1_29dof.urdf",
    "h1": ROOT/"tests/fixtures/R02/h1_description/urdf/h1.urdf",
}
HASHES = {
    "g1": "e1dc89366bf96aa33ba4ef211884f6d81320ddd2ac6f8b1ad82986e64008be31",
    "h1": "ebd495cba7887406c406b8441a5e2dd712f8da91dcb60e7b099cbfa3adf2efa5",
}


def mutate(model, fn):
    tree = ET.fromstring(PATHS[model].read_bytes())
    fn(tree)
    return ET.tostring(tree, encoding="unicode")


def check(report, rule, obj):
    found = [c for c in report["checks"] if c["rule_id"] == rule and c["object"] == obj]
    assert len(found) == 1, (rule, obj, found)
    return found[0]


def trace():
    polygons = {
        "left": [[-0.1, 0.05], [0.1, 0.05], [0.1, 0.12], [-0.1, 0.12]],
        "right": [[-0.1, -0.12], [0.1, -0.12], [0.1, -0.05], [-0.1, -0.05]],
    }
    return {"source_kind": "synthetic_fixture", "frame": "world", "samples": [
        {"t_s": 0.0, "com_xy_m": [0, 0], "sole_polygons_xy_m": copy.deepcopy(polygons),
         "contacts": ["left", "right"], "torso_rpy_rad": [0.1, -0.2, 0]},
        {"t_s": 0.01, "com_xy_m": [0, 0.08], "sole_polygons_xy_m": copy.deepcopy(polygons),
         "contacts": ["left"], "joint_positions_rad": {"left_knee_joint": 0.3}},
    ]}


class HumanoidTests(unittest.TestCase):
    def test_pinned_real_vendor_baselines(self):
        for name, path in PATHS.items():
            with self.subTest(name=name):
                raw = path.read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), HASHES[name])
                r = evaluate_humanoid_xml(raw.decode())
                self.assertTrue(r["passed"], r["checks"])
                self.assertEqual(r["source_sha256"], HASHES[name])
                self.assertEqual(r["profile"], name)
                self.assertEqual(check(r, "actuated_dof", "robot")["observed"], 29 if name=="g1" else 19)
                for side in ("left", "right"):
                    self.assertEqual(check(r, "leg_chain", side)["status"], "pass")
                    foot = side+("_ankle_roll_link" if name=="g1" else "_ankle_link")
                    self.assertEqual(check(r, "sole_collision", foot)["status"], "pass")
                    self.assertGreater(check(r, "sole_xy_proxy", foot)["observed"]["area_m2"], 1e-5)
                self.assertGreater(check(r, "declared_mass_sum", "robot")["observed"]["kg"], 20)
                nominal = check(r, "declared_com_nominal", "robot")
                self.assertEqual(nominal["status"], "unknown")  # sensor inertials absent
                self.assertEqual(len(nominal["observed"]["xyz_m"]), 3)
                self.assertLess(abs(nominal["observed"]["xyz_m"][0]), 1.0)
                self.assertEqual(check(r, "dynamic_balance_and_gait", "robot")["status"], "unknown")
                self.assertEqual(check(r, "motor_calibration", "robot")["status"], "unknown")

    def test_missing_sole_collision(self):
        def remove(root):
            foot = root.find("./link[@name='left_ankle_roll_link']")
            for collision in list(foot.findall("collision")):
                foot.remove(collision)
        r = evaluate_humanoid_xml(mutate("g1", remove))
        self.assertFalse(r["passed"])
        self.assertEqual(check(r, "sole_collision", "left_ankle_roll_link")["status"], "fail")
        self.assertEqual(check(r, "sole_xy_proxy", "left_ankle_roll_link")["status"], "unknown")

    def test_wrong_knee_axis_and_limit(self):
        def bad(root):
            j = root.find("./joint[@name='left_knee_joint']")
            j.find("axis").set("xyz", "0 0 0")
            j.find("limit").set("lower", "8")
        r = evaluate_humanoid_xml(mutate("h1", bad))
        self.assertEqual(check(r, "joint_axis", "left_knee_joint")["status"], "fail")
        self.assertEqual(check(r, "joint_range", "left_knee_joint")["status"], "fail")

    def test_broken_chain(self):
        def bad(root):
            root.find("./joint[@name='right_knee_joint']/parent").set("link", "pelvis")
        r = evaluate_humanoid_xml(mutate("g1", bad))
        self.assertEqual(check(r, "leg_chain", "right")["status"], "fail")

    def test_inertia_and_mass_mutants(self):
        def bad(root):
            link = root.find("./link[@name='left_knee_link']")
            link.find("./inertial/mass").set("value", "-1")
            inertia = link.find("./inertial/inertia")
            inertia.set("ixx", "-0.5")
        r = evaluate_humanoid_xml(mutate("h1", bad))
        self.assertEqual(check(r, "link_mass", "left_knee_link")["status"], "fail")
        self.assertEqual(check(r, "link_inertia", "left_knee_link")["status"], "fail")

    def test_missing_motor_limit_is_unknown(self):
        def missing(root):
            root.find("./joint[@name='left_ankle_joint']/limit").attrib.pop("effort")
        r = evaluate_humanoid_xml(mutate("h1", missing))
        self.assertTrue(r["passed"])
        self.assertEqual(check(r, "urdf_effort", "left_ankle_joint")["status"], "unknown")

    def test_double_and_single_support_not_dynamic_claim(self):
        r = evaluate_humanoid_xml(PATHS["h1"].read_text(), trace())
        analysis = r["contact_trace_analysis"]
        self.assertEqual(analysis["quasistatic_projection_status"], "pass")
        self.assertEqual(analysis["contact_transition_count"], 1)
        self.assertAlmostEqual(analysis["max_abs_torso_pitch_rad"], 0.2)
        self.assertEqual(analysis["gait_quality_status"], "unknown")
        self.assertEqual(analysis["dynamic_balance_status"], "unknown")

    def test_outside_projection_and_joint_limit_mutants(self):
        t = trace()
        t["samples"][1]["com_xy_m"] = [5, 5]
        t["samples"][1]["joint_positions_rad"]["left_knee_joint"] = 99
        r = evaluate_humanoid_xml(PATHS["h1"].read_text(), t)
        self.assertFalse(r["passed"])
        self.assertEqual(check(r, "quasistatic_com_projection", "contact_trace")["status"], "fail")
        self.assertEqual(check(r, "declared_joint_limit_trace", "contact_trace")["status"], "fail")
        self.assertEqual(r["contact_trace_analysis"]["gait_quality_status"], "unknown")

    def test_indeterminate_point_contacts(self):
        t = trace()
        for sample in t["samples"]:
            sample["sole_polygons_xy_m"] = {"left": [[0, 0]], "right": [[0, 0]]}
        r = evaluate_humanoid_xml(PATHS["g1"].read_text(), t)
        self.assertTrue(r["passed"])
        self.assertEqual(check(r, "quasistatic_com_projection", "contact_trace")["status"], "unknown")

    def test_trace_validation_and_xml_security(self):
        for t in [dict(trace(), frame="body"), dict(trace(), source_kind="unknown")]:
            with self.assertRaises(ValueError):
                evaluate_humanoid_xml(PATHS["h1"].read_text(), t)
        t = trace()
        t["samples"][1]["t_s"] = 0
        with self.assertRaises(ValueError):
            evaluate_humanoid_xml(PATHS["h1"].read_text(), t)
        t = trace()
        t["samples"][0]["com_xy_m"] = [True, 0]
        with self.assertRaises(ValueError):
            evaluate_humanoid_xml(PATHS["h1"].read_text(), t)
        for xml in ['<!DOCTYPE robot [<!ENTITY x "x">]><robot>&x;</robot>',
                    "<not_robot/>", "<robot", "x"*(4*1024*1024+1)]:
            with self.assertRaises(ValueError):
                evaluate_humanoid_xml(xml)

    def test_installed_skill_contract(self):
        skill = discover_skills(ROOT/"skills")["humanoid_structure"]
        r = run_skill(skill, {"humanoid_scan": {"urdf_xml": PATHS["g1"].read_bytes().decode()}})
        self.assertTrue(r["passed"])
        self.assertEqual(r["results"][0]["source_sha256"], HASHES["g1"])
        with self.assertRaises(SkillError):
            run_skill(skill, {"humanoid_scan": {"urdf_xml": "<bad/>"}})


if __name__ == "__main__":
    unittest.main()
