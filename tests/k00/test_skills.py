import json
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
import tempfile
import unittest
from urdftools.evaluation.skills import SkillError, discover_skills, run_skill

ROOT = Path(__file__).resolve().parents[2]


class TestSkills(unittest.TestCase):
    def setUp(self):
        self.skills = discover_skills(ROOT / "skills")

    def test_builtins(self):
        self.assertTrue({"inertia_basics", "frame_basics", "contact_basics", "statistics_basics"} <= self.skills.keys())

    def test_inertia(self):
        skill = self.skills["inertia_basics"]
        run = lambda a: run_skill(skill, {"mass_matrix": {"tensor_kg_m2": a}})
        self.assertTrue(run([[2,0,0],[0,3,0],[0,0,4]])["passed"])
        self.assertEqual(run([[1,0,0],[0,1,0],[0,0,5]])["results"][0]["reason"], "triangle_inequality")
        self.assertFalse(run([[1,2,0],[0,2,0],[0,0,3]])["passed"])

    def test_frame(self):
        skill = self.skills["frame_basics"]
        run = lambda r: run_skill(skill, {"frame_rotation": {"rotation": r}})
        a = math.sqrt(.5)
        self.assertTrue(run([[a,-a,0],[a,a,0],[0,0,1]])["passed"])
        self.assertFalse(run([[-1,0,0],[0,1,0],[0,0,1]])["passed"])

    def test_contact(self):
        skill = self.skills["contact_basics"]
        run = lambda t: run_skill(skill, {"friction_cone": {
            "normal_force_n": 10, "tangential_force_n": t, "friction_coefficient": .4}})
        self.assertTrue(run(3)["passed"])
        self.assertFalse(run(5)["passed"])

    def test_statistics(self):
        skill = self.skills["statistics_basics"]
        run = lambda v: run_skill(skill, {"sample_summary": {"samples": v}})
        self.assertAlmostEqual(run([1,2,3,4])["results"][0]["mean"], 2.5)
        self.assertFalse(run([1])["passed"])

    def test_local_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"local"/"custom_frame"
            path.mkdir(parents=True)
            manifest = {"schema_version": 1, "id": "custom_frame", "version": "1.0.0",
                        "source": "test", "description": "user supplied local manifest",
                        "rules": [{"id": "check", "tool": "coordinate_frame", "config": {}}]}
            (path/"manifest.json").write_text(json.dumps(manifest))
            skill = discover_skills(tmp)["custom_frame"]
            self.assertTrue(run_skill(skill, {"check": {"rotation": [[1,0,0],[0,1,0],[0,0,1]]}})["passed"])
            manifest["rules"][0]["tool"] = "unapproved_tool"
            (path/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaises(SkillError):
                discover_skills(tmp)
            manifest["rules"][0]["tool"] = "coordinate_frame"
            manifest["unexpected"] = "bad"
            (path/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaises(SkillError):
                discover_skills(tmp)

    def test_input_validation(self):
        with self.assertRaises(SkillError):
            run_skill(self.skills["inertia_basics"], {"mass_matrix": {"tensor_kg_m2":
                [[float("nan"),0,0],[0,1,0],[0,0,1]]}})
        with self.assertRaises(SkillError):
            run_skill(self.skills["statistics_basics"], {"sample_summary": {"samples": [True,2]}})

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)/"local"
            parent.mkdir()
            (parent/"shortcut").symlink_to(ROOT/"skills"/"builtin"/"frame_basics", target_is_directory=True)
            with self.assertRaises(SkillError):
                discover_skills(tmp)


if __name__ == "__main__":
    unittest.main()
