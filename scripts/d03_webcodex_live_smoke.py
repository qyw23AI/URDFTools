#!/usr/bin/env python3
"""Verify two actually-submitted web-conversation WebCodex replies, NOT mock LLM generation.

These are persisted human-in-the-loop handoffs. The verifier does not infer
cryptographic identity of the web model, and it never calls Codex CLI.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"python"))
from urdftools.agent.webcodex_bridge import WebCodexBridge, _encoded
from urdftools.diagnosis.agent_explain import validate_explanation
from urdftools.agent.tools import _current

store=WebCodexBridge(ROOT/"artifacts/WebCodexAgent")
cases=[
    ("diagnosis",ROOT/"artifacts/D03/webcodex-live-request-status.json",
     ROOT/"artifacts/D03/webcodex-chatgpt-response.json",
     ROOT/"artifacts/D03/webcodex-chatgpt-submission.json"),
    ("model_recipe",ROOT/"artifacts/D03/webcodex-model-request-status.json",
     ROOT/"artifacts/D03/webcodex-model-response.json",
     ROOT/"artifacts/D03/webcodex-model-submission.json")
]
out=[]
source_versions_changed=[]
for kind,created_file,response_file,submitted_file in cases:
    created=json.loads(created_file.read_text())
    request_id=created["request_id"]
    current=store.status(request_id)
    original=(store._path(request_id)/"request.json").read_bytes()
    request=json.loads(original)
    raw_reply=response_file.read_bytes()
    reply=json.loads(raw_reply)
    raw_result=(store._path(request_id)/"result.json").read_bytes()
    result=json.loads(raw_result)
    submitted=json.loads(submitted_file.read_text())
    assert kind==current["kind"]==request["kind"]
    assert current["status"]=="reply_validated"
    assert request_id==reply["request_id"]==result["request_id"]
    assert hashlib.sha256(original).hexdigest()==created["request_sha256"]==reply["request_sha256"]
    assert hashlib.sha256(_encoded(reply["answer"],4*1024*1024)).hexdigest()==result["answer_sha256"]
    assert submitted["request_sha256"]==current["request_sha256"]
    assert result["validated"]["changes_applied"] is False
    assert result["provider"]=="chatgpt_web_via_webcodex"
    assert result["provenance"].startswith("submitted_through_authorized_project_bridge")
    if kind=="diagnosis":
        validated=validate_explanation(request["payload"]["bundle"],reply["answer"])
        assert len(validated["causes"])==5
        assert len(validated["recommendations"])>=1
        assert "evidence:d00" in validated["verification"]["unresolved_source_evidence_ids"]
        assert "e04-pd-contrast" in validated["verification"]["cross_source_mapping_ids"]
        assert not request["payload"]["bundle"]["performance_is_real_observation"]
        # This *recorded* web response is tied to the immutable request, not
        # to the most recent regenerated FreeCAD report. D02 rebuilds may
        # produce distinct source hashes; report staleness instead of claiming
        # the earlier ChatGPT answer addresses current CAD evidence.
        for source,digest in zip((
            ROOT/"artifacts/D00/diagnosis-graph.json",
            ROOT/"artifacts/D02/mechanical-report.json"),
            request["payload"]["source_report_sha256"]):
            actual=hashlib.sha256(source.read_bytes()).hexdigest()
            if actual != digest:
                source_versions_changed.append({"path":str(source.relative_to(ROOT)),
                    "original_sha256":digest,"current_sha256":actual,
                    "action":"new ChatGPT request required for current source version"})
    else:
        project=ROOT/"artifacts/D03/webcodex-model-project"
        revision,report_sha,recipe=_current(project)
        assert revision==request["payload"]["model_revision"]==1
        assert report_sha==request["payload"]["baseline_report_sha256"]
        assert recipe["parts"][0]["profile"]["width_mm"]==20
        suggestion=reply["answer"]
        assert suggestion["expected_revision"]==revision
        assert suggestion["recipe"]["parts"][0]["profile"]["width_mm"]==25
        assert suggestion["recipe"]["parts"][0]["density_kg_m3"]==recipe["parts"][0]["density_kg_m3"]
        preview=result["validated"]["preview"]
        assert preview["diff"]["changed_parts"]==["Leg"]
        assert (project/"proposals"/preview["proposal_id"]/"Leg.step").is_file()
        assert preview["report"]["parts"][0]["mass_kg"]>0
        # Preview-only; current model is still original 20 mm version.
        assert revision==1
    out.append({"kind":kind,"request_id":request_id,
                "response_sha256":hashlib.sha256(raw_reply).hexdigest(),
                "result_sha256":hashlib.sha256(raw_result).hexdigest(),
                "status":"validated_user_mediated_web_response",
                "auto_applied":False})

report={"status":"passed","real_web_conversation_responses":2,
        "file_roundtrips":out,
        "source_versions_changed_after_handoff":source_versions_changed,
        "historical_response_must_not_be_used_as_current":bool(source_versions_changed),
        "scope":"This validates recorded web-conversation replies and actual CAD preview, not a callable ChatGPT API.",
        "model_origin_attestation":"Tool-mediated conversational workflow; not a cryptographic model identity attestation.",
        "no_codex_cli":True,"external_training_performance_verified":False}
target=ROOT/"artifacts/D03/webcodex-live-acceptance.json"
target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"status":"passed","web_roundtrips":2,
    "types":[r["kind"] for r in out],"model_preview_only":True,
    "evidence_grounded":True,"codex_cli_required":False,
    "changed_sources_since_handoff":len(source_versions_changed),
    "artifact":"artifacts/D03/webcodex-live-acceptance.json"}))
