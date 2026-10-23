#!/usr/bin/env python3
"""D02 real FreeCAD STEP revision -> explicit fixture CAD mapping -> HTML/PDF sources."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"python"))
from urdftools.modeling.reconcile import compare_cad_versions
from urdftools.cad.step_reader import inspect_step
from urdftools.diagnosis.mechanical_report import build_report, render_html

def shell(*argv,timeout=150):
    completed=subprocess.run([str(x) for x in argv],cwd=ROOT,capture_output=True,text=True,timeout=timeout)
    if completed.returncode:
        raise RuntimeError(completed.stderr[-1200:]+completed.stdout[-900:])
    return completed

def main():
    out=ROOT/"artifacts/D02"
    out.mkdir(parents=True,exist_ok=True)
    graph=json.loads((ROOT/"artifacts/D00/diagnosis-graph.json").read_text())
    old=json.loads((ROOT/"artifacts/D01/parametric-leg-report.json").read_text())["plan"]
    assert old["source_evidence_ids"]==["evidence:d00"] # historical unresolved, must preserve as unknown
    with tempfile.TemporaryDirectory(prefix="d02-cad-",dir=ROOT/".tools") as tmp:
        tmp=Path(tmp)
        step_files={}
        for version in ("base","resized","topology"):
            fcstd=tmp/(version+".FCStd")
            step=tmp/(version+".step")
            shell(ROOT/".tools/cad-venv/bin/python",ROOT/"scripts/freecad_bridge.py",
                  "--make-fixture","--fixture-variant",version,"--output",fcstd)
            shell(ROOT/".tools/cad-venv/bin/python",ROOT/"scripts/freecad_bridge.py",fcstd,"--output",step)
            step_files[version]=step
        names=sorted(part["name"] for part in inspect_step(step_files["base"])["parts"])
        assert len(names)==2,names
        # Explicit synthetic annotation, not automatic fuzzy match or confirmed real CAD-to-URDF mapping.
        declared={names[0]:"leg",names[1]:"base"}
        original_sha=hashlib.sha256(step_files["base"].read_bytes()).hexdigest()
        different=compare_cad_versions(step_files["base"],step_files["resized"],
            expected_baseline_sha256=original_sha,link_mapping=declared)
        conflict=compare_cad_versions(step_files["base"],step_files["topology"],
            expected_baseline_sha256=original_sha,link_mapping=declared)
        assert different["status"]=="review_required",different
        assert conflict["status"]=="conflict",conflict
        changes=[x for x in different["relinks"] if abs(x["volume_delta_mm3"])>1]
        assert changes
        interesting=changes[0]
        explicit_name=interesting["baseline_part"]
        link=declared[explicit_name]
        joint="hip" if link=="leg" else "hip"
        e_id="e04-pd-contrast"
        mapping=[{"cad_part":explicit_name,"urdf_link":link,"urdf_joint":joint,
                  "evidence_id":e_id,"annotation_origin":"synthetic_fixture"}]
        # Source report is separately generated from a real D00 skill evaluation and
        # a CAD synthetic fixture; different origins are NOT inferred as causally linked.
        report=build_report(diagnosis=graph,ablation=old,cad_reconciliation=different,
            associations=mapping,source_urdf_xml=old["baseline"]["urdf_xml"],
            artifact_files=["artifacts/D00/diagnosis-graph.json",
                            "artifacts/D01/parametric-leg-report.json",
                            "artifacts/B07/desktop/media-view.png"],
            project_root=ROOT)
        assert report["unresolved_evidence_ids"]==["evidence:d00"]
        assert len(report["part_mappings"])==1
        assert report["part_mappings"][0]["cad_match_status"]=="relink_requires_review"
        assert report["part_mappings"][0]["cad_difference"]["baseline_part"]==explicit_name
        assert len(report["unmatched_cad_parts"])==1
        report["cad_topology_conflict_example"]=conflict["conflicts"]
        report["cad_mapping_scope"]="synthetic_fixture manual annotation; unrelated D00 evidence is NOT a mechanical effect"
        (out/"mechanical-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
        render_html(report,out/"mechanical-report.html",ROOT)
        assert "href=" in (out/"mechanical-report.html").read_text()
    print(json.dumps({"status":"passed","mapped_cad_part":explicit_name,"urdf_link":link,
       "unmatched_cad_parts":report["unmatched_cad_parts"],"unresolved_evidence":report["unresolved_evidence_ids"],
       "html":"artifacts/D02/mechanical-report.html","source_geometry_changed":True},ensure_ascii=False))

if __name__=="__main__":main()
