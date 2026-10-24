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
import shlex
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
                         mechanical_file: str | Path, mode: str = "webcodex") -> dict:
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
        }, source_paths=[diagnosis_file, mechanical_file], mode=mode)

    def create_imported_urdf(self, *, instruction: str, urdf_file: str | Path,
                             mode: str = "webcodex") -> dict:
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
        }, source_paths=[path], mode=mode)

    def create_result_comparison(self, *, result_store: str | Path, reference_id: str,
                                 candidate_id: str, instruction: str,
                                 mode: str = "webcodex") -> dict:
        """Create a bounded real-result evidence request without sending raw assets."""
        self._instruction(instruction)
        from xml.etree import ElementTree
        from urdftools.results.catalog import ResultCatalog
        from urdftools.results.jobs import ImportQueue
        from urdftools.results.workflow import ResultWorkflow
        with ImportQueue(Path(result_store) / "results") as queue:
            ResultCatalog(queue)
            workflow = ResultWorkflow(queue)
            pair = workflow.compare(reference_id, candidate_id)
            detail = {run: workflow.detail(run) for run in (reference_id, candidate_id)}
            models = {}
            paths = []
            for run in (reference_id, candidate_id):
                row = queue.db.execute("SELECT model_sha,model_name FROM result_models WHERE run_id=?", (run,)).fetchone()
                if row is None:
                    raise WebBridgeError("Both projects need linked URDF assets")
                source = queue.blobs / row["model_sha"][:2] / row["model_sha"]
                raw = source.read_bytes()
                if len(raw) > 4 * 1024 * 1024 or _sha(raw) != row["model_sha"] or b"<!DOCTYPE" in raw.upper():
                    raise WebBridgeError("Bounded unchanged URDF asset required")
                robot = ElementTree.fromstring(raw)
                if robot.tag != "robot":
                    raise WebBridgeError("Linked model is not a URDF robot")
                models[run] = {"name": row["model_name"], "sha256": row["model_sha"],
                               "links": len(robot.findall("link")), "joints": len(robot.findall("joint")),
                               "joint_types": sorted({joint.attrib.get("type", "unknown") for joint in robot.findall("joint")})}
                paths.append(source)
            for run in (reference_id, candidate_id):
                sha = detail[run]["source_sha256"]
                path = queue.blobs / sha[:2] / sha
                if _sha(path.read_bytes()) != sha:
                    raise WebBridgeError("Comparison evidence changed")
                paths.append(path)
            candidate_model = models[candidate_id]
            reference_model = models[reference_id]
            condition = pair["comparison"]["comparability"]
            evidence = [
                {"id": "protocol:comparison", "kind": "protocol_comparability",
                 "status": condition["status"], "source_kind": "user_imported_training_protocol",
                 "source_sha256": detail[candidate_id]["source_sha256"],
                 "value": {"reasons": condition["reasons"][:12],
                           "sampling_unit": pair["comparison"]["sampling_unit"]}},
                {"id": "outcome:success", "kind": "multi_seed_success_comparison",
                 "status": pair["comparison"]["status"], "source_kind": "user_imported_training_outcomes",
                 "source_sha256": detail[candidate_id]["source_sha256"],
                 "value": {"candidate_mean": pair["comparison"]["candidate_mean"],
                           "reference_mean": pair["comparison"]["reference_mean"],
                           "difference": pair["comparison"]["difference"],
                           "confidence_interval_95": pair["comparison"]["confidence_interval_95"]}},
            ]
            for role, run in (("candidate", candidate_id), ("reference", reference_id)):
                model = models[run]
                evidence.append({"id": "urdf:" + role, "kind": "urdf_structure_summary",
                                 "status": "observed", "source_kind": "linked_urdf_asset",
                                 "source_sha256": model["sha256"], "value": model})
                config_sha = detail[run]["protocol"].get("source_config_sha256")
                if isinstance(config_sha, str) and len(config_sha) == 64:
                    config_file = queue.blobs / config_sha[:2] / config_sha
                    if config_file.is_file() and config_file.stat().st_size <= 16 * 1024 * 1024:
                        raw_config = config_file.read_bytes()
                        if _sha(raw_config) != config_sha:
                            raise WebBridgeError("Training configuration changed")
                        config = json.loads(raw_config)
                        arguments = config.get("args", {}) if isinstance(config, dict) else {}
                        if not isinstance(arguments, dict):
                            arguments = {}
                        selected = ("task", "stage", "terrain", "iterations", "num_envs",
                                    "rollout_steps", "episode_seconds", "wm_batch", "wm_length",
                                    "wm_updates", "reward_schedule_scale", "seed")
                        summary = {key: arguments[key] for key in selected if key in arguments and
                                   type(arguments[key]) in (str, int, float, bool)}
                        evidence.append({"id": "config:" + role, "kind": "effective_training_configuration",
                                         "status": "observed", "source_kind": "imported_config_json",
                                         "source_sha256": config_sha, "value": summary})
                        paths.append(config_file)
                auxiliary = detail[run]["protocol"].get("auxiliary_sha256", {})
                if isinstance(auxiliary, dict):
                    for name in ("gait_metrics.json", "validation.json", "evaluation.json", "progress.json"):
                        sha = auxiliary.get(name)
                        if not isinstance(sha, str) or len(sha) != 64:
                            continue
                        report_file = queue.blobs / sha[:2] / sha
                        if not report_file.is_file() or report_file.stat().st_size > 4 * 1024 * 1024:
                            continue
                        raw_report = report_file.read_bytes()
                        if _sha(raw_report) != sha:
                            raise WebBridgeError("Imported training report changed")
                        report = json.loads(raw_report)
                        if not isinstance(report, dict):
                            continue
                        allowed = ("status", "iterations", "environment_steps", "resets",
                                   "stance_slip_mean", "tilt_xy_square_mean",
                                   "diagonal_contact_agreement", "saturation_fraction",
                                   "world_model_updates", "depth_predictor_updates")
                        summary = {key: report[key] for key in allowed if key in report and
                                   type(report[key]) in (str, int, float, bool)}
                        evidence.append({"id": f"report:{role}:{name.split('.')[0]}",
                                         "kind": "training_report_summary", "status": "descriptive_only",
                                         "source_kind": name, "source_sha256": sha, "value": summary})
                        paths.append(report_file)
                for index, video in enumerate(detail[run]["media"][:8]):
                    evidence.append({"id": f"video:{role}:{index}", "kind": "video_metadata_only",
                                     "status": "metadata_only", "source_kind": "imported_gait_video",
                                     "source_sha256": video["source_sha256"],
                                     "value": {"episode_id": video["video"]["episode_id"],
                                               "camera": video["video"]["camera"],
                                               "frame_count": video["video"]["frame_count"],
                                               "gap_frames": video["video"]["suspected_gap_frame_indices"][:24]}})
                metric_rows = queue.db.execute("""SELECT metric,step,value,unit,source_sha FROM scalar_metrics
                    WHERE run_id=? ORDER BY metric,step DESC,row_index DESC""", (run,))
                seen = set()
                for row in metric_rows:
                    if row["metric"] in seen:
                        continue
                    seen.add(row["metric"])
                    evidence.append({"id": f"metric:{role}:{len(seen)}", "kind": "last_training_scalar",
                                     "status": "observed", "source_kind": "imported_scalar_series",
                                     "source_sha256": row["source_sha"],
                                     "value": {"metric": row["metric"][:100], "step": row["step"],
                                               "value": row["value"], "unit": row["unit"][:40]}})
                    if len(seen) >= 12:
                        break
            cause_specs = [
                ("export_or_description", "URDF 导出和结构描述",
                 ["urdf:candidate", "urdf:reference"], "核查两份 URDF 的关节、惯量与原始 CAD；结构差异本身不证明训练差异。"),
                ("collision_or_contact", "碰撞与接触配置", [],
                 "读取碰撞体、接触参数与步态事件；仅视频元数据不足以判断接触机制。"),
                ("actuator_or_controller", "执行器与控制器", [],
                 "取得执行器标定、PD 增益、动作映射与同条件控制日志。"),
                ("algorithm_or_budget", "算法、配置与训练预算",
                 ["protocol:comparison", "outcome:success"] +
                 [f"config:{role}" for role in ("candidate", "reference") if
                  any(item["id"] == f"config:{role}" for item in evidence)] +
                 [item["id"] for item in evidence if item["id"].startswith("report:")],
                 "复核算法版本、奖励、预算、地形和独立种子；不可比时先修正协议。"),
                ("mechanical_design", "机械结构与质量分布",
                 ["urdf:candidate", "urdf:reference"],
                 "用 CAD 与质量实测检查机械差异，并以受控实验验证因果假设。"),
            ]
            causes = [{"cause_id": cid, "label": label, "status": "needs_evidence",
                       "support_evidence_ids": support, "counter_evidence_ids": [],
                       "missing_data": ["缺少能独立验证因果关系的对照实验"],
                       "verification_action": action, "causal_claim": False}
                      for cid, label, support, action in cause_specs]
            case_key = _sha((reference_id + "\0" + candidate_id + "\0" +
                             detail[reference_id]["source_sha256"] +
                             detail[candidate_id]["source_sha256"]).encode())[:16]
            bundle = {"schema_version": 1, "case_id": "results-" + case_key,
                      "category": "external_training_pair", "symptom": "candidate_vs_standard",
                      "performance_is_real_observation": not pair["fixture_only"],
                      "source_urdf_sha256": candidate_model["sha256"], "evidence": evidence,
                      "candidates": causes,
                      "cad_review": {"status": "not_provided", "unresolved_evidence_ids": [],
                                     "mappings": [], "unmatched_cad_parts": [], "auto_applied": False},
                      "unknowns": ["上传者的训练结果尚未获得独立第三方复现",
                                   "原始训练目录可能没有独立评估回合，缺失时不得计算成功率或归因",
                                   "视频只传递帧数、缺帧与事件元数据，模型未看到视频画面",
                                   "模型结构摘要不能替代 CAD、动力学、执行器与接触数据"]}
            EvidenceTools(bundle)
            hashes = [_sha(path.read_bytes()) for path in paths]
        return self._create("diagnosis", instruction, {
            "bundle": bundle, "source_report_sha256": hashes,
            "synthetic_fixture": pair["fixture_only"], "source_kind": "user_imported_result_comparison",
            "original_urdf_not_sent": True, "original_video_not_sent": True,
        }, source_paths=paths, mode=mode)

    def create_model(self, *, instruction: str, model_project: str | Path,
                     expected_revision: int, mode: str = "webcodex") -> dict:
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
        }, model_project=str(project), mode=mode)

    @staticmethod
    def _instruction(instruction):
        if not isinstance(instruction, str) or not 1 <= len(instruction.strip()) <= 2000:
            raise WebBridgeError("Instruction must be 1–2000 characters")

    def _create(self, kind: str, instruction: str, payload: dict,
                model_project: str | None = None,
                source_paths: list[str | Path] | None = None,
                mode: str = "webcodex") -> dict:
        if mode not in {"webcodex", "cli"}:
            raise WebBridgeError("Unknown agent mode")
        request_id = secrets.token_hex(16)
        row = {
            "schema_version": 1, "request_id": request_id,
            "kind": kind, "status": ("awaiting_chatgpt_web_reply" if mode == "webcodex"
                                      else "awaiting_codex_cli_run"),
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "instruction": instruction, "payload": payload,
            "policy": {"requires_human_confirmation": True, "auto_apply": False,
                       "provider": ("chatgpt_web_via_webcodex" if mode == "webcodex"
                                    else "codex_cli_chatgpt"),
                       "no_codex_cli": mode == "webcodex", "no_api_key": True},
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
            "status": "reply_validated" if result else row["status"],
            "request_path": str(folder / "request.json"),
            "result_path": str(completed) if result else None,
            "result": result.get("validated") if result else None,
            "prompt": (self.prompt(request_id, digest, str(folder / "request.json"))
                       if not result and row["policy"]["provider"] == "chatgpt_web_via_webcodex"
                       else None),
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
            "scripts/webcodex_agent_bridge.py --store " +
            shlex.quote(str(Path(request_path).parent.parent)) + " submit --id " + request_id +
            " --response <项目内临时回复JSON路径> 实际提交并检查校验结果。"
        )

    def run_codex_cli(self, request_id: str) -> dict:
        """Run only after an explicit desktop click using existing ChatGPT login."""
        row, digest = self._read_request(request_id)
        if row["policy"]["provider"] != "codex_cli_chatgpt":
            raise WebBridgeError("Request did not authorize Codex CLI")
        if self.status(request_id)["source_current"] is False:
            raise WebBridgeError("Source changed since request; create a new request")
        if (self._path(request_id) / "result.json").exists():
            raise WebBridgeError("Existing validated reply cannot be overwritten")
        if row["kind"] == "diagnosis":
            from urdftools.diagnosis.agent_explain import codex_explain
            answer = codex_explain(row["payload"]["bundle"])
            answer.pop("verification", None)
        else:
            from urdftools.agent.providers import CodexCliProvider
            from urdftools.agent.tools import _current
            payload = row["payload"]
            settings = self._path(request_id) / "local.json"
            if settings.is_symlink() or not settings.is_file():
                raise WebBridgeError("Missing local model-project binding")
            project = Path(json.loads(settings.read_text())["model_project"]).resolve(strict=True)
            revision, report_sha, recipe = _current(project)
            if (revision != payload["model_revision"] or
                report_sha != payload["baseline_report_sha256"] or
                _sha(_encoded(recipe, MAX_RESPONSE)) != payload["recipe_sha256"]):
                raise WebBridgeError("Model modified since agent request; re-create request")
            answer = CodexCliProvider().suggest(payload["recipe"],
                                                 payload["model_revision"],
                                                 row["instruction"])
        return self.submit(request_id, {
            "schema_version": 1, "request_id": request_id,
            "request_sha256": digest, "answer": answer,
        }, provider="codex_cli_chatgpt")

    def submit(self, request_id: str, response: dict,
               *, model_project: str | Path | None = None,
               provider: str = "chatgpt_web_via_webcodex") -> dict:
        if provider not in {"chatgpt_web_via_webcodex", "codex_cli_chatgpt"}:
            raise WebBridgeError("Unknown agent provider")
        row, source_sha = self._read_request(request_id)
        if row["policy"]["provider"] != provider:
            raise WebBridgeError("Reply provider does not match selected request mode")
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
            validated["verification"]["source"] = (
                "chatgpt_web_via_webcodex_bridge" if provider == "chatgpt_web_via_webcodex"
                else provider)
            validated["verification"]["provider"] = (
                "ChatGPT web, user-initiated WebCodex handoff" if provider == "chatgpt_web_via_webcodex"
                else "Codex CLI, explicitly started with existing ChatGPT login")
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
                     "request_sha256": source_sha, "provider": provider,
                     "provenance": ("submitted_through_authorized_project_bridge_not_cryptographic_model_proof"
                                    if provider == "chatgpt_web_via_webcodex" else
                                    "explicit_local_codex_cli_turn"),
                     "answer_sha256": _sha(_encoded(answer, MAX_RESPONSE)),
                     "validated": result}
        _write_exclusive(self._path(request_id) / "result.json",
                         _encoded(immutable, MAX_RESPONSE))
        return self.status(request_id)
