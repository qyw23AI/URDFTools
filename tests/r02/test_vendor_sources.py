"""R02 pinned humanoid source, source mutation and MuJoCo joint-map regression."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.r02_vendor_model_smoke import COMMIT, SPECS, H1_MANIFEST, analyze, inspect_source


class HumanoidSourceTests(unittest.TestCase):
    def test_source_hashes_and_joint_group_dimensions(self):
        self.assertEqual(COMMIT, "5994d4faef0a9cadd3287f8de0199a67eeb2a259")
        self.assertEqual(H1_MANIFEST["source_commit"], COMMIT)
        self.assertEqual(next(f["sha256"] for f in H1_MANIFEST["files"] if f["path"] == "urdf/h1.urdf"),
                         "ebd495cba7887406c406b8441a5e2dd712f8da91dcb60e7b099cbfa3adf2efa5")
        for label, spec in SPECS.items():
            with self.subTest(model=label):
                result = inspect_source(label)
                self.assertEqual(result["source_1d_dof"], spec["dof"])
                self.assertEqual(result["source_links"], spec["links"])
                self.assertEqual(result["source_joints"], spec["joints"])
                self.assertEqual(len(result["joint_groups"]["legs"]), spec["leg_dof"])
                self.assertEqual(len(result["joint_groups"]["arms"]), spec["arm_dof"])
                self.assertEqual(len(result["joint_groups"]["trunk"]), spec["trunk_dof"])
                self.assertEqual(hashlib.sha256(result["raw"]).hexdigest(), spec["sha256"])

    def test_native_compile_and_simulation_derivatives_are_audited(self):
        before = {label: hashlib.sha256((spec["folder"] / spec["urdf"]).read_bytes()).hexdigest()
                  for label, spec in SPECS.items()}
        with tempfile.TemporaryDirectory(dir=ROOT / ".tools") as tmp:
            for label, spec in SPECS.items():
                with self.subTest(model=label):
                    data = analyze(label, Path(tmp))
                    self.assertEqual(data["compiled_dof"], spec["dof"])
                    self.assertEqual(set(data["compiled_joint_names"]), set(inspect_source(label)["joint_names"]))
                    self.assertTrue(data["collision_elements_preserved"])
                    self.assertFalse(data["training_ready"])
                    self.assertEqual(data["source_hardware_calibration"], "unverified")
        for label, spec in SPECS.items():
            self.assertEqual(hashlib.sha256((spec["folder"] / spec["urdf"]).read_bytes()).hexdigest(),
                             before[label])

    def test_invalid_joint_group_cannot_be_silently_classified(self):
        for label in SPECS:
            source = inspect_source(label)
            groups = source["joint_groups"]
            all_names = groups["legs"] + groups["arms"] + groups["trunk"]
            self.assertEqual(len(all_names), len(set(all_names)))
            self.assertEqual(len(all_names), source["source_1d_dof"])
            self.assertNotIn("floating_base_joint", all_names)

    def test_vendor_source_contains_real_visual_and_collision_geometry(self):
        for label in SPECS:
            with self.subTest(model=label):
                root = inspect_source(label)["root"]
                self.assertGreaterEqual(len(root.findall(".//visual")), 20)
                self.assertGreaterEqual(len(root.findall(".//collision")), 20)


if __name__ == "__main__":
    unittest.main()
