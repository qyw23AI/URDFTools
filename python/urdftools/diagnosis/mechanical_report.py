"""D02 mechanical engineering report: explicit, reviewable CAD/URDF mapping and bounded local links.

This module never guesses CAD topology matches or claims a physical robot outcome.
"""
from __future__ import annotations
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.parse import quote
import xml.etree.ElementTree as ET

ID = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")


class MechanicalReportError(ValueError):
    pass


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def build_report(*, diagnosis: dict, ablation: dict, cad_reconciliation: dict,
                 associations: list[dict], source_urdf_xml: str,
                 artifact_files: list[str], project_root: str | Path) -> dict:
    """Inputs: D00 diagnosis, D01 proposed plan, M02 real STEP reconciliation.

    associations are explicitly user-provided fixtures/sidecars, never inferred by name.
    """
    project_root=Path(project_root).resolve()
    if diagnosis.get("schema_version") != 1 or ablation.get("schema_version") != 1:
        raise MechanicalReportError("Versioned diagnosis and ablation required")
    if ablation.get("status")!="proposed" or cad_reconciliation.get("requires_human_confirmation") is not True:
        raise MechanicalReportError("Only proposals and unaccepted CAD reconciliation are reportable")
    if cad_reconciliation.get("automatically_applied") is not False:
        raise MechanicalReportError("CAD must not be auto-applied")
    for key in ("baseline_sha256","returned_sha256"):
        if not HEX.fullmatch(str(cad_reconciliation.get(key,""))):
            raise MechanicalReportError("Real source STEP SHA256 required")
    if len(associations)>128 or not isinstance(associations,list):
        raise MechanicalReportError("Bounded explicit part associations required")
    root=ET.fromstring(source_urdf_xml)
    if root.tag!="robot":raise MechanicalReportError("Invalid URDF")
    source_links={n.get("name") for n in root.findall("link")}
    source_joints={n.get("name") for n in root.findall("joint")}
    asset_sha=_digest(source_urdf_xml.encode())
    if asset_sha!=ablation["baseline"]["urdf_sha256"]:
        raise MechanicalReportError("Plan and source URDF bytes differ")

    evidence_index={e["id"]:e for e in diagnosis.get("evidence",[])}
    if len(evidence_index)!=len(diagnosis.get("evidence",[])):
        raise MechanicalReportError("Duplicate evidence in diagnosis")
    unresolved_ids=sorted(set(ablation.get("source_evidence_ids",[]))-set(evidence_index))
    candidate_ids={cause["id"] for cause in diagnosis.get("candidate_causes",[])}
    references=[]
    for item in associations:
        if not isinstance(item,dict) or set(item)!={"cad_part","urdf_link","urdf_joint","evidence_id","annotation_origin"}:
            raise MechanicalReportError("Explicit mapping fields required")
        if item["annotation_origin"] not in ("synthetic_fixture","user_reviewed"):
            raise MechanicalReportError("Only annotated mapping is allowed")
        if item["urdf_link"] not in source_links or item["urdf_joint"] not in source_joints:
            raise MechanicalReportError("Mapping must name actual URDF link/joint")
        if item["evidence_id"] not in evidence_index:
            raise MechanicalReportError("Mapping has unresolved evidence id")
        if not ID.fullmatch(item["cad_part"]):
            raise MechanicalReportError("Invalid CAD part id")
        relinks=[link for link in cad_reconciliation.get("relinks",[])
                 if link.get("baseline_part")==item["cad_part"]]
        conflicts=[v for v in cad_reconciliation.get("conflicts",[])
                   if v.get("part")==item["cad_part"]]
        if len(relinks)+len(conflicts)!=1:
            raise MechanicalReportError("CAD part absent or ambiguous in real reconciliation")
        matched=relinks[0] if relinks else conflicts[0]
        if matched.get("link") is not None and matched["link"]!=item["urdf_link"]:
            raise MechanicalReportError("CAD recorded link conflicts with annotation")
        source_evidence=evidence_index[item["evidence_id"]]
        references.append({
            "cad_part":item["cad_part"],"urdf_link":item["urdf_link"],
            "urdf_joint":item["urdf_joint"],"evidence_id":item["evidence_id"],
            "annotation_origin":item["annotation_origin"],
            "cad_match_status":"relink_requires_review" if relinks else "topology_unresolved",
            "cad_difference":matched,"evidence_source_sha256":source_evidence.get("source_sha256"),
            "evidence_scope":("same_source" if source_evidence.get("source_sha256")==asset_sha else "cross_source_unverified"),
            "verified_mechanical_causality":False,
        })
    # Missing or unmatched links are visible, not silently inferred.
    covered={part["cad_part"] for part in references}
    unlinked=sorted({part["baseline_part"] for part in cad_reconciliation.get("relinks",[])
                     if part["baseline_part"] not in covered}
                    |{c["part"] for c in cad_reconciliation.get("conflicts",[])
                      if c.get("part") not in covered})
    assets=[]
    for relative in artifact_files:
        if not isinstance(relative,str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise MechanicalReportError("Artifact link must be bounded relative path")
        path=(project_root/relative).resolve()
        if not path.is_relative_to(project_root) or not path.is_file():
            raise MechanicalReportError("Artifact link missing or escapes project")
        assets.append({"relative_path":relative,"sha256":_digest(path.read_bytes()),
                       "size_bytes":path.stat().st_size})
    return {
        "schema_version":1,"status":"review_required","case_id":diagnosis["case_id"],
        "report_language":"zh-CN","evidence_ids":sorted(evidence_index),
        "unresolved_evidence_ids":unresolved_ids,"cause_ids":sorted(candidate_ids),
        "candidate_causes":diagnosis["candidate_causes"],
        "cad_baseline_sha256":cad_reconciliation["baseline_sha256"],
        "cad_returned_sha256":cad_reconciliation["returned_sha256"],
        "source_urdf_sha256":asset_sha,"part_mappings":references,
        "unmatched_cad_parts":unlinked,"related_artifacts":assets,
        "predicted_change":{"parameter":ablation["single_variable"]["parameter"],
            "from_mm":ablation["single_variable"]["baseline_mm"],
            "to_mm":ablation["single_variable"]["variant_mm"],
            "baseline_mass_kg":ablation["baseline"]["mass_kg"],
            "variant_mass_kg":ablation["variant"]["mass_kg"],
            "evidence_is_prediction_only":True},
        "requires_human_confirmation":True,"automatically_applied":False,
        "limitations":["CAD mapping is a labeled fixture or human annotation, not automated SolidWorks feature-tree matching",
                       "Unknown/unresolved or cross-source evidence cannot justify modification",
                       "Synthetic data and static CAD checks do not prove real-world performance"],
        "next_action":"人工复核零件与 frame，重新导出并通过相同外部评估协议复验。",
    }


def render_html(report: dict, output: str | Path, root: str | Path) -> Path:
    dest=Path(output).resolve()
    root=Path(root).resolve()
    if not dest.is_relative_to(root):
        raise MechanicalReportError("Report must be inside project")
    dest.parent.mkdir(parents=True,exist_ok=True)
    esc=lambda obj: html.escape(str(obj),quote=True)
    rows=[]
    for entry in report["part_mappings"]:
        rows.append("<tr>"+ "".join(f"<td>{esc(entry.get(key,''))}</td>"
                     for key in ("cad_part","urdf_link","urdf_joint","evidence_id","cad_match_status"))+"</tr>")
    link_items=[]
    for asset in report["related_artifacts"]:
        file=(root/asset["relative_path"]).resolve()
        href=quote(file.relative_to(dest.parent),safe="/.-_") if file.is_relative_to(dest.parent) else \
             quote(str(Path(__import__('os').path.relpath(file,dest.parent))),safe="/.-_")
        link_items.append(f'<li><a href="{esc(href)}">{esc(asset["relative_path"])}</a> '
                          f'({asset["size_bytes"]} bytes; SHA256 {esc(asset["sha256"])})</li>')
    causes=[]
    for cause in report["candidate_causes"]:
        causes.append(f'<li><strong>{esc(cause["label"])}</strong>: {esc(cause["status"])}; '
                      f'复验: {esc(cause["verification_action"])}; 证据: '
                      f'{esc(", ".join(cause["support_evidence_ids"]))}</li>')
    content=f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>URDFTools 机械组诊断报告</title><style>
body{{font-family:system-ui,"Noto Sans CJK SC",sans-serif;max-width:900px;margin:2em auto;line-height:1.65;padding:0 1em}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #aaa;padding:.5em}}
.warning{{font-weight:600}}@media print{{a{{color:black}}}}</style></head>
<body><h1>URDFTools 机械组诊断报告</h1>
<p class="warning">待人工确认：这是带来源的机械修改提议，并非真实机械性能验证。</p>
<p>案例：{esc(report["case_id"])}；原始 URDF SHA256：{esc(report["source_urdf_sha256"])}</p>
<h2>CAD 零件、URDF Link/Joint 与证据映射</h2>
<table><thead><tr><th>CAD part</th><th>URDF Link</th><th>Joint</th><th>Evidence ID</th><th>审核状态</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<p>未匹配 CAD 零件：{esc(", ".join(report["unmatched_cad_parts"]) or "无")}</p>
<p>缺失证据：{esc(", ".join(report["unresolved_evidence_ids"]) or "无")}</p>
<h2>预测变化（不可直接断言训练效果）</h2>
<p>{esc(report["predicted_change"]["parameter"])}: {esc(report["predicted_change"]["from_mm"])} → {esc(report["predicted_change"]["to_mm"])} mm；
质量 {esc(report["predicted_change"]["baseline_mass_kg"])} → {esc(report["predicted_change"]["variant_mass_kg"])} kg。</p>
<h2>竞争性候选原因与复验</h2><ul>{''.join(causes)}</ul>
<h2>证据/视频/数据文件</h2><ul>{''.join(link_items)}</ul>
<h2>限制和下一步</h2><ul>{''.join('<li>'+esc(v)+'</li>' for v in report["limitations"])}</ul>
<p>{esc(report["next_action"])}</p></body></html>"""
    dest.write_text(content,encoding="utf-8")
    return dest
