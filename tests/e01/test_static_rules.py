"""E01: independent gold-label evaluation against actual XML parsing and tensor arithmetic."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from urdftools.evaluation.static import scan_urdf, symmetric_eigenvalues

FIXTURES = ROOT / "tests/fixtures/E00"


def trusted_context(manifest):
    return {
        "joint_axes": {"LF_knee": manifest["design_context"]["LF_knee_expected_axis"]},
        "link_visual_box_sizes_m": {"torso": manifest["design_context"]["quadruped_torso_size_m"]},
    }


class StaticRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((FIXTURES / "manifest.json").read_text())
        cls.context = trusted_context(cls.manifest)

    def test_all_nine_gold_labels_and_real_source_hashes(self):
        for case in self.manifest["cases"]:
            with self.subTest(file=case["file"]):
                path = FIXTURES / case["file"]
                context = self.context if case["category"] == "quadruped" else None
                report = scan_urdf(path, context)
                observed = [(f["rule_id"], f["location"], f["certainty"])
                            for f in report["findings"]]
                expected = [(x["rule"], x["location"], x["certainty"])
                            for x in case["expected"]]
                self.assertEqual(observed, expected)
                self.assertEqual(report["input_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
                for finding in report["findings"]:
                    self.assertEqual(finding["source_sha256"], report["input_sha256"])
                    self.assertEqual(finding["rule_version"], "1.0")
                    self.assertTrue(finding["next_action"])
                    self.assertTrue(finding["observed"] is not None)
                if "positive_boundary" in case:
                    self.assertEqual(report["result"], "no_findings")

    def test_context_is_required_to_report_nonzero_axis_and_scale_mismatch(self):
        for name in ("quadruped_axis_context_mismatch", "quadruped_misunit_visual"):
            report = scan_urdf(FIXTURES / (name + ".urdf"))
            self.assertEqual(report["findings"], [])

    def test_symmetric_tensor_eigenvalues_and_triangle_vs_spd(self):
        # Rotation of diag(0.003, 0.004, 0.005) by 45 deg about Z.
        eig = symmetric_eigenvalues([[0.0035, -0.0005, 0],
                                     [-0.0005, 0.0035, 0], [0, 0, 0.005]])
        for a, b in zip(eig, (0.003, 0.004, 0.005)):
            self.assertAlmostEqual(a, b, places=13)
        # Positive definite does not imply physically realizable rotational inertia.
        eig = symmetric_eigenvalues([[0.001, 0, 0], [0, 0.001, 0], [0, 0, 0.01]])
        self.assertGreater(eig[0], 0)
        self.assertGreater(eig[2], eig[0] + eig[1])

    def test_actual_mutation_changes_diagnosis_without_filename_heuristics(self):
        healthy = (FIXTURES / "quadruped_valid.urdf").read_text()
        self.assertIn('xyz="0 1 0"', healthy)
        changed = healthy.replace('xyz="0 1 0"', 'xyz="0 0 0"', 1)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ordinary_model.urdf"
            path.write_text(changed)
            report = scan_urdf(path)
            self.assertEqual([(f["rule_id"], f["location"]) for f in report["findings"]],
                             [("invalid_joint_axis", "LF_hip")])
            self.assertNotEqual(report["input_sha256"],
                                hashlib.sha256(healthy.encode()).hexdigest())

    def test_dynamic_missing_inertia_is_unknown_not_a_fake_zero(self):
        original = (FIXTURES / "quadruped_valid.urdf").read_text()
        import xml.etree.ElementTree as ET
        robot = ET.fromstring(original)
        child = robot.find("./link[@name='LF_lower']")
        child.remove(child.find("inertial"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "robot.urdf"
            path.write_bytes(ET.tostring(robot))
            report = scan_urdf(path)
            self.assertEqual(len(report["findings"]), 1)
            finding = report["findings"][0]
            self.assertEqual(finding["rule_id"], "missing_dynamic_inertia")
            self.assertEqual(finding["status"], "unknown")
            self.assertEqual(finding["category"], "missing_data")


if __name__ == "__main__":
    unittest.main()
