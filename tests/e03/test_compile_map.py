"""E03: engine compiles actual URDF bytes with names, inertia mass and DOF loss accounting."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from urdftools.evaluation.compile import compile_report
FIX = ROOT / "tests/fixtures/E00"


class ConversionProvenanceTests(unittest.TestCase):
    def test_four_leg_model_dof_body_map_and_root_mass_loss(self):
        path = FIX / "quadruped_valid.urdf"
        record = compile_report(path)
        self.assertEqual(record["source_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(record["status"], "compiled_with_losses")
        self.assertEqual(record["source"]["total_declared_mass_kg"], 11.2)
        self.assertAlmostEqual(record["compiled"]["body_mass_sum_kg"], 3.2)
        self.assertEqual(record["compiled"]["nv"], 8)
        self.assertEqual(len(record["joint_mapping"]), 8)
        self.assertTrue(all(v["status"] == "preserved" for v in record["joint_mapping"].values()))
        self.assertEqual(record["link_mapping"]["torso"]["status"], "not_independent_body")
        self.assertEqual(record["link_mapping"]["LF_lower"]["compiled_body"], "LF_lower")
        self.assertTrue(any(loss["kind"] == "source_vs_compiled_mass_difference"
                            for loss in record["losses"]))
        self.assertFalse(record["training_ready"])

    def test_humanoid_and_fixed_massless_frame_loss_is_explicit(self):
        a = compile_report(FIX / "humanoid_valid.urdf")
        b = compile_report(FIX / "humanoid_fixed_sensor_frame.urdf")
        self.assertEqual(a["compiled"]["nv"], 4)
        self.assertEqual(b["compiled"]["nv"], 4)
        self.assertEqual(a["source"]["total_declared_mass_kg"], 19.0)
        self.assertEqual(a["compiled"]["body_mass_sum_kg"], 7.0)
        self.assertEqual(b["link_mapping"]["imu_frame"]["status"], "not_independent_body")
        self.assertEqual(b["joint_mapping"]["imu_mount"]["status"], "fixed_or_fused")
        self.assertTrue(any(loss.get("source_joint") == "imu_mount" for loss in b["losses"]))

    def test_bad_physics_cannot_be_auto_repaired(self):
        for name in ("quadruped_zero_axis", "humanoid_triangle_violation",
                     "humanoid_negative_inertia"):
            with self.subTest(name=name):
                r = compile_report(FIX / (name + ".urdf"))
                self.assertEqual(r["status"], "rejected")
                self.assertTrue(r["preflight_failures"])
                self.assertEqual(r["compiler"]["inertia_repairs"], "none")
                self.assertNotIn("compiled", r)

    def test_hollow_root_not_a_false_dynamic_body(self):
        r = compile_report(FIX / "hollow_frame_valid.urdf")
        self.assertEqual(r["compiled"]["nv"], 0)
        self.assertAlmostEqual(r["compiled"]["body_mass_sum_kg"], 0.0)
        self.assertEqual(r["source"]["total_declared_mass_kg"], 2.0)
        self.assertEqual(r["link_mapping"]["frame"]["status"], "not_independent_body")


if __name__ == "__main__":
    unittest.main()
