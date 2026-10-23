"""D03 prevent citations hallucinations, omitted counterevidence and silent CAD edits."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"python"))
from urdftools.diagnosis.agent_explain import (
    build_retrieval,validate_explanation,ExplanationError,
)


class AgentGroundingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.diagnosis=json.loads((ROOT/"artifacts/D00/diagnosis-graph.json").read_text())
        cls.report=json.loads((ROOT/"artifacts/D02/mechanical-report.json").read_text())
        cls.bundle=build_retrieval(cls.diagnosis,cls.report)

    def sample(self):
        bundle=self.bundle
        causes=[{"cause_id":c["cause_id"],"status":c["status"],
                 "evidence_ids":list(c["support_evidence_ids"]),
                 "counter_evidence_ids":list(c["counter_evidence_ids"]),
                 "missing_data":list(c["missing_data"]),
                 "interpretation":"原始数据尚不足以判断机械因果。",
                 "verification_action":c["verification_action"],
                 "causal_claim":False} for c in bundle["candidates"]]
        return {"schema_version":1,"case_id":bundle["case_id"],
                "summary":"本报告只说明已有信息，未验证真实机械因果。",
                "causes":causes,
                "recommendations":[{"cause_id":"actuator_or_controller",
                    "action":"固定机器人 URDF，审查 PD 增益，独立复验后再提出 CAD 变更。",
                    "evidence_ids":["e04-pd-contrast"],
                    "requires_human_confirmation":True,"automatically_applied":False,
                    "claim_scope":"hypothesis_only_no_causal_proof"}],
                "limitations":["Synthetic fixture cannot support actual performance conclusions."]}

    def test_bounded_retrieval_and_actual_citation_success(self):
        ret=validate_explanation(self.bundle,self.sample())
        self.assertEqual(len(ret["causes"]),5)
        self.assertTrue(ret["verification"]["evidence_ids_valid"])
        self.assertFalse(ret["verification"]["changes_applied"])
        self.assertIn("evidence:d00",ret["verification"]["unresolved_source_evidence_ids"])
        self.assertIn("e04-pd-contrast",ret["verification"]["cross_source_mapping_ids"])

    def test_hallucinated_citation_rejected(self):
        for field in ("recommendation","support"):
            with self.subTest(field=field):
                altered=self.sample()
                if field=="recommendation":
                    altered["recommendations"][0]["evidence_ids"]=["fake:evidence"]
                else:
                    candidate=next(x for x in altered["causes"] if x["cause_id"]=="actuator_or_controller")
                    candidate["evidence_ids"]=["fake:evidence"]
                with self.assertRaisesRegex(ExplanationError,"citations|citation"):
                    validate_explanation(self.bundle,altered)

    def test_recommendation_cannot_launder_other_causes_evidence(self):
        altered=self.sample()
        altered["recommendations"][0]["cause_id"]="mechanical_design"
        # The PD simulation is real evidence, but not evidence that a
        # mechanical design change is warranted.
        with self.assertRaisesRegex(ExplanationError,"unrelated"):
            validate_explanation(self.bundle,altered)
        altered["recommendations"][0]["evidence_ids"]=[]
        result=validate_explanation(self.bundle,altered)
        self.assertTrue(result["verification"]["needs_human_review"])

    def test_missing_counterevidence_rejected(self):
        bundle=copy.deepcopy(self.bundle)
        target=next(x for x in bundle["candidates"] if x["cause_id"]=="actuator_or_controller")
        target["counter_evidence_ids"]=["e04-pd-contrast"]
        with self.assertRaisesRegex(ExplanationError,"Contradictory"):
            validate_explanation(bundle,self.sample())

    def test_missing_does_not_increase_confidence(self):
        altered=self.sample()
        c=next(x for x in altered["causes"] if x["cause_id"]=="mechanical_design")
        c["status"]="mechanical_design_confirmed"
        with self.assertRaisesRegex(ExplanationError,"elevate"):
            validate_explanation(self.bundle,altered)
        altered=self.sample()
        c=next(x for x in altered["causes"] if x["cause_id"]=="mechanical_design")
        c["causal_claim"]=True
        with self.assertRaisesRegex(ExplanationError,"elevate"):
            validate_explanation(self.bundle,altered)

    def test_agent_edit_tool_and_unreviewed_change_forbidden(self):
        for field,value in (("automatically_applied",True),
                            ("requires_human_confirmation",False),
                            ("claim_scope","real_hardware_proof")):
            with self.subTest(field=field):
                altered=self.sample()
                altered["recommendations"][0][field]=value
                with self.assertRaises(ExplanationError):
                    validate_explanation(self.bundle,altered)
        altered=self.sample()
        altered["apply_cad"]=True
        with self.assertRaisesRegex(ExplanationError,"exact"):
            validate_explanation(self.bundle,altered)

    def test_missing_evidence_or_tampered_d02_mapping_rejected(self):
        modified=copy.deepcopy(self.report)
        modified["part_mappings"][0]["evidence_id"]="nonexistent:test"
        with self.assertRaisesRegex(ExplanationError,"references missing"):
            build_retrieval(self.diagnosis,modified)
        modified=copy.deepcopy(self.diagnosis)
        modified["evidence"].append(copy.deepcopy(modified["evidence"][0]))
        with self.assertRaisesRegex(ExplanationError,"duplicated"):
            build_retrieval(modified,self.report)


if __name__=="__main__":
    unittest.main()
