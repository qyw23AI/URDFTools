from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from urdftools.results.jobs import ImportFailure
from urdftools.results.terrain import compare_protocols, summarize_episodes, validate_protocol


class TerrainProtocolTests(unittest.TestCase):
    def setUp(self):
        self.protocol = {"terrain_kind": "step", "terrain_version": "generator-2", "scale_mode": "physical_m",
                         "terrain_size": 0.20, "terrain_size_unit": "m", "push_force_n": 10.0, "push_duration_s": 0.1,
                         "train_seeds": [1,2], "test_seeds": [101,102],
                         "success_definition": "base crosses 2 m without fall"}

    def test_grouped_success_rate_and_seed_split(self):
        rows = [{"episode_id": f"ep-{i}", "seed": 101 if i < 2 else 102,
                 "success": i < 3, "terrain_kind": "step", "terrain_version": "generator-2"}
                for i in range(4)]
        result = summarize_episodes(self.protocol, rows)
        self.assertEqual(result["groups"], [{"terrain_kind": "step", "terrain_version": "generator-2",
                                              "episodes": 4, "successes": 3, "success_rate": 0.75}])
        with self.assertRaises(ImportFailure):
            summarize_episodes(self.protocol, rows + [dict(rows[0], episode_id="leak", seed=1)])
        with self.assertRaises(ImportFailure):
            summarize_episodes(self.protocol, rows + [dict(rows[0])])

    def test_version_scale_push_and_leak_enter_comparison(self):
        self.assertEqual(compare_protocols(self.protocol, dict(self.protocol))["status"], "matched")
        changed = dict(self.protocol, terrain_version="generator-3")
        self.assertEqual(compare_protocols(self.protocol, changed)["status"], "incomparable")
        changed = dict(self.protocol, scale_mode="leg_normalized", terrain_size_unit="leg_ratio", leg_length_m=0.5)
        self.assertEqual(compare_protocols(self.protocol, changed)["status"], "incomparable")
        changed = dict(self.protocol, push_force_n=15.0)
        report = compare_protocols(self.protocol, changed)
        self.assertEqual(report["status"], "conditional")
        self.assertEqual(report["reasons"][0]["field"], "push_force_n")
        changed = dict(self.protocol, train_seeds=[1,101])
        report = compare_protocols(self.protocol, changed)
        self.assertEqual(report["status"], "incomparable")
        self.assertIn("leakage", report["reasons"][0]["reason"])

    def test_normalized_requires_leg_length_and_no_boolean_sizes(self):
        with self.assertRaises(ImportFailure):
            validate_protocol(dict(self.protocol, scale_mode="leg_normalized", terrain_size_unit="leg_ratio"))
        with self.assertRaises(ImportFailure):
            validate_protocol(dict(self.protocol, terrain_size=True))
        for kind, unit in (("slope", "deg"), ("obstacle", "m"), ("rough", "m"), ("flat", "none")):
            candidate = dict(self.protocol, terrain_kind=kind, terrain_size_unit=unit,
                             terrain_size=0 if kind == "flat" else 0.2)
            self.assertEqual(validate_protocol(candidate)["terrain_kind"], kind)


if __name__ == "__main__":
    unittest.main()
