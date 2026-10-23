#!/usr/bin/env python3
"""D03: real ChatGPT-login, no edit, exact grounded evidence citation workflow."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"python"))
from urdftools.diagnosis.agent_explain import build_retrieval,codex_explain
from urdftools.diagnosis.evidence_tools import EvidenceTools

def main():
    origin_d00=ROOT/"artifacts/D00/diagnosis-graph.json"
    origin_d02=ROOT/"artifacts/D02/mechanical-report.json"
    source_bytes=(origin_d00.read_bytes(),origin_d02.read_bytes())
    graph=json.loads(source_bytes[0]);mechanical=json.loads(source_bytes[1])
    bundle=build_retrieval(graph,mechanical)
    tools=EvidenceTools(bundle)
    # Actual deterministic read-only tool invocations with explicit provenance.
    checked=[tools.invoke('get_evidence',{'evidence_id':e['id']})
             for e in bundle['evidence']]
    causes=[tools.invoke('get_cause',{'cause_id':c['cause_id']})
            for c in bundle['candidates']]
    cad=tools.invoke('get_cad_mappings',{})
    assert all(x['status']=='ok' and x['read_only'] for x in checked+causes+[cad])
    assert tools.invoke('get_evidence',{'evidence_id':'evidence:d00'})['status']=='error'
    output=ROOT/'artifacts/D03';output.mkdir(exist_ok=True,parents=True)
    (output/'retrieval-summary.json').write_text(json.dumps(bundle,ensure_ascii=False,indent=2)+'\n')
    (output/'read-only-tool-audit.json').write_text(json.dumps({
        'status':'retrieved','source':'read-only deterministic D00/D02 evidence tools',
        'bundle_sha256':tools.bundle_sha256,
        'resolved_evidence_ids':[x['data']['id'] for x in checked],
        'cause_ids':[x['data']['cause_id'] for x in causes],
        'unresolved_evidence_ids':cad['data']['unresolved_evidence_ids'],
        'changes_applied':False},ensure_ascii=False,indent=2)+'\n')
    explanation=codex_explain(bundle,timeout=230)
    assert explanation["verification"]["evidence_ids_valid"]
    assert "evidence:d00" in explanation["verification"]["unresolved_source_evidence_ids"]
    assert not explanation["verification"]["changes_applied"]
    assert all(row["causal_claim"] is False for row in explanation["causes"])
    assert len(explanation["causes"])==5
    assert source_bytes==(origin_d00.read_bytes(),origin_d02.read_bytes())
    assert bundle["performance_is_real_observation"] is False
    (output/"agent-advice.json").write_text(json.dumps(explanation,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"status":"passed","provider":explanation["verification"]["provider"],
      "causes":len(explanation["causes"]),"recommendations":len(explanation["recommendations"]),
      "unresolved":explanation["verification"]["unresolved_source_evidence_ids"],
      "response_sha256":explanation["verification"]["response_sha256"],
      "evidence_references_valid":True,"applied":False,
      "artifact":"artifacts/D03/agent-advice.json"},ensure_ascii=False))

if __name__=="__main__":
    main()
