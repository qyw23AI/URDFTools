import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from urdftools.results.humanoid import evaluate_humanoid, validate_action_semantics
from urdftools.results.jobs import ImportFailure


class HumanoidResultTests(unittest.TestCase):
    def test_g1_h1_distinct_action_semantics(self):
        cases = [
            (ROOT / "tests/fixtures/S06/reference_models/g1_description/g1_29dof.urdf", "left_ankle_pitch_joint", "right_ankle_pitch_joint", 29),
            (ROOT / "tests/fixtures/R02/h1_description/urdf/h1.urdf", "left_ankle_joint", "right_ankle_joint", 19),
        ]
        for path, left_ankle, right_ankle, expected in cases:
            with self.subTest(model=path.name):
                roles = {"left_hip": "left_hip_pitch_joint", "left_knee": "left_knee_joint", "left_ankle": left_ankle,
                         "right_hip": "right_hip_pitch_joint", "right_knee": "right_knee_joint", "right_ankle": right_ankle}
                result = validate_action_semantics(path, roles, list(roles.values()))
                self.assertEqual(result["urdf_movable_joints"], expected)
                self.assertEqual(result["action_dimensions"], 6)
                with self.assertRaises(ImportFailure):
                    validate_action_semantics(path, roles, ["nonexistent_joint"])

    def test_support_modes_symmetry_trunk_and_com(self):
        mapping = {"left": "R_sensor", "right": "L_sensor"}
        statuses = [(True, False), (True, True), (False, True), (False, False), (True, False)]
        frames = []
        for t, (left, right) in enumerate(statuses):
            frames.append({"time_s": t, "contact": {"R_sensor": left, "L_sensor": right},
                           "trunk_roll_rad": 0.1, "trunk_pitch_rad": 0.0,
                           "com_xy_m": [0, 0], "support_polygon_xy_m": [[-1,-1],[1,-1],[1,1],[-1,1]]})
        result = evaluate_humanoid(frames, mapping)
        self.assertEqual(result["support_mode_fraction"], {"left_only": 0.25, "right_only": 0.25, "double": 0.25, "flight": 0.25})
        self.assertAlmostEqual(result["left_right_duty_difference"], 0)
        self.assertAlmostEqual(result["trunk_tilt_rms_rad"], 0.1)
        self.assertEqual(result["quasistatic_com_inside_fraction"], 1)
        self.assertIsNone(result["dynamic_balance"])

    def test_missing_contact_or_pose_stays_unknown(self):
        frames = [{"time_s": 0}, {"time_s": 1}]
        result = evaluate_humanoid(frames, {"left": "l", "right": "r"})
        self.assertIsNone(result["support_mode_fraction"]["double"])
        self.assertIsNone(result["trunk_tilt_rms_rad"])
        self.assertIsNone(result["quasistatic_com_inside_fraction"])
        with self.assertRaises(ImportFailure):
            evaluate_humanoid([{"time_s": 0}, {"time_s": math.nan}], {"left": "l", "right": "r"})


if __name__ == "__main__":
    unittest.main()
