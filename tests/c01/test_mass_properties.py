"""C01 analytical tests for STEP B-rep mass properties, tensor rotation and missing materials."""
import hashlib
import json
import math
from pathlib import Path
import sys
import unittest

import numpy as np
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from urdftools.cad.mass_properties import (
    MassPropertiesError,
    calculate_solid_mass_properties,
    compute_step_mass_properties,
    transform_mass_properties,
)
from urdftools.cad.step2urdf_adapter import load_step

FIXTURE_DIR = ROOT / "tests/fixtures/C01"
MANIFEST = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))


class MassPropertiesTests(unittest.TestCase):
    def assert_vector_close(self, actual, expected, *, atol=1e-10, rtol=1e-6):
        np.testing.assert_allclose(np.asarray(actual, dtype=float), np.asarray(expected, dtype=float), atol=atol, rtol=rtol)

    def test_fixture_hashes_and_pinned_kernel(self):
        self.assertEqual(MANIFEST["kernel_distribution"], "cadquery-ocp-novtk")
        self.assertEqual(MANIFEST["kernel_version"], "8.0.1.1.0")
        self.assertEqual(set(MANIFEST["files"]), {"box_mm.step", "offset_double_sphere_mm.step", "rotated_box_mm.step"})
        for name, record in MANIFEST["files"].items():
            path = FIXTURE_DIR / name
            self.assertTrue(path.is_file())
            self.assertEqual(path.stat().st_size, record["size_bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"])

    def test_box_mass_and_diagonal_inertia_match_closed_form(self):
        report = compute_step_mass_properties(FIXTURE_DIR / "box_mm.step", {"Box20x10x5": 1000.0})
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["units"]["source_length_unit"], "mm")
        self.assertTrue(report["assembly"]["mass_complete"])
        part = report["parts"][0]
        a, b, c = 0.02, 0.01, 0.005
        expected_volume = a * b * c
        expected_mass = 1000.0 * expected_volume
        expected_inertia = [
            [expected_mass * (b*b + c*c) / 12.0, 0.0, 0.0],
            [0.0, expected_mass * (a*a + c*c) / 12.0, 0.0],
            [0.0, 0.0, expected_mass * (a*a + b*b) / 12.0],
        ]
        self.assertAlmostEqual(part["volume_m3"], expected_volume, delta=1e-12)
        self.assertAlmostEqual(part["mass_kg"], expected_mass, delta=1e-12)
        self.assert_vector_close(part["center_of_mass_m"], [a/2, b/2, c/2])
        self.assert_vector_close(part["inertia_com_kg_m2"], expected_inertia, atol=1e-14)
        self.assertAlmostEqual(report["assembly"]["total_mass_kg"], expected_mass, delta=1e-12)
        self.assert_vector_close(report["assembly"]["inertia_about_total_com_kg_m2"], expected_inertia, atol=1e-14)

    def test_offset_double_sphere_matches_parallel_axis_formula(self):
        density = 1000.0
        radius = 0.01
        spacing = 0.05
        each_volume = 4.0 * math.pi * radius**3 / 3.0
        each_mass = density * each_volume
        expected_mass = 2.0 * each_mass
        expected_com = [spacing / 2.0, 0.0, 0.0]
        sphere_center_inertia = 2.0 * each_mass * radius**2 / 5.0
        expected_inertia = [
            [2.0 * sphere_center_inertia, 0.0, 0.0],
            [0.0, 2.0 * sphere_center_inertia + 2.0 * each_mass * (spacing/2.0)**2, 0.0],
            [0.0, 0.0, 2.0 * sphere_center_inertia + 2.0 * each_mass * (spacing/2.0)**2],
        ]
        report = compute_step_mass_properties(FIXTURE_DIR / "offset_double_sphere_mm.step", default_density_kg_m3=density)
        self.assertEqual(report["adapter"]["part_count"], 2)
        self.assertTrue(report["assembly"]["mass_complete"])
        self.assertAlmostEqual(report["assembly"]["total_volume_m3"], 2.0 * each_volume, delta=1e-11)
        self.assertAlmostEqual(report["assembly"]["total_mass_kg"], expected_mass, delta=1e-10)
        self.assert_vector_close(report["assembly"]["center_of_mass_m"], expected_com, atol=1e-9)
        self.assert_vector_close(report["assembly"]["inertia_about_total_com_kg_m2"], expected_inertia, atol=1e-12)

    def test_rotated_box_has_non_diagonal_inertia_and_transform_matches_direct_ocp(self):
        density = 1000.0
        report = compute_step_mass_properties(FIXTURE_DIR / "rotated_box_mm.step", {"RotatedBox": density})
        part = report["parts"][0]
        inertia = np.asarray(part["inertia_com_kg_m2"], dtype=float)
        self.assertAlmostEqual(inertia[0, 1], -1.25e-8, delta=1e-13)
        self.assertAlmostEqual(inertia[1, 0], -1.25e-8, delta=1e-13)
        self.assertAlmostEqual(inertia[0, 0], 2.291666666666667e-8, delta=1e-13)
        self.assert_vector_close(part["center_of_mass_m"], [0.10353553390593274, -0.009393398282201789, 0.0325])

        local_shape = BRepPrimAPI_MakeBox(20, 10, 5).Shape()
        local_props = calculate_solid_mass_properties(local_shape, density, name="local_box")
        transformed = transform_mass_properties(local_props, part["world_transform_4x4_m"])
        self.assert_vector_close(transformed["center_of_mass_m"], part["center_of_mass_m"])
        self.assert_vector_close(transformed["inertia_com_kg_m2"], part["inertia_com_kg_m2"], atol=1e-14)

    def test_missing_density_never_becomes_zero_mass_or_inertia(self):
        report = compute_step_mass_properties(FIXTURE_DIR / "box_mm.step")
        part = report["parts"][0]
        assembly = report["assembly"]
        self.assertEqual(part["status"], "missing_density")
        self.assertIsNone(part["mass_kg"])
        self.assertIsNone(part["inertia_com_kg_m2"])
        self.assertIn("material_density_missing", part["warnings"])
        self.assertFalse(assembly["mass_complete"])
        self.assertIsNone(assembly["total_mass_kg"])
        self.assertIsNone(assembly["center_of_mass_m"])
        self.assertIsNone(assembly["inertia_about_total_com_kg_m2"])
        self.assertIsNone(assembly["known_mass_subtotal_kg"])
        self.assertIn("assembly_mass_incomplete", assembly["warnings"])

    def test_partial_material_assignment_reports_known_subtotal_and_unknown_part(self):
        fixture = FIXTURE_DIR / "offset_double_sphere_mm.step"
        names = [part.name for part in load_step(str(fixture))]
        report = compute_step_mass_properties(fixture, {names[0]: 1000.0})
        self.assertEqual(report["assembly"]["known_mass_part_count"], 1)
        self.assertFalse(report["assembly"]["mass_complete"])
        self.assertIsNone(report["assembly"]["total_mass_kg"])
        self.assertIsNone(report["assembly"]["center_of_mass_m"])
        self.assertGreater(report["assembly"]["known_mass_subtotal_kg"], 0)
        self.assertEqual(report["assembly"]["unknown_parts"], [names[1]])

    def test_unmatched_density_and_approximate_geometry_are_not_silently_used(self):
        report = compute_step_mass_properties(FIXTURE_DIR / "box_mm.step", {"TypoPartName": 1000.0})
        self.assertEqual(report["unmatched_density_assignments"], ["TypoPartName"])
        self.assertIn("unmatched_density_assignments", report["warnings"])
        self.assertIsNone(report["parts"][0]["mass_kg"])

        shape = BRepPrimAPI_MakeBox(20, 10, 5).Shape()
        approximate = calculate_solid_mass_properties(shape, 1000.0, approximate=True)
        self.assertEqual(approximate["status"], "unsupported_approximate_geometry")
        self.assertIsNone(approximate["volume_m3"])
        self.assertIsNone(approximate["mass_kg"])
        self.assertIsNone(approximate["inertia_com_kg_m2"])
        self.assertIn("approximate_geometry_not_used_for_mass", approximate["warnings"])

    def test_rejects_mesh_files_as_physical_mass_sources_and_invalid_density(self):
        with self.assertRaisesRegex(MassPropertiesError, "visual/collision meshes"):
            compute_step_mass_properties(FIXTURE_DIR / "not-a-physical-mass-source.obj", default_density_kg_m3=1000.0)
        shape = BRepPrimAPI_MakeBox(20, 10, 5).Shape()
        with self.assertRaisesRegex(MassPropertiesError, "finite positive"):
            calculate_solid_mass_properties(shape, 0.0)


if __name__ == "__main__":
    unittest.main()
