"""E04 acceptance: real CPU integration, corrupt PD contrast, collision and replay metadata."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.e02_dynamics_smoke import make_robot
from scripts.e04_sim_probes import (
    run_servo, run_drop, run_sweep, run_quad_stance, write_gif, TARGET,
)


class SimulationProbesTests(unittest.TestCase):
    def test_same_robot_wrong_pd_diagnosed_as_controller(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "robot.urdf"
            make_robot(path)
            normal = run_servo(path, kp=35, kd=6)
            wrong = run_servo(path, kp=35, kd=-6)
            disturbed = run_servo(path, kp=35, kd=6, disturbance=True)
            self.assertEqual(TARGET.tolist(), [0.4, 0.0])
            self.assertEqual(normal["source_sha256"], wrong["source_sha256"])
            self.assertEqual(normal["source_sha256"], disturbed["source_sha256"])
            self.assertLess(normal["final_tracking_error_rad"], 0.05)
            self.assertGreater(wrong["final_tracking_error_rad"], 0.1)
            self.assertLess(disturbed["final_tracking_error_rad"], 0.05)
            self.assertEqual(normal["steps"], 1200)
            self.assertEqual(len(normal["trace"]), 60)

    def test_actual_contact_and_mass_matrix_sweep(self):
        drop = run_drop()
        self.assertGreater(drop["contact_frames"], 100)
        self.assertTrue(0.045 < drop["resting_height_m"] < 0.065)
        self.assertEqual(drop["steps"], 1200)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "robot.urdf"
            make_robot(path)
            sweep = run_sweep(path)
            self.assertEqual(sweep["poses"], 25)
            self.assertGreater(sweep["minimum_mass_eigen"], 0)

    def test_floating_quad_stance_failure_is_reported_not_suppressed(self):
        with tempfile.TemporaryDirectory() as temp:
            result = run_quad_stance(Path(temp))
            self.assertEqual(result["nv"], 14)
            self.assertAlmostEqual(result["mass_kg"], 11.2, places=9)
            self.assertGreater(result["contact_steps"], 0)
            self.assertEqual(result["status"], "unstable_in_this_probe")
            self.assertTrue(result["trace"])

    def test_animated_gif_is_a_state_replay_not_external_experiment(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            source = folder / "source.urdf"
            make_robot(source)
            trace = run_servo(source, kp=35, kd=6)["trace"]
            gif = folder / "replay.gif"
            meta = write_gif(gif, trace)
            image = gif.read_bytes()
            self.assertEqual(image[:6], b"GIF89a")
            self.assertEqual(image[-1], 0x3b)
            self.assertEqual(meta["frames"], 30)
            self.assertEqual(meta["sha256"], hashlib.sha256(image).hexdigest())
            self.assertIn("diagrammatic", meta["representation"])
            self.assertGreater(meta["size_bytes"], 20000)


if __name__ == "__main__":
    unittest.main()
