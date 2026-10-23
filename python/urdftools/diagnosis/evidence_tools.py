"""Bounded, read-only evidence tool dispatcher for D03 agent review.

No filesystem, network, arbitrary evaluator, edits, or schema fallbacks are exposed.
Unknown IDs, even if mentioned in source proposals, are not resolvable citations.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .agent_explain import ExplanationError

ID = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")
MAX_REQUEST_BYTES = 2048
MAX_RESPONSE_BYTES = 65536
TOOLS = {
    "list_evidence": {
        "description": "List bounded, source-provenanced evidence ids and statuses.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "required": [], "properties": {}},
    },
    "get_evidence": {
        "description": "Retrieve exactly one existing evidence record by its registered id.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "required": ["evidence_id"],
                        "properties": {"evidence_id": {"type": "string", "maxLength": 160}}},
    },
    "get_cause": {
        "description": "Read one registered competing cause and its supporting and contradicting ids.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "required": ["cause_id"],
                        "properties": {"cause_id": {"type": "string", "maxLength": 160}}},
    },
    "get_cad_mappings": {
        "description": "Read all explicitly annotated CAD part/link/joint mappings and unresolved ids.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "required": [], "properties": {}},
    },
}


def catalog() -> list[dict]:
    return [dict(name=name, description=value["description"],
                 inputSchema=value["inputSchema"]) for name, value in TOOLS.items()]


class EvidenceTools:
    def __init__(self, bundle: dict):
        if not isinstance(bundle, dict) or bundle.get("schema_version") != 1:
            raise ExplanationError("Versioned evidence bundle required")
        if bundle.get("cad_review", {}).get("auto_applied") is not False:
            raise ExplanationError("Read-only evidence must not contain applied CAD changes")
        e = bundle.get("evidence")
        causes = bundle.get("candidates")
        if not isinstance(e, list) or not isinstance(causes, list) or len(e) > 128:
            raise ExplanationError("Bounded evidence lists required")
        self.by_id = {}
        for item in e:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or (
                not ID.fullmatch(item["id"]) or item["id"] in self.by_id
            ):
                raise ExplanationError("Duplicate or ungrounded evidence id")
            self.by_id[item["id"]] = item
        self.causes = {}
        for item in causes:
            if not isinstance(item, dict) or not isinstance(item.get("cause_id"), str) or (
                not ID.fullmatch(item["cause_id"]) or item["cause_id"] in self.causes
            ):
                raise ExplanationError("Duplicate cause id")
            for key in ("support_evidence_ids", "counter_evidence_ids"):
                ids = item.get(key)
                if not isinstance(ids, list) or any(i not in self.by_id for i in ids):
                    raise ExplanationError("Cause evidence reference unresolved")
            self.causes[item["cause_id"]] = item
        self.cad = bundle["cad_review"]
        for item in self.cad.get("mappings", []):
            if item.get("evidence_id") not in self.by_id:
                raise ExplanationError("Mapping references unresolved id")
        self.bundle_sha256 = hashlib.sha256(json.dumps(
            bundle, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()

    def invoke(self, tool: str, arguments: dict[str, Any]) -> dict:
        if not isinstance(tool, str) or tool not in TOOLS:
            return self._error(str(tool), "unknown_tool")
        if not isinstance(arguments, dict):
            return self._error(tool, "invalid_arguments")
        try:
            encoded = json.dumps(arguments, allow_nan=False)
        except (TypeError, ValueError):
            return self._error(tool, "invalid_arguments")
        if len(encoded.encode()) > MAX_REQUEST_BYTES:
            return self._error(tool, "request_too_large")
        required = TOOLS[tool]["inputSchema"]["required"]
        if set(arguments) != set(required) or any(
            not isinstance(v, str) or not ID.fullmatch(v) for v in arguments.values()
        ):
            return self._error(tool, "invalid_arguments")
        if tool == "list_evidence":
            data = [{"id": item["id"], "kind": item.get("kind"),
                     "status": item.get("status"),
                     "source_sha256": item.get("source_sha256")}
                    for item in self.by_id.values()]
        elif tool == "get_evidence":
            data = self.by_id.get(arguments["evidence_id"])
            if data is None:
                return self._error(tool, "unresolved_evidence_id")
        elif tool == "get_cause":
            data = self.causes.get(arguments["cause_id"])
            if data is None:
                return self._error(tool, "unknown_cause")
        else:
            data = self.cad
        # Return a deep copy; callers cannot mutate this dispatcher or its source.
        serialized = json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False)
        if len(serialized.encode()) > MAX_RESPONSE_BYTES:
            return self._error(tool, "response_too_large")
        return {"schema_version": 1, "status": "ok", "tool": tool,
                "bundle_sha256": self.bundle_sha256,
                "data": json.loads(serialized), "read_only": True}

    def _error(self, tool, code):
        return {"schema_version": 1, "status": "error", "tool": tool,
                "error": {"code": code}, "bundle_sha256": self.bundle_sha256,
                "read_only": True}
