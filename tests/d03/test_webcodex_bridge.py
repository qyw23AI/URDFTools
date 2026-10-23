"""D03 WebCodex desktop/ChatGPT bridge: actual files, SHA, CAD previews, no auto-apply."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"python"))
from urdftools.agent.webcodex_bridge import WebCodexBridge, WebBridgeError, _encoded
from urdftools.diagnosis.agent_explain import ExplanationError
from urdftools.modeling.core import apply_project

SOURCE_D00=ROOT/"artifacts/D00/diagnosis-graph.json"
SOURCE_D02=ROOT/"artifacts/D02/mechanical-report.json"


def grounded_answer(bundle):
    candidates=[]
    for c in bundle["candidates"]:
        candidates.append({
            "cause_id":c["cause_id"],"status":c["status"],
            "evidence_ids":c["support_evidence_ids"],
            "counter_evidence_ids":c["counter_evidence_ids"],
            "missing_data":c["missing_data"],
            "interpretation":"现有来源仅支持需要独立复验的假设，不能确认机械设计导致结果差异。",
            "verification_action":c["verification_action"],"causal_claim":False,
        })
    return {"schema_version":1,"case_id":bundle["case_id"],
            "summary":"当前仿真观察仅支持控制配置作为待复验假设，缺乏直接机械因果证据，合成数据不能视为真实训练性能。",
            "causes":candidates,"recommendations":[{
                "cause_id":"actuator_or_controller",
                "action":"固定 URDF、记录 PD 参数与落地轨迹，在相同条件下复验而非直接修改机械几何。",
                "evidence_ids":["e04-pd-contrast"],"requires_human_confirmation":True,
                "automatically_applied":False,
                "claim_scope":"hypothesis_only_no_causal_proof"}],
            "limitations":["合成试验不是用户真实四足实验；跨来源 CAD 映射不可作为机械因果证明。"]}


def envelope(bridge, created, answer):
    return {"schema_version":1,"request_id":created["request_id"],
            "request_sha256":created["request_sha256"],"answer":answer}


def recipe(length=20):
    return {"schema_version":1,"parts":[{
        "name":"Leg","material":"declared", "density_kg_m3":2700,
        "profile":{"kind":"rectangle","width_mm":length,"height_mm":10},
        "operation":{"kind":"extrude","distance_mm":5},
        "placement_mm":[0,0,0]
    }]}


class WebCodexAgentBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="urdftools-webcodex-")
        self.addCleanup(self.tmp.cleanup)
        self.dir=Path(self.tmp.name)
        self.bridge=WebCodexBridge(self.dir/"bridge")

    def analysis_request(self):
        return self.bridge.create_diagnosis(
            instruction="请解释候选原因，不自动修改机械模型",
            diagnosis_file=SOURCE_D00,mechanical_file=SOURCE_D02)

    def test_consent_request_and_real_source_provenance(self):
        task=self.analysis_request()
        self.assertEqual(task["status"],"awaiting_chatgpt_web_reply")
        self.assertIn("@web-codex-tunnel",task["prompt"])
        self.assertIn(task["request_id"],task["prompt"])
        doc=json.loads(Path(task["request_path"]).read_text())
        self.assertEqual(doc["kind"],"diagnosis")
        self.assertTrue(doc["payload"]["synthetic_fixture"])
        self.assertTrue(doc["policy"]["no_codex_cli"])
        self.assertFalse(doc["policy"]["auto_apply"])
        self.assertEqual(len(doc["payload"]["bundle"]["candidates"]),5)

    def test_actual_json_web_reply_is_verified_and_immutable(self):
        task=self.analysis_request()
        bundle=json.loads(Path(task["request_path"]).read_text())["payload"]["bundle"]
        before=Path(task["request_path"]).read_bytes()
        reply=envelope(self.bridge,task,grounded_answer(bundle))
        received=self.bridge.submit(task["request_id"],reply)
        self.assertEqual(received["status"],"reply_validated")
        self.assertEqual(received["result"]["status"],"advice_only")
        self.assertEqual(received["result"]["advice"]["verification"]["source"],
                         "chatgpt_web_via_webcodex_bridge")
        self.assertEqual(received["result"]["advice"]["verification"]["unresolved_source_evidence_ids"],
                         ["evidence:d00"])
        self.assertFalse(received["result"]["changes_applied"])
        self.assertEqual(Path(task["request_path"]).read_bytes(),before)
        with self.assertRaisesRegex(WebBridgeError,"cannot be overwritten"):
            self.bridge.submit(task["request_id"],reply)

    def test_wrong_binding_fake_citation_and_invalid_request_rejected(self):
        task=self.analysis_request()
        source=json.loads(Path(task["request_path"]).read_text())
        answer=grounded_answer(source["payload"]["bundle"])
        wrong=envelope(self.bridge,task,answer)
        wrong["request_sha256"]="f"*64
        with self.assertRaisesRegex(WebBridgeError,"mismatched"):
            self.bridge.submit(task["request_id"],wrong)
        tampered=grounded_answer(source["payload"]["bundle"])
        tampered["recommendations"][0]["evidence_ids"]=["fabricated:123"]
        with self.assertRaises(ExplanationError):
            self.bridge.submit(task["request_id"],envelope(self.bridge,task,tampered))
        self.assertEqual(self.bridge.status(task["request_id"])["status"],
                         "awaiting_chatgpt_web_reply")
        with self.assertRaisesRegex(WebBridgeError,"Invalid request id"):
            self.bridge.status("../../../../etc/passwd")

    def test_model_revision_preview_human_only(self):
        from urdftools.agent.tools import apply_preview
        project=self.dir/"project"
        apply_project(project,recipe(),expected_revision=0)
        task=self.bridge.create_model(
            instruction="将 Leg 宽度调整为 25mm，别改密度",model_project=project,
            expected_revision=1)
        self.assertEqual(task["kind"],"model_recipe")
        raw=json.loads(Path(task["request_path"]).read_text())
        self.assertEqual(raw["payload"]["recipe"],recipe())
        self.assertEqual(raw["payload"]["model_revision"],1)
        pointer=(project/"current.json").read_bytes()
        suggestion={"schema_version":1,"action":"replace_recipe",
                    "expected_revision":1,"recipe":recipe(25),
                    "rationale":"只增加腿长、保持密度与厚度"}
        with self.assertRaisesRegex(WebBridgeError,"wrong revision"):
            wrong=copy.deepcopy(suggestion)
            wrong["expected_revision"]=2
            self.bridge.submit(task["request_id"],envelope(self.bridge,task,wrong))
        accepted=self.bridge.submit(task["request_id"],
                                    envelope(self.bridge,task,suggestion))
        self.assertEqual(accepted["result"]["status"],"preview_only")
        preview=accepted["result"]["preview"]
        self.assertIn("Leg",preview["diff"]["changed_parts"])
        self.assertEqual(pointer,(project/"current.json").read_bytes())
        self.assertTrue((project/"proposals"/preview["proposal_id"]).is_dir())
        with self.assertRaisesRegex(Exception,"confirmation"):
            apply_preview(project,preview["proposal_id"],human_confirmed=False)

    def test_stale_cad_model_refused_without_result(self):
        project=self.dir/"project"
        apply_project(project,recipe(),expected_revision=0)
        task=self.bridge.create_model(instruction="调整零件参数",model_project=project,
                                      expected_revision=1)
        apply_project(project,recipe(23),expected_revision=1)
        response={"schema_version":1,"action":"replace_recipe",
                  "expected_revision":1,"recipe":recipe(25),"rationale":"待人工复核"}
        with self.assertRaisesRegex(WebBridgeError,"modified since"):
            self.bridge.submit(task["request_id"],envelope(self.bridge,task,response))
        self.assertEqual(self.bridge.status(task["request_id"])["status"],
                         "awaiting_chatgpt_web_reply")


    def test_user_imported_urdf_static_evidence_without_raw_cad_bytes(self):
        source=ROOT/"tests/fixtures/E00/quadruped_zero_axis.urdf"
        ticket=self.bridge.create_imported_urdf(
            instruction="定位关节轴错误并列出需要的复验",
            urdf_file=source)
        row=json.loads(Path(ticket["request_path"]).read_bytes())
        evidence=row["payload"]["bundle"]["evidence"]
        self.assertEqual(row["payload"]["source_kind"],"user_imported_urdf_unverified")
        self.assertIsNone(row["payload"]["synthetic_fixture"])
        self.assertEqual(len(evidence),1)
        self.assertEqual(evidence[0]["rule"],"invalid_joint_axis")
        self.assertEqual(evidence[0]["status"],"fail")
        self.assertEqual(row["payload"]["bundle"]["candidates"][0]["status"],
                         "supported_hypothesis")
        payload=Path(ticket["request_path"]).read_text()
        self.assertNotIn("<robot",payload)
        self.assertNotIn(str(source),payload)
        self.assertFalse(row["payload"]["bundle"]["performance_is_real_observation"])

        healthy=self.bridge.create_imported_urdf(
            instruction="核查缺少机械证据的处理",
            urdf_file=ROOT/"tests/fixtures/E00/quadruped_valid.urdf")
        report=json.loads(Path(healthy["request_path"]).read_bytes())
        self.assertEqual(report["payload"]["bundle"]["evidence"][0]["status"],"unknown")
        self.assertTrue(all(x["status"]=="needs_evidence" for x in
                            report["payload"]["bundle"]["candidates"]))


    def test_import_source_change_is_flagged_not_silently_reused(self):
        original=ROOT/"tests/fixtures/E00/quadruped_valid.urdf"
        local=self.dir/"myrobot.urdf"
        local.write_bytes(original.read_bytes())
        ticket=self.bridge.create_imported_urdf(
            instruction="检查静态物理约束",urdf_file=local)
        self.assertTrue(ticket["source_current"])
        local.write_bytes(original.read_bytes()+b"\n<!-- updated -->\n")
        changed=self.bridge.status(ticket["request_id"])
        self.assertFalse(changed["source_current"])
        self.assertEqual(changed["status"],"awaiting_chatgpt_web_reply")

    def test_reject_oversized_instruction_and_oversized_reply(self):
        with self.assertRaisesRegex(WebBridgeError,"1–2000"):
            self.bridge.create_diagnosis(instruction="x"*2001,
                 diagnosis_file=SOURCE_D00, mechanical_file=SOURCE_D02)
        with self.assertRaisesRegex(WebBridgeError,"payload exceeds"):
            _encoded({"bad":"x"*(4*1024*1024+1)}, 4*1024*1024)


if __name__=="__main__":
    unittest.main()
