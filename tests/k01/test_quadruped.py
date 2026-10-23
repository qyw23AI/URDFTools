"""K01 real pinned vendor XML plus explicitly mutated negative fixtures."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from urdftools.evaluation.quadruped import evaluate_quadruped_xml
from urdftools.evaluation.skills import discover_skills, run_skill, SkillError

VENDOR = json.loads((ROOT/"tests/fixtures/S06/reference_models.json").read_text())
GO2 = VENDOR["models"]["go2"]
PATHS = {
    "a1": ROOT/"tests/fixtures/S06/a1_description/a1.urdf",
    "go2": ROOT/GO2["fixture_dir"]/GO2["urdf_path"],
}
HASHES = {
    "a1": "b5feb8464ed82f6f6ac1905e915d5177b887e6f338e0f8f810da35fd4395a607",
    "go2": GO2["fixture_urdf_sha256"],
}


def altered(name, change):
    root = ET.fromstring(PATHS[name].read_bytes())
    change(root)
    return ET.tostring(root, encoding="unicode")


def check(report, rule, obj):
    matches = [x for x in report["checks"] if x["rule_id"] == rule and x["object"] == obj]
    assert len(matches) == 1, (rule, obj, matches)
    return matches[0]


class QuadrupedTests(unittest.TestCase):
    def test_vendor_provenance_and_baseline(self):
        for name, path in PATHS.items():
            with self.subTest(name=name):
                raw = path.read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), HASHES[name])
                r = evaluate_quadruped_xml(raw.decode())
                self.assertTrue(r["passed"], r["checks"])
                self.assertEqual(r["source_sha256"], HASHES[name])
                self.assertEqual(check(r, "actuated_dof", "robot")["observed"], 12)
                self.assertGreater(check(r, "nominal_foot_spread", "robot")["observed"]["area_m2"], .01)
                for leg in ("FL","FR","RL","RR"):
                    self.assertEqual(check(r, "leg_chain", leg)["status"], "pass")
                    self.assertEqual(check(r, "foot_collision", leg+"_foot")["status"], "pass")
                self.assertEqual(check(r, "motor_calibration", "robot")["status"], "unknown")
                self.assertEqual(check(r, "dynamic_balance_and_gait", "robot")["status"], "unknown")

    def test_missing_foot_contact(self):
        def mutation(root):
            foot = root.find("./link[@name='FL_foot']")
            for collision in list(foot.findall("collision")):
                foot.remove(collision)
        r = evaluate_quadruped_xml(altered("go2", mutation))
        self.assertFalse(r["passed"])
        self.assertEqual(check(r, "foot_collision", "FL_foot")["status"], "fail")

    def test_invalid_axis(self):
        def mutation(root):
            root.find("./joint[@name='FR_hip_joint']/axis").set("xyz", "0 0 0")
        r = evaluate_quadruped_xml(altered("a1", mutation))
        self.assertEqual(check(r, "joint_axis", "FR_hip_joint")["status"], "fail")

    def test_unknown_vs_bad_effort(self):
        def mutation(root):
            root.find("./joint[@name='RR_calf_joint']/limit").attrib.pop("effort")
        xml = altered("go2", mutation)
        r = evaluate_quadruped_xml(xml)
        self.assertTrue(r["passed"])
        self.assertEqual(check(r, "urdf_effort", "RR_calf_joint")["status"], "unknown")
        root = ET.fromstring(xml)
        root.find("./joint[@name='RR_calf_joint']/limit").set("effort", "-5")
        bad = evaluate_quadruped_xml(ET.tostring(root, encoding="unicode"))
        self.assertFalse(bad["passed"])
        self.assertEqual(check(bad, "urdf_effort", "RR_calf_joint")["status"], "fail")

    def test_broken_leg_chain(self):
        def mutation(root):
            foot_joint = next(j for j in root.findall("joint")
                              if j.find("child") is not None and j.find("child").get("link")=="FL_foot")
            foot_joint.find("parent").set("link", "base")
        r = evaluate_quadruped_xml(altered("go2", mutation))
        self.assertFalse(r["passed"])
        self.assertEqual(check(r, "leg_chain", "FL")["status"], "fail")

    def test_bad_range_and_collapsed_footprint(self):
        def mutation(root):
            root.find("./joint[@name='FL_thigh_joint']/limit").set("upper", "-999")
        r = evaluate_quadruped_xml(altered("a1", mutation))
        self.assertEqual(check(r, "joint_range", "FL_thigh_joint")["status"], "fail")
        def collapse(root):
            for leg in ("FL","FR","RL","RR"):
                root.find(f"./joint[@name='{leg}_hip_joint']/origin").set("xyz", "0 0 0")
        r = evaluate_quadruped_xml(altered("a1", collapse))
        self.assertEqual(check(r, "nominal_foot_spread", "robot")["status"], "fail")

    def test_quasistatic_trace_not_gait_claim(self):
        feet = {"FL": [0.3, 0.2], "FR": [0.3, -0.2],
                "RL": [-0.3, 0.2], "RR": [-0.3, -0.2]}
        samples = [{"t_s": 0.0, "com_xy_m": [0, 0], "feet_xy_m": feet,
                    "contacts": ["FL", "FR", "RL", "RR"]},
                   {"t_s": 0.01, "com_xy_m": [0.0, 0.0], "feet_xy_m": feet,
                    "contacts": ["FL", "FR", "RL"]}]
        trace = {"source_kind": "synthetic_fixture", "frame": "world", "samples": samples}
        xml = PATHS["a1"].read_text()
        report = evaluate_quadruped_xml(xml, trace)
        analysis = report["contact_trace_analysis"]
        self.assertEqual(analysis["quasistatic_projection_status"], "pass")
        self.assertEqual(analysis["gait_quality_status"], "unknown")
        self.assertEqual(analysis["contact_transition_count"], 1)
        samples[1]["com_xy_m"] = [2.0, 2.0]
        report = evaluate_quadruped_xml(xml, trace)
        self.assertEqual(check(report, "quasistatic_com_projection", "contact_trace")["status"], "fail")
        self.assertFalse(report["passed"])
        samples[0]["contacts"] = ["FL", "FR"]
        samples[1]["contacts"] = ["FL", "FR"]
        report = evaluate_quadruped_xml(xml, trace)
        self.assertEqual(report["contact_trace_analysis"]["quasistatic_projection_status"], "unknown")
        self.assertTrue(report["passed"])

    def test_trace_rejects_invalid_units_and_timestamps(self):
        trace = {"source_kind": "synthetic_fixture", "frame": "body", "samples": []}
        with self.assertRaises(ValueError):
            evaluate_quadruped_xml(PATHS["a1"].read_text(), trace)
        feet = {leg: [0, 0] for leg in ("FL", "FR", "RL", "RR")}
        sample = {"t_s": 0.0, "com_xy_m": [0, 0], "feet_xy_m": feet, "contacts": []}
        trace = {"source_kind": "synthetic_fixture", "frame": "world", "samples": [sample, dict(sample)]}
        with self.assertRaises(ValueError):
            evaluate_quadruped_xml(PATHS["a1"].read_text(), trace)

    def test_skill_registry_and_input_security(self):
        skill = discover_skills(ROOT/"skills")["quadruped_structure"]
        raw = PATHS["a1"].read_text()
        report = run_skill(skill, {"quadruped_scan": {"urdf_xml": raw}})
        self.assertTrue(report["passed"])
        self.assertEqual(report["results"][0]["source_sha256"], HASHES["a1"])
        for value in ('<!DOCTYPE robot [<!ENTITY x "x">]><robot>&x;</robot>',
                      "<root/>", "x" * (4*1024*1024+1)):
            with self.subTest(value=value[:20]), self.assertRaises(SkillError):
                run_skill(skill, {"quadruped_scan": {"urdf_xml": value}})


if __name__ == "__main__":
    unittest.main()
