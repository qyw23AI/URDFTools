import hashlib
import json
from fractions import Fraction
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import av
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from b08_results_worker import compare_runs, import_bundle, list_runs
from urdftools.results.jobs import ImportFailure

SOURCES = {
    "quadruped": (ROOT / "tests/fixtures/S06/a1_description/a1.urdf",
                   ROOT / "tests/fixtures/E00/quadruped_valid.urdf"),
    "humanoid": (ROOT / "tests/fixtures/S06/reference_models/g1_description/g1_29dof.urdf",
                 ROOT / "tests/fixtures/E00/humanoid_valid.urdf"),
}

class DesktopBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = self.root / "store"

    def bundle(self, category, role):
        source_urdf = SOURCES[category][0 if role == "standard" else 1]
        name = f"{category}-{role}"
        folder = self.root / name
        folder.mkdir()
        robot = folder / "robot.urdf"
        robot.write_bytes(source_urdf.read_bytes())
        robot_hash = hashlib.sha256(robot.read_bytes()).hexdigest()
        (folder / "metrics.csv").write_text("metric,step,value,wall_time\nsuccess,1,0.5,10\n")
        (folder / "experiment.json").write_text(json.dumps({
            "schema_version": 1, "run_id": name, "robot_hash": robot_hash,
            "robot_category": category, "origin": "synthetic_fixture", "algorithm": "fixture-ppo",
            "protocol": "fixture-stairs", "license": "CC0-1.0", "algorithm_version": "1",
            "protocol_version": "1", "metrics": [{"path": "metrics.csv", "format": "csv",
                                                "units": {"success": "ratio"}}]}))
        video = folder / "episode.mp4"
        with av.open(str(video), "w") as output:
            stream = output.add_stream("mpeg4", rate=10)
            stream.width = stream.height = 64
            stream.pix_fmt = "yuv420p"
            stream.time_base = Fraction(1, 10)
            for index in range(3):
                frame = av.VideoFrame.from_ndarray(np.full((64, 64, 3), index * 20, dtype=np.uint8), format="rgb24")
                frame.pts = index
                frame.time_base = Fraction(1, 10)
                for packet in stream.encode(frame): output.mux(packet)
            for packet in stream.encode(): output.mux(packet)
        terrain = {"terrain_kind": "step", "terrain_version": "fixture-v1", "scale_mode": "physical_m",
                   "terrain_size": 0.1, "terrain_size_unit": "m", "push_force_n": 0,
                   "push_duration_s": 0, "train_seeds": [1, 2, 3], "test_seeds": [101, 102],
                   "success_definition": "cross without fall"}
        protocol = {"robot_category": category, "algorithm": "fixture-ppo", "algorithm_version": "1",
                    "protocol": "fixture-stairs", "protocol_version": "1", "reward_sha256": "a" * 64,
                    "track": "fixed_recipe", "recipe_sha256": "b" * 64, "budget_steps": 10000,
                    "paired_seed_design": True, "terrain": terrain}
        successes = [True, True, False] if role == "standard" else [True, False, False]
        (folder / "evidence.json").write_text(json.dumps({"schema_version": 1, "protocol": protocol,
            "seed_runs": [{"train_seed": seed, "status": "completed", "episodes": [value]}
                          for seed, value in zip((1, 2, 3), successes)],
            "videos": [{"path": "episode.mp4", "episode_id": "ep-101", "camera": "front",
                        "experiment_offset_s": 5, "declared_fps": 10,
                        "events": [{"episode_id": "ep-101", "experiment_time_s": 5.1,
                                    "metric": "fall", "value": 1}]}]}))
        inventory = [{"path": p.name, "size": p.stat().st_size,
                      "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                     for p in sorted(folder.iterdir())]
        (folder / "manifest.json").write_text(json.dumps({
            "bundle_id": name, "robot_hash": robot_hash, "files": inventory,
            "model": {"path": "robot.urdf", "name": name, "version": "fixture-v1",
                      "category": category, "origin": "public_import" if role == "standard" else "user_upload",
                      "license": "BSD-3-Clause" if role == "standard" else None}}))
        return folder

    def test_two_categories_standard_and_user_persist_after_restart(self):
        self.assertEqual(list_runs(self.store), {"runs": [], "verified_reference_count": 0})
        for category in SOURCES:
            for role in ("standard", "user"):
                result = import_bundle(self.store, self.bundle(category, role))
                self.assertEqual(result["rows"], 1)
                self.assertEqual(result["origin"], "synthetic_fixture")
                self.assertFalse(result["reference_performance"])
                self.assertEqual(result["evidence"]["videos"], 1)
        after_restart = list_runs(self.store)
        self.assertEqual(len(after_restart["runs"]), 4)
        self.assertEqual(after_restart["verified_reference_count"], 0)
        self.assertEqual({item["category"] for item in after_restart["runs"]}, set(SOURCES))
        self.assertEqual({item["metrics"] for item in after_restart["runs"]}, {1})
        self.assertTrue(all(item["has_evidence"] for item in after_restart["runs"]))
        for category in SOURCES:
            compared = compare_runs(self.store, f"{category}-standard", f"{category}-user")
            self.assertEqual(compared["comparison"]["comparability"]["status"], "matched")
            self.assertEqual(compared["comparison"]["status"], "compared")
            self.assertTrue(compared["fixture_only"])
            self.assertEqual(compared["reference_media"][0]["events"][0]["frame_index"], 1)

    def test_model_hash_tampering_does_not_import(self):
        folder = self.bundle("quadruped", "standard")
        (folder / "robot.urdf").write_text("<robot/>")
        with self.assertRaises(ImportFailure):
            import_bundle(self.store, folder)
        self.assertEqual(list_runs(self.store)["runs"], [])

    def test_desktop_worker_json_process_contract(self):
        folder = self.bundle("quadruped", "standard")
        command = [sys.executable, str(ROOT / "scripts/b08_results_worker.py")]
        imported = subprocess.run(command + ["import", "--store", str(self.store), "--source", str(folder)],
                                  capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(imported.stdout)["run_id"], "quadruped-standard")
        listed = subprocess.run(command + ["list", "--store", str(self.store)],
                                capture_output=True, text=True, check=True)
        self.assertEqual(len(json.loads(listed.stdout)["runs"]), 1)

if __name__ == "__main__":
    unittest.main()
