"""Numerical, provenance and error-path tests for the isolated STEP reader."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from urdftools.cad.step_reader import StepImportError, inspect_step


FIXTURE_DIR = ROOT / "tests/fixtures/C00"
MANIFEST = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))


class StepReaderTests(unittest.TestCase):
    def assert_vector_close(self, actual, expected, delta=1e-6):
        self.assertEqual(len(actual), len(expected))
        for got, want in zip(actual, expected):
            self.assertAlmostEqual(got, want, delta=delta)

    def test_fixture_manifest_hashes_and_pinned_kernel(self):
        self.assertEqual(MANIFEST["kernel_distribution"], "cadquery-ocp-novtk")
        self.assertEqual(MANIFEST["kernel_version"], "8.0.1.1.0")
        adapter = ROOT / "python/urdftools/cad/step2urdf_adapter.py"
        self.assertEqual(hashlib.sha256(adapter.read_bytes()).hexdigest(), "1be7423e3de2e7e14ba7d1fc0849d579c610cad91e493397f5c69fe24ae080cc")
        license_file = ROOT / "third_party/step2urdf-adapter/LICENSE"
        self.assertTrue(license_file.is_file())
        self.assertIn("MIT License", license_file.read_text(encoding="utf-8"))
        self.assertEqual(set(MANIFEST["files"]), {"two_part_mm.step", "single_part_m.step"})
        for name, record in MANIFEST["files"].items():
            path = FIXTURE_DIR / name
            self.assertTrue(path.is_file())
            self.assertEqual(path.stat().st_size, record["size_bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"])

    def test_two_part_mm_assembly_keeps_hierarchy_placement_and_colors(self):
        path = FIXTURE_DIR / "two_part_mm.step"
        report = inspect_step(path)
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["source"]["sha256"], MANIFEST["files"][path.name]["sha256"])
        self.assertEqual(report["units"]["source_length_units"], ["millimetre"])
        self.assertEqual(report["units"]["source_length_unit"], "mm")
        self.assertAlmostEqual(report["units"]["source_unit_scale_to_m"], 0.001)
        self.assertEqual(report["units"]["kernel_length_unit"], "mm")
        self.assertEqual(report["counts"], {
            "root_count": 1, "assembly_count": 1, "part_instance_count": 2,
            "colored_part_count": 2, "missing_color_count": 0,
        })

        root = report["assembly_roots"][0]
        self.assertEqual((root["name"], root["kind"]), ("TwoPartAssembly", "assembly"))
        self.assertEqual([child["name"] for child in root["children"]], ["BasePart", "OffsetPart"])
        parts = {part["name"]: part for part in report["parts"]}
        self.assertEqual(set(parts), {"BasePart", "OffsetPart"})
        self.assert_vector_close(parts["BasePart"]["bounds"]["dimensions_m"], [0.02, 0.01, 0.005])
        self.assert_vector_close(parts["BasePart"]["world_translation_m"], [0, 0, 0])
        self.assert_vector_close(parts["OffsetPart"]["bounds"]["dimensions_m"], [0.01, 0.006, 0.004])
        self.assert_vector_close(parts["OffsetPart"]["world_translation_m"], [0.05, 0.02, 0.01])
        self.assertEqual(parts["BasePart"]["color_source"], "definition")
        self.assertEqual(parts["OffsetPart"]["color_source"], "definition")
        self.assert_vector_close(parts["BasePart"]["color_rgb"], [0.8, 0.2, 0.1], delta=1e-4)
        self.assert_vector_close(parts["OffsetPart"]["color_rgb"], [0.1, 0.4, 0.9], delta=1e-4)
        self.assertEqual(report["adapter"]["status"], "matched")
        self.assertEqual(report["adapter"]["part_count"], 2)
        self.assertEqual(report["adapter"]["commit"], "3845072d29c0cdbd12a9b3c65808440163e32130")
        self.assertEqual(report["kernel"]["version"], "8.0.1.1.0")

    def test_single_part_meter_file_normalizes_to_si_and_keeps_missing_color_unknown(self):
        path = FIXTURE_DIR / "single_part_m.step"
        report = inspect_step(path)
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["source"]["sha256"], MANIFEST["files"][path.name]["sha256"])
        self.assertEqual(report["units"]["source_length_units"], ["metre"])
        self.assertEqual(report["units"]["source_length_unit"], "m")
        self.assertAlmostEqual(report["units"]["source_unit_scale_to_m"], 1.0)
        self.assertEqual(report["counts"]["assembly_count"], 0)
        self.assertEqual(report["counts"]["part_instance_count"], 1)
        self.assertEqual(report["counts"]["missing_color_count"], 1)
        part = report["parts"][0]
        self.assertEqual(part["name"], "MeterPart")
        self.assertIsNone(part["color_rgb"])
        self.assertEqual(part["color_source"], "missing")
        self.assertIn("missing_color", part["warnings"])
        self.assert_vector_close(part["bounds"]["dimensions_m"], [0.02, 0.01, 0.005])
        self.assertEqual(report["adapter"]["status"], "matched")
        self.assertEqual(report["adapter"]["part_count"], 1)

    def test_rejects_unsupported_extensions_and_missing_files(self):
        with tempfile.TemporaryDirectory(prefix="c00-step-invalid-") as temp:
            temp_dir = Path(temp)
            unsupported = temp_dir / "model.obj"
            unsupported.write_text("not a STEP file", encoding="utf-8")
            with self.assertRaisesRegex(StepImportError, "Unsupported CAD extension"):
                inspect_step(unsupported)
            missing = temp_dir / "missing.step"
            with self.assertRaisesRegex(StepImportError, "does not exist"):
                inspect_step(missing)


if __name__ == "__main__":
    unittest.main()
