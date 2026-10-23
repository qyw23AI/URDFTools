"""URDFTools agent bridge to the *ChatGPT web conversation* through WebCodex.

This is not a model HTTP API: desktop queues a consented request, the human
brings it to ChatGPT with @web-codex-tunnel, and a conversation tool writes
a validated answer. No Codex CLI, API key or hidden remote task dispatch.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
from datetime import datetime, timezone

from urdftools.diagnosis.agent_explain import build_retrieval, validate_explanation
from urdftools.diagnosis.evidence_tools import EvidenceTools

ID = re.compile(r"^[0-9a-f]{32}$")
MAX_REQUEST = 128 * 1024
MAX_RESPONSE = 4 * 1024 * 1024
REQUEST_KINDS = {"diagnosis", "model_recipe"}


class WebBridgeError(ValueError):
    pass


def _encoded(value: dict, limit: int) -> bytes:
    try:
        data = (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                           separators=(",", ":")) + "\n").encode()
    except (ValueError, TypeError, OverflowError) as exc:
        raise WebBridgeError("Non-finite or invalid JSON input") from exc
    if len(data) > limit:
        raise WebBridgeError("Agent payload exceeds size limit")
    return data


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_exclusive(file: Path, content: bytes):
    """Atomic durable create without overwriting existing result, even on a race."""
    file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = file.with_name("." + secrets.token_hex(16) + ".tmp")
    try:
        with tmp.open("xb") as out:
            os.chmod(tmp, 0o600)
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.link(tmp, file)  # atomic, fails if a reply was already stored
    except FileExistsError as exc:
        raise WebBridgeError("Request or response already exists; never overwrite") from exc
    finally:
        tmp.unlink(missing_ok=True)


class WebCodexBridge:
    def __init__(self, store: str | Path):
        proposed_store = Path(store).expanduser()
        if proposed_store.is_symlink():
            raise WebBridgeError('Symlink store is not permitted')
        self.store = proposed_store.resolve()
        if self.store.is_symlink():
            raise WebBridgeError("Symlink store is not permitted")
        self.store.mkdir(mode=0o700, parents=True, exist_ok=True)

    def _path(self, request_id: str) -> Path:
        if not isinstance(request_id, str) or ID.fullmatch(request_id) is None:
            raise WebBridgeError("Invalid request id")
        path = self.store / request_id
        if path.is_symlink():
            raise WebBridgeError("Symlink request is forbidden")
        return path

    def _read_request(self, request_id: str):
        file = self._path(request_id) / "request.json"
        if file.is_symlink() or not file.is_file():
            raise WebBridgeError("Request not found")
        data = file.read_bytes()
        if len(data) > MAX_REQUEST:
            raise WebBridgeError("Oversized request")
        request = json.loads(data)
        if request.get("request_id") != request_id or request.get("kind") not in REQUEST_KINDS:
            raise WebBridgeError("Request id/kind mismatch")
        if request.get("schema_version") != 1:
            raise WebBridgeError("Unknown request schema")
        return request, _sha(data)

    def create_diagnosis(self, *, instruction: str, diagnosis_file: str | Path,
                         mechanical_file: str | Path) -> dict:
        self._instruction(instruction)
        graph = Path(diagnosis_file).read_bytes()
        mechanical = Path(mechanical_file).read_bytes()
        if len(graph) > MAX_RESPONSE or len(mechanical) > MAX_RESPONSE:
            raise WebBridgeError("Source report too large")
        bundle = build_retrieval(json.loads(graph), json.loads(mechanical))
        EvidenceTools(bundle)  # strict preflight
        return self._create("diagnosis", instruction, {
            "bundle": bundle,
            "source_report_sha256": [_sha(graph), _sha(mechanical)],
            "synthetic_fixture": not bundle["performance_is_real_observation"],
        }, source_paths=[diagnosis_file, mechanical_file])

    def create_imported_urdf(self, *, instruction: str, urdf_file: str | Path) -> dict:
        """Ground an opt-in imported URDF analysis in actual local static findings.

        Only bounded rule/number/link names enter request. Never include original
        XML, mesh bytes, local absolute paths or invented RL performance evidence.
        """
        self._instruction(instruction)
        from urdftools.evaluation.static import scan_urdf
        path=Path(urdf_file).resolve(strict=True)
        if not path.is_file() or path.suffix.lower() != ".urdf" or path.stat().st_size > 4*1024*1024:
            raise WebBridgeError("Bounded imported URDF file required")
        raw=path.read_bytes()
        scan=scan_urdf(path)
        sha=_sha(raw)
        if sha != scan["input_sha256"]:
            raise WebBridgeError("Imported source changed during local scan")
        observations=[]
        for idx, finding in enumerate(scan["findings"][:100]):
            observations.append({
                "id": f"static:{sha[:12]}:{idx}",
                "kind": "urdf_static_rule",
                "rule": finding["rule_id"],
                "object": finding["location"],
                "status": finding["status"],
                "source_kind": "user_imported_urdf_static_inspection",
                "source_sha256": sha,
                "unit": finding.get("unit"),
                "value": finding.get("observed"),
            })
        if not observations:
            observations=[{"id":f"static:{sha[:12]}:no_diagnosis",
                "kind":"static_inspection_no_findings",
                "rule":None,"object":"robot","status":"unknown",
                "source_kind":"user_imported_urdf_static_inspection",
                "source_sha256":sha}]
        causes=[]
        cause_specs=[
            ("export_or_description", "URDF 导出和语义一致性",
             "与 CAD 设计参照、关节轴、惯量和 link/joint 关系逐项比对，并保留证据来源。"),
            ("collision_or_contact","碰撞与接触配置",
             "先获取碰撞体、接触参数与无训练仿真探测记录，再判断接触风险。"),
            ("actuator_or_controller","执行器与控制器",
             "补充真实执行器标定、PD 与动作映射；URDF 静态文件不能证明控制效果。"),
            ("algorithm_or_budget","算法或外部实验协议",
             "需要独立来源的多种子与一致性协议，不能由 URDF 静态信息推导训练效果。"),
            ("mechanical_design","机械结构与质量分布",
             "必须取得可信 CAD、实测质量与独立受控实验，不能仅因静态告警自动改机械。"),
        ]
        export_support=[e["id"] for e in observations
                        if e["kind"]=="urdf_static_rule" and e["status"]=="fail"]
        for cid,label,action in cause_specs:
            support=export_support if cid=="export_or_description" else []
            causes.append({
                "cause_id":cid,"label":label,
                "status":"supported_hypothesis" if support else "needs_evidence",
                "support_evidence_ids":support,"counter_evidence_ids":[],
                "missing_data":["缺少真实运动/外部验证数据"] if cid!="export_or_description"
                               else ["缺少独立 CAD 设计侧参照"],
                "verification_action":action,"causal_claim":False,
            })
        bundle={"schema_version":1,
            "case_id":"user-urdf-"+sha[:16],"category":"user_imported_urdf",
            "symptom":"static_inspection_not_dynamics_performance",
            "performance_is_real_observation":False,
            "source_urdf_sha256":sha,"evidence":observations,
            "candidates":causes,
            "cad_review":{"status":"not_provided","unresolved_evidence_ids":[],
                          "mappings":[],"unmatched_cad_parts":[],"auto_applied":False},
            "unknowns":["Local static findings are not proof of real robot performance",
                        "No original CAD, joint torque curves, multi-seed outcomes or external training data were supplied"] }
        EvidenceTools(bundle)
        return self._create("diagnosis",instruction,{
            "bundle":bundle,"source_report_sha256":[sha],
            "synthetic_fixture":None,"source_kind":"user_imported_urdf_unverified",
            "original_urdf_not_sent":True,
        }, source_paths=[path])

    def create_model(self, *, instruction: str, model_project: str | Path,
                     expected_revision: int) -> dict:
        self._instruction(instruction)
        # This existing project helper validates immutable report hashes;
        # intentionally lazy import to avoid CAD deps for diagnosis mode.
        from urdftools.agent.tools import _current
        if (isinstance(expected_revision, bool) or
                not isinstance(expected_revision, int) or expected_revision < 1):
            raise WebBridgeError("Built model revision must be >= 1")
        project = Path(model_project).resolve(strict=True)
        revision, report_sha, recipe = _current(project)
        if revision != expected_revision or recipe is None:
            raise WebBridgeError("Model changed or not built; refresh workspace first")
        return self._create("model_recipe", instruction, {
            "model_revision": revision,
            "baseline_report_sha256": report_sha,
            "recipe": recipe,
            "recipe_sha256": _sha(_encoded(recipe, MAX_RESPONSE)),
            # Actual project location is not included in the ChatGPT-facing payload.
        }, model_project=str(project))

    @staticmethod
    def _instruction(instruction):
        if not isinstance(instruction, str) or not 1 <= len(instruction.strip()) <= 2000:
            raise WebBridgeError("Instruction must be 1–2000 characters")

    def _create(self, kind: str, instruction: str, payload: dict,
                model_project: str | None = None,
                source_paths: list[str | Path] | None = None) -> dict:
        request_id = secrets.token_hex(16)
        row = {
            "schema_version": 1, "request_id": request_id,
            "kind": kind, "status": "awaiting_chatgpt_web_reply",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "instruction": instruction, "payload": payload,
            "policy": {"requires_human_confirmation": True, "auto_apply": False,
                       "provider": "chatgpt_web_via_webcodex",
                       "no_codex_cli": True, "no_api_key": True},
        }
        # Keep on-disk trusted project location in a separate file that isn't
        # sent as part of ChatGPT request.
        _encoded(row, MAX_REQUEST)
        folder = self._path(request_id)
        folder.mkdir(mode=0o700, parents=False)
        _write_exclusive(folder / "request.json", _encoded(row, MAX_REQUEST))
        local={}
        if model_project is not None:
            local["model_project"]=model_project
        if source_paths is not None:
            local["source_paths"]=[str(Path(src).resolve(strict=True)) for src in source_paths]
        if local:
            _write_exclusive(folder / "local.json", _encoded(local, 4096))
        return self.status(request_id)

    def status(self, request_id: str) -> dict:
        row, digest = self._read_request(request_id)
        folder = self._path(request_id)
        completed = folder / "result.json"
        result = None
        if completed.exists():
            if completed.is_symlink():
                raise WebBridgeError("Result symlink not allowed")
            result = json.loads(completed.read_bytes())
            if result.get("request_sha256") != digest or result.get("request_id") != request_id:
                raise WebBridgeError("Result does not match request bytes")
        source_current=None
        settings=folder/"local.json"
        if settings.is_file() and not settings.is_symlink():
            paths=json.loads(settings.read_text()).get("source_paths")
            if paths is not None:
                expected=row["payload"].get("source_report_sha256",[])
                source_current=(len(paths)==len(expected) and all(
                    Path(path).is_file() and _sha(Path(path).read_bytes())==sha
                    for path,sha in zip(paths,expected)))
        return {
            "source_current":source_current,
            "request_id": request_id, "request_sha256": digest, "kind": row["kind"],
            "status": "reply_validated" if result else "awaiting_chatgpt_web_reply",
            "request_path": str(folder / "request.json"),
            "result_path": str(completed) if result else None,
            "result": result.get("validated") if result else None,
            "prompt": self.prompt(request_id, digest, str(folder / "request.json")) if not result else None,
        }

    @staticmethod
    def prompt(request_id, digest, request_path):
        # This copy/paste step is required: a local Electron app cannot
        # submit autonomous ChatGPT turns or call the WebCodex host as an API.
        return (
            "请在当前 ChatGPT 网页会话使用已连接 @web-codex-tunnel 插件处理 URDFTools "
            "Agent 请求（不要使用 Codex CLI）。请求 ID：" + request_id +
            "；请求 SHA256：" + digest + "。在已授权的 URDFTools 项目中读取 " +
            request_path + "，按其中 kind 和 instruction 生成受证据约束的 JSON 建议；对于 diagnosis 使用 "
            "validate_explanation 的五候选原因格式，对于 model_recipe 使用 "
            "schema_version/action=replace_recipe/expected_revision/recipe/rationale。"
            "不要把夹具当作真实性能，不自动应用建模变更。通过 "
            "scripts/webcodex_agent_bridge.py submit --id " + request_id +
            " --response <项目内临时回复JSON路径> 实际提交并检查校验结果。"
        )

    def submit(self, request_id: str, response: dict,
               *, model_project: str | Path | None = None) -> dict:
        row, source_sha = self._read_request(request_id)
        if (not isinstance(response, dict) or set(response) !=
                {"schema_version", "request_id", "request_sha256", "answer"}):
            raise WebBridgeError("Reply envelope schema invalid")
        if (response["schema_version"] != 1 or response["request_id"] != request_id
                or response["request_sha256"] != source_sha):
            raise WebBridgeError("Reply mismatched to current immutable request")
        if (self._path(request_id) / "result.json").exists():
            raise WebBridgeError("Existing validated reply cannot be overwritten")
        answer = response["answer"]
        if row["kind"] == "diagnosis":
            validated = validate_explanation(row["payload"]["bundle"], answer)
            validated["verification"]["source"] = "chatgpt_web_via_webcodex_bridge"
            validated["verification"]["provider"] = "ChatGPT web, user-initiated WebCodex handoff"
            result = {
                "status": "advice_only", "advice": validated,
                "requires_human_confirmation": True, "changes_applied": False,
            }
        else:
            from urdftools.agent.tools import _validate_suggestion, _current, preview_recipe
            _validate_suggestion(answer)
            expected = row["payload"]["model_revision"]
            if answer["expected_revision"] != expected:
                raise WebBridgeError("Model suggestion refers to wrong revision")
            settings = self._path(request_id) / "local.json"
            if settings.is_symlink() or not settings.is_file():
                raise WebBridgeError("Missing local model-project binding")
            original_project = json.loads(settings.read_text())["model_project"]
            project = Path(original_project).resolve(strict=True)
            if model_project is not None and Path(model_project).resolve() != project:
                raise WebBridgeError("Model project binding mismatch")
            current, source_report_sha, recipe = _current(project)
            if (current != expected or
                source_report_sha != row["payload"]["baseline_report_sha256"] or
                _sha(_encoded(recipe, MAX_RESPONSE)) != row["payload"]["recipe_sha256"]):
                raise WebBridgeError("Model modified since agent request; re-create request")
            preview = preview_recipe(project, answer)
            result = {
                "status": "preview_only", "preview": {
                    "proposal_id": preview["proposal_id"],
                    "expected_revision": preview["expected_revision"],
                    "diff": preview["diff"], "report": preview["report"],
                },
                "suggestion": answer,
                "requires_human_confirmation": True, "changes_applied": False,
            }
        immutable = {"schema_version": 1, "request_id": request_id,
                     "request_sha256": source_sha, "provider": "chatgpt_web_via_webcodex",
                     "provenance": "submitted_through_authorized_project_bridge_not_cryptographic_model_proof",
                     "answer_sha256": _sha(_encoded(answer, MAX_RESPONSE)),
                     "validated": result}
        _write_exclusive(self._path(request_id) / "result.json",
                         _encoded(immutable, MAX_RESPONSE))
        return self.status(request_id)
