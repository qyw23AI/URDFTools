"""D02 mechanical report constraints: auditable mapping, missing IDs, real links and HTML injection."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"python"))
from urdftools.diagnosis.mechanical_report import build_report,render_html,MechanicalReportError


class MechanicalReportTests(unittest.TestCase):
    def setUp(self):
        self.diagnosis=json.loads((ROOT/"artifacts/D00/diagnosis-graph.json").read_text())
        self.plan=json.loads((ROOT/"artifacts/D01/parametric-leg-report.json").read_text())["plan"]
        self.reconcile={"status":"review_required","baseline_sha256":"1"*64,
                        "returned_sha256":"2"*64,"automatically_applied":False,
                        "requires_human_confirmation":True,
                        "relinks":[{"baseline_part":"ArmLink","returned_part":"ArmLink",
                                    "link":"leg","volume_delta_mm3":25.0}],
                        "conflicts":[{"part":"LostBracket","kind":"topology_changed",
                                      "preserved_link":"base"}]}
        self.mapping=[{"cad_part":"ArmLink","urdf_link":"leg","urdf_joint":"hip",
                       "evidence_id":"e04-pd-contrast","annotation_origin":"synthetic_fixture"}]
    def make(self,**changes):
        args={"diagnosis":self.diagnosis,"ablation":self.plan,
              "cad_reconciliation":self.reconcile,"associations":self.mapping,
              "source_urdf_xml":self.plan["baseline"]["urdf_xml"],
              "artifact_files":["artifacts/B07/desktop/media-view.png"],
              "project_root":ROOT}
        args.update(changes)
        return build_report(**args)
    def test_explicit_part_and_missing_evidence_remain_visible(self):
        report=self.make()
        self.assertEqual(report["part_mappings"][0]["cad_part"],"ArmLink")
        self.assertEqual(report["part_mappings"][0]["urdf_link"],"leg")
        self.assertEqual(report["part_mappings"][0]["evidence_scope"],"cross_source_unverified")
        self.assertFalse(report["part_mappings"][0]["verified_mechanical_causality"])
        self.assertEqual(report["unmatched_cad_parts"],["LostBracket"])
        self.assertEqual(report["unresolved_evidence_ids"],["evidence:d00"])
        self.assertEqual(len(report["related_artifacts"]),1)
        self.assertFalse(report["automatically_applied"])
    def test_foreign_evidence_or_forged_part_rejected(self):
        for key,value,pattern in [
            ("evidence_id","fabricated:123","unresolved evidence"),
            ("cad_part","fabricated","absent or ambiguous"),
            ("urdf_link","fake_link","actual URDF")]:
            association=copy.deepcopy(self.mapping)
            association[0][key]=value
            with self.subTest(key=key), self.assertRaisesRegex(MechanicalReportError,pattern):
                self.make(associations=association)
    def test_html_escaping_and_links_point_to_real_content(self):
        report=self.make()
        report["case_id"]="<script>alert('bad')</script>"
        with tempfile.TemporaryDirectory(dir=ROOT/".tools") as tmp:
            html=render_html(report,Path(tmp)/"report.html",ROOT).read_text()
        self.assertIn("&lt;script&gt;",html)
        self.assertNotIn("<script>",html)
        self.assertIn("href=",html)
        self.assertIn("无法", "无法解析")
    def test_missing_artifact_and_untrusted_path_fail(self):
        for artifact in ("../etc/passwd","artifacts/D02/not-existent-file.mp4"):
            with self.subTest(artifact=artifact), self.assertRaises(MechanicalReportError):
                self.make(artifact_files=[artifact])
    def test_tampered_ablation_urdf_rejected(self):
        with self.assertRaisesRegex(MechanicalReportError,"bytes differ"):
            self.make(source_urdf_xml=self.plan["variant"]["urdf_xml"])
    def test_topology_conflict_not_misreported_as_matching(self):
        association=[{"cad_part":"LostBracket","urdf_link":"base","urdf_joint":"hip",
                       "evidence_id":"e04-pd-contrast","annotation_origin":"synthetic_fixture"}]
        report=self.make(associations=association)
        self.assertEqual(report["part_mappings"][0]["cad_match_status"],"topology_unresolved")


if __name__=="__main__":unittest.main()
