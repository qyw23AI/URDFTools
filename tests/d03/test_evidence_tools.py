"""D03 controlled evidence lookup contracts on real D00/D02 artifacts."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from urdftools.diagnosis.agent_explain import build_retrieval, ExplanationError
from urdftools.diagnosis.evidence_tools import EvidenceTools, catalog


class EvidenceToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        graph=json.loads((ROOT/"artifacts/D00/diagnosis-graph.json").read_text())
        report=json.loads((ROOT/"artifacts/D02/mechanical-report.json").read_text())
        cls.bundle=build_retrieval(graph,report)

    def test_actual_d00_e04_evidence_and_cause(self):
        tool=EvidenceTools(self.bundle)
        keys=tool.invoke("list_evidence",{})
        self.assertEqual(keys["status"],"ok")
        self.assertGreater(len(keys["data"]),2)
        checked=tool.invoke("get_evidence",{"evidence_id":"e04-pd-contrast"})
        self.assertEqual(checked["status"],"ok")
        self.assertEqual(checked["data"]["source_kind"],"simulation")
        self.assertEqual(checked["data"]["unit"],"rad")
        cause=tool.invoke("get_cause",{"cause_id":"actuator_or_controller"})
        self.assertEqual(cause["data"]["support_evidence_ids"],["e04-pd-contrast"])
        self.assertEqual(cause["bundle_sha256"],checked["bundle_sha256"])

    def test_unresolved_evidence_is_not_a_resolvable_citation(self):
        tool=EvidenceTools(self.bundle)
        self.assertEqual(tool.invoke("get_evidence",{"evidence_id":"evidence:d00"})["error"]["code"],
                         "unresolved_evidence_id")
        self.assertEqual(tool.invoke("get_evidence",{"evidence_id":"fabricated:id"})["status"],"error")
        cad=tool.invoke("get_cad_mappings",{})
        self.assertIn("evidence:d00",cad["data"]["unresolved_evidence_ids"])
        self.assertEqual(cad["data"]["mappings"][0]["evidence_scope"],
                         "cross_source_unverified")
        self.assertFalse(cad["data"]["auto_applied"])

    def test_schema_and_tool_whitelist_reject_arbitrary_operations(self):
        tool=EvidenceTools(self.bundle)
        self.assertEqual(tool.invoke("run_shell",{"command":"true"})["error"]["code"],
                         "unknown_tool")
        self.assertEqual(tool.invoke("get_evidence",{"evidence_id":"e04-pd-contrast",
                          "path":"../../secret"})["error"]["code"],"invalid_arguments")
        self.assertEqual(tool.invoke("get_cause",{"cause_id":"../../../etc/passwd"})["error"]["code"],
                         "invalid_arguments")
        self.assertEqual(tool.invoke("get_cause",{"cause_id":"unregistered"})["error"]["code"],
                         "unknown_cause")
        self.assertEqual(tool.invoke("get_evidence",{"evidence_id":0})["error"]["code"],
                         "invalid_arguments")
        self.assertEqual(tool.invoke("get_evidence",{"evidence_id":"a"*4096})["error"]["code"],
                         "request_too_large")
        self.assertTrue(all(x["name"].startswith(("get_","list_")) for x in catalog()))
        self.assertFalse(any("apply" in x["name"] or "write" in x["name"] for x in catalog()))

    def test_result_is_deep_copied_from_underlying_evidence(self):
        tool=EvidenceTools(self.bundle)
        result=tool.invoke("get_cause",{"cause_id":"actuator_or_controller"})
        result["data"]["support_evidence_ids"].append("fake-id")
        again=tool.invoke("get_cause",{"cause_id":"actuator_or_controller"})
        self.assertEqual(again["data"]["support_evidence_ids"],["e04-pd-contrast"])

    def test_tampered_registry_and_applied_edit_rejected(self):
        for change in ("duplicates","cause_evidence","applied"):
            with self.subTest(change=change):
                bundle=copy.deepcopy(self.bundle)
                if change=="duplicates":
                    bundle["evidence"].append(bundle["evidence"][0])
                elif change=="cause_evidence":
                    bundle["candidates"][0]["support_evidence_ids"]=["made-up:ref"]
                else:
                    bundle["cad_review"]["auto_applied"]=True
                with self.assertRaises(ExplanationError):
                    EvidenceTools(bundle)


    def test_provider_error_classification_prioritizes_usage_limit(self):
        from urdftools.diagnosis.agent_explain import classify_codex_failure
        report='ERROR websocket tls handshake eof; {"type":"turn.failed","error":{"message":"You’ve hit your usage limit. Try again at 1:29 PM."}}'
        self.assertIn("usage limit", classify_codex_failure(report))
        self.assertIn("network", classify_codex_failure("tls handshake eof websocket"))
        self.assertIn("model/transport", classify_codex_failure("unknown backend failure"))


if __name__ == "__main__":
    unittest.main()
