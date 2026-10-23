import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from urdftools.results.jobs import ImportFailure
from urdftools.results.quadruped import FEET, evaluate_quadruped


class QuadrupedResultTests(unittest.TestCase):
    def setUp(self):
        # Deliberately swap source names: analysis must use explicit roles.
        self.mapping = {"front_left": "FR_sensor", "front_right": "FL_sensor",
                        "rear_left": "RR_sensor", "rear_right": "RL_sensor"}
        self.frames = []
        for t in range(9):
            contact = (t % 4) >= 2
            self.frames.append({"time_s": float(t),
                                "contact": {name: contact for name in self.mapping.values()},
                                "foot_speed_m_s": {name: 0.1 for name in self.mapping.values()},
                                "command_speed_m_s": 1.0, "body_speed_m_s": 0.8,
                                "fallen": t == 5})

    def test_known_contact_slip_tracking_and_falls(self):
        result = evaluate_quadruped(self.frames, self.mapping)
        self.assertEqual(result["foot_mapping"], self.mapping)
        self.assertAlmostEqual(result["duty_factor"]["front_left"], 0.5)
        self.assertAlmostEqual(result["stride_hz"]["front_left"], 0.25)
        self.assertAlmostEqual(result["slip_distance_m"]["front_left"], 0.4)
        self.assertAlmostEqual(result["tracking_rmse_m_s"], 0.2)
        self.assertEqual(result["fall_events"], 1)
        self.assertIsNone(result["torque_saturation"])
        self.assertEqual(result["unknown"], [])

    def test_missing_sensors_do_not_create_slip_or_torque(self):
        frames = [{"time_s": 0, "contact": {"FR_sensor": True}},
                  {"time_s": 1, "contact": {"FR_sensor": False}}]
        result = evaluate_quadruped(frames, self.mapping)
        self.assertIsNone(result["slip_distance_m"]["front_left"])
        self.assertIsNone(result["duty_factor"]["rear_left"])
        self.assertIsNone(result["tracking_rmse_m_s"])
        self.assertIsNone(result["fall_events"])
        self.assertIsNone(result["torque_saturation"])

    def test_bad_mapping_and_nonfinite_sample_rejected(self):
        with self.assertRaises(ImportFailure):
            evaluate_quadruped(self.frames, dict.fromkeys(FEET, "same"))
        changed = list(self.frames)
        changed[2] = dict(changed[2], time_s=1)
        with self.assertRaises(ImportFailure):
            evaluate_quadruped(changed, self.mapping)
        changed = list(self.frames)
        changed[0] = dict(changed[0], body_speed_m_s=math.nan)
        with self.assertRaises(ImportFailure):
            evaluate_quadruped(changed, self.mapping)


if __name__ == "__main__":
    unittest.main()
