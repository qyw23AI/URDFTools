"""E02 analytic and MuJoCo cross-validation, with intentional joint frame corruption."""
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from urdftools.evaluation.dynamics import PlanarArm
from scripts.e02_dynamics_smoke import make_robot, evaluate_urdf


class DynamicConsistencyTests(unittest.TestCase):
    def test_mass_matrix_symmetry_and_known_zero_pose(self):
        arm = PlanarArm()
        matrix = arm.mass_matrix(0, 0)
        self.assertAlmostEqual(matrix[0][1], matrix[1][0], places=14)
        self.assertGreater(matrix[0][0], 0)
        self.assertGreater(matrix[1][1], 0)
        self.assertGreater(matrix[0][0] * matrix[1][1] - matrix[0][1] ** 2, 0)
        self.assertEqual(arm.mass_matrix(0.2, 0.7), arm.mass_matrix(-0.8, 0.7))

    def test_analytic_gravity_matches_finite_difference_potential(self):
        arm = PlanarArm()
        def potential(q1, q2):
            return -arm.gravity_m_s2 * (
                arm.mass1_kg * arm.com1_m * math.cos(q1)
                + arm.mass2_kg * (arm.length1_m * math.cos(q1)
                                  + arm.com2_m * math.cos(q1+q2)))
        h = 1e-6
        for q1, q2 in [(0.2, -0.3), (1.0, 0.4), (-0.5, 1.2)]:
            expected = ((potential(q1+h,q2)-potential(q1-h,q2))/(2*h),
                        (potential(q1,q2+h)-potential(q1,q2-h))/(2*h))
            for a,b in zip(arm.gravity_generalized(q1,q2), expected):
                self.assertAlmostEqual(a,b,places=8)

    def test_actual_compiled_dynamics_and_bad_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            normal = folder / "normal.urdf"
            wrong = folder / "wrong.urdf"
            fixed = folder / "fixed.urdf"
            make_robot(normal)
            make_robot(wrong, wrong_elbow_frame=True)
            make_robot(fixed, fixed_imu=True)
            result = evaluate_urdf(normal)
            corrupted = evaluate_urdf(wrong)
            sensor = evaluate_urdf(fixed)
            self.assertEqual(result["nv"], 2)
            self.assertEqual(sensor["nv"], 2)
            self.assertLess(result["max_mass_error"], 1e-8)
            self.assertLess(result["max_gravity_error"], 1e-8)
            self.assertLess(sensor["max_mass_error"], 1e-8)
            self.assertLess(sensor["max_gravity_error"], 1e-8)
            self.assertGreater(corrupted["max_mass_error"], 0.01)
            self.assertGreater(corrupted["max_gravity_error"], 0.01)
            self.assertNotEqual(result["sha256"], corrupted["sha256"])


if __name__ == "__main__":
    unittest.main()
