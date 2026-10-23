from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from urdftools.results.compare import compare_conditions, compare_success
from urdftools.results.jobs import ImportFailure


TERRAIN = {"terrain_kind": "step", "terrain_version": "v1", "scale_mode": "physical_m",
           "terrain_size": 0.2, "terrain_size_unit": "m", "push_force_n": 0,
           "push_duration_s": 0, "train_seeds": [1,2,3], "test_seeds": [101,102],
           "success_definition": "cross without fall"}
PROTOCOL = {"robot_category": "quadruped", "algorithm": "ppo", "algorithm_version": "1",
            "protocol": "stair", "protocol_version": "1", "reward_sha256": "a"*64,
            "track": "fixed_recipe", "recipe_sha256": "b"*64, "budget_steps": 100000,
            "paired_seed_design": True,
            "terrain": TERRAIN}


def run(seed, successes, status="completed"):
    return {"train_seed": seed, "status": status, "episodes": successes}


class ComparisonTests(unittest.TestCase):
    def test_paired_seed_difference_and_interval(self):
        ref = [run(1,[True,True,False,False]), run(2,[True,False,False,False]), run(3,[True,True,True,False])]
        candidate = [run(1,[True,True,True,False]), run(2,[True,True,False,False]), run(3,[True,True,True,True])]
        result = compare_success(PROTOCOL, PROTOCOL, ref, candidate)
        self.assertEqual(result["comparability"]["status"], "matched")
        self.assertAlmostEqual(result["difference"], 0.25)
        self.assertEqual(result["confidence_interval_95"], [0.25, 0.25])
        self.assertEqual(result["interval_method"], "paired_seed_bootstrap")
        self.assertEqual(result["sampling_unit"], "independent_training_seed")
        unpaired = dict(PROTOCOL, paired_seed_design=False)
        self.assertEqual(compare_success(unpaired, unpaired, ref, candidate)["interval_method"], "independent_seed_bootstrap")

    def test_failed_training_included_missing_blocks_rank(self):
        ref = [run(1,[True,False]),run(2,[],"training_failed"),run(3,[True,True])]
        candidate = [run(1,[True,True]),run(2,[True,False]),run(3,[True,True])]
        result = compare_success(PROTOCOL, PROTOCOL, ref, candidate)
        self.assertEqual(result["reference_counts"]["training_failed"], 1)
        self.assertAlmostEqual(result["reference_mean"], 0.5)
        missing = [run(1,[True]),run(2,[],"missing"),run(3,[False])]
        result = compare_success(PROTOCOL, PROTOCOL, missing, candidate)
        self.assertEqual(result["status"], "insufficient_data")
        self.assertIsNone(result["difference"])
        self.assertEqual(result["reference_counts"]["missing"], 1)

    def test_single_seed_and_reward_or_tuning_mismatch(self):
        single = compare_success(PROTOCOL, PROTOCOL, [run(1,[True,False])], [run(1,[True,True])])
        self.assertEqual(single["status"], "single_seed_descriptive")
        self.assertIsNone(single["confidence_interval_95"])
        changed = dict(PROTOCOL, reward_sha256="c"*64)
        self.assertEqual(compare_success(PROTOCOL, changed, [run(1,[True])], [run(1,[True])])["status"], "incomparable")
        bounded = dict(PROTOCOL, track="bounded_tuning", search_budget=20)
        other = dict(bounded, search_budget=10)
        self.assertEqual(compare_conditions(bounded, other)["status"], "incomparable")
        with self.assertRaises(ImportFailure):
            compare_success(PROTOCOL, PROTOCOL, [run(1,[True]),run(1,[False])], [run(1,[True])])


if __name__ == "__main__":
    unittest.main()
