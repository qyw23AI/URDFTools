#!/usr/bin/env python3
"""D03 read-only retrieval of real D00/D02 files; does not claim an LLM answer."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"python"))
from urdftools.diagnosis.agent_explain import build_retrieval
from urdftools.diagnosis.evidence_tools import EvidenceTools, catalog

def main():
    paths=[ROOT/"artifacts/D00/diagnosis-graph.json",
           ROOT/"artifacts/D02/mechanical-report.json"]
    original=[p.read_bytes() for p in paths]
    bundle=build_retrieval(*(json.loads(b) for b in original))
    agent_tools=EvidenceTools(bundle)
    resolved=[]
    for e in bundle["evidence"]:
        lookup=agent_tools.invoke("get_evidence",{"evidence_id":e["id"]})
        assert lookup["status"]=="ok" and lookup["data"]["id"]==e["id"]
        assert lookup["read_only"] and lookup["bundle_sha256"]==agent_tools.bundle_sha256
        resolved.append(e["id"])
    causes=[]
    for cause in bundle["candidates"]:
        lookup=agent_tools.invoke("get_cause",{"cause_id":cause["cause_id"]})
        assert lookup["status"]=="ok"
        assert lookup["data"]["support_evidence_ids"]==cause["support_evidence_ids"]
        causes.append(cause["cause_id"])
    assert len(causes)==5
    cad=agent_tools.invoke("get_cad_mappings",{})
    assert cad["status"]=="ok" and "evidence:d00" in cad["data"]["unresolved_evidence_ids"]
    assert agent_tools.invoke("get_evidence",{"evidence_id":"evidence:d00"})["status"]=="error"
    assert agent_tools.invoke("get_evidence",{"evidence_id":"fake:id"})["status"]=="error"
    assert agent_tools.invoke("run_shell",{"command":"anything"})["status"]=="error"
    assert [p.read_bytes() for p in paths]==original
    output=ROOT/"artifacts/D03"
    output.mkdir(parents=True,exist_ok=True)
    report={"status":"passed","kind":"read_only_retrieval_only_not_llm_generation",
            "source_hashes":{p.name:hashlib.sha256(b).hexdigest()
                             for p,b in zip(paths,original)},
            "bundle_sha256":agent_tools.bundle_sha256,
            "registered_tools":[item["name"] for item in catalog()],
            "resolved_evidence_ids":resolved,"cause_ids":causes,
            "unresolved_evidence_ids":cad["data"]["unresolved_evidence_ids"],
            "cross_source_mapping_ids":[m["evidence_id"] for m in cad["data"]["mappings"]
                                        if m["evidence_scope"]!="same_source"],
            "simulation_evidence_not_real_hardware":True,"changes_applied":False}
    (output/"read-only-tool-audit.json").write_text(json.dumps(
        report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"status":"passed","tools":len(report["registered_tools"]),
                      "resolved_evidence":len(resolved),"causes":len(causes),
                      "unresolved_ids":report["unresolved_evidence_ids"],
                      "real_llm_response":False},ensure_ascii=False))

if __name__=="__main__":
    main()
