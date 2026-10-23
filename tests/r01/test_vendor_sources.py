"""R01 pin and loss-audit regressions on original vendor URDF bytes."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.r01_vendor_model_smoke import SPECS,STAMP,analyze


class UnitreeSourceTests(unittest.TestCase):
    def test_sources_license_and_immutable_pinned_hashes(self):
        self.assertEqual(STAMP["source_commit"],
                         "5994d4faef0a9cadd3287f8de0199a67eeb2a259")
        for label,spec in SPECS.items():
            with self.subTest(label=label):
                source=spec["folder"]/spec["urdf"]
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                                 spec["expected_sha256"])
                self.assertIn(b"BSD 3-Clause",spec["license"].read_bytes())
                self.assertGreater(sum(f.stat().st_size for f in spec["folder"].rglob("*")
                                       if f.is_file()),10_000)

    def test_engine_and_original_viewer_assets_have_separate_truth(self):
        original={label:hashlib.sha256((v["folder"]/v["urdf"]).read_bytes()).hexdigest()
                  for label,v in SPECS.items()}
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            a=analyze("a1",folder)
            b=analyze("go2",folder)
            self.assertEqual((a["compiled_dof"],b["compiled_dof"]),(12,12))
            self.assertEqual(a["engine_original_source_status"],"compiled")
            self.assertEqual(b["engine_original_source_status"],"rejected")
            self.assertEqual(len(b["removed_visual_elements"]),17)
            self.assertNotEqual(b["source_sha256"],b["simulation_derived_sha256"])
            self.assertGreater(a["source_asset_count"],5)
            self.assertGreater(b["source_asset_count"],5)
            self.assertFalse(a["training_ready"])
            self.assertFalse(b["training_ready"])
            for label,spec in SPECS.items():
                self.assertEqual(hashlib.sha256(
                    (spec["folder"]/spec["urdf"]).read_bytes()).hexdigest(),original[label])

    def test_license_metadata_defects_not_hidden(self):
        package=(ROOT/"tests/fixtures/S06/a1_description/package.xml").read_text()
        self.assertIn("<license>TODO</license>",package)
        self.assertFalse((ROOT/"tests/fixtures/S06/README.md").read_text().count("not") == 0)


if __name__=="__main__":
    unittest.main()
