"""Shared, bounded product tool dispatcher for CLI and local MCP stdio."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Any

from urdftools.agent.tools import preview_recipe
from urdftools.importers import ImportService


ROOT = Path(__file__).resolve().parents[3]

TOOLS = {
    'import_source': {'description': 'Copy and inspect a local URDF, ZIP, or folder inside the configured workspace.',
        'inputSchema': {'type': 'object', 'additionalProperties': False, 'required': ['source'],
            'properties': {'source': {'type': 'string'}}}},
    'preview_model_recipe': {'description': 'Build a CAD suggestion in an isolated preview; never apply it.',
        'inputSchema': {'type': 'object', 'additionalProperties': False, 'required': ['suggestion'],
            'properties': {'suggestion': {'type': 'object'}}}},
    'inspect_step_conversion': {'description': 'Inspect a STEP file and propose robot links and joints without exporting.',
        'inputSchema': {'type': 'object', 'additionalProperties': False, 'required': ['source'],
            'properties': {'source': {'type': 'string'}}}},
    'validate_urdf_package': {'description': 'Independently check a local URDF ZIP and compile its physics in MuJoCo. Does not assess RL training quality.',
        'inputSchema': {'type': 'object', 'additionalProperties': False, 'required': ['source'],
            'properties': {'source': {'type': 'string'}}}},
}


class FacadeError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _source(workspace: Path, raw: Any, suffixes: tuple[str, ...] | None = None) -> Path:
    if not isinstance(raw, str) or not raw or len(raw) > 4096:
        raise FacadeError('invalid_path', 'A bounded relative source path is required')
    pure = PurePosixPath(raw)
    if pure.is_absolute() or '..' in pure.parts or '\\' in raw or ':' in raw:
        raise FacadeError('invalid_path', 'Source must be relative to the configured workspace')
    candidate = (workspace / raw).resolve()
    if not candidate.is_relative_to(workspace) or not candidate.exists():
        raise FacadeError('invalid_path', 'Source is missing or escapes the workspace')
    if suffixes and (not candidate.is_file() or candidate.suffix.lower() not in suffixes):
        raise FacadeError('invalid_path', 'Source has an unsupported file type')
    return candidate


def _storage(workspace: Path, relative: str) -> Path:
    candidate = (workspace / relative).resolve()
    if not candidate.is_relative_to(workspace):
        raise FacadeError('invalid_path', 'Tool storage escapes the workspace')
    return candidate


def _worker(python: str, script: str, source: Path) -> dict:
    command = [str(ROOT / python), str(ROOT / script), str(source)]
    try:
        completed = subprocess.run(command, cwd=ROOT, env={'PATH': '/usr/bin:/bin'},
                                   capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FacadeError('worker_unavailable', 'Local validation worker unavailable') from exc
    if len(completed.stdout) > 4 * 1024 * 1024 or len(completed.stderr) > 4 * 1024 * 1024:
        raise FacadeError('worker_invalid', 'Local worker output exceeded limit')
    if completed.returncode:
        raise FacadeError('validation_failed', completed.stderr[-2000:] or 'Local worker rejected input')
    try:
        return json.loads(completed.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise FacadeError('worker_invalid', 'Local worker returned invalid JSON') from exc


def call_tool(workspace: str | Path, name: str, arguments: dict) -> dict:
    """CLI and MCP share this exact result/error envelope and access policy."""
    try:
        base = Path(workspace).resolve(strict=True)
        if not base.is_dir():
            raise FacadeError('invalid_workspace', 'Workspace is not a directory')
        if name not in TOOLS:
            raise FacadeError('unknown_tool', 'Tool is not registered')
        schema = TOOLS[name]['inputSchema']
        if not isinstance(arguments, dict) or set(arguments) != set(schema['required']):
            raise FacadeError('invalid_arguments', 'Tool arguments do not match schema')
        if name == 'import_source':
            source = _source(base, arguments['source'])
            data = ImportService(_storage(base, '.urdftools/imports')).ingest(source)
        elif name == 'preview_model_recipe':
            data = preview_recipe(_storage(base, '.urdftools/modeling'), arguments['suggestion'])
        elif name == 'inspect_step_conversion':
            source = _source(base, arguments['source'], ('.step', '.stp'))
            data = _worker('.tools/cad-venv/bin/python', 'scripts/cad_joint_wizard.py', source)
        else:
            source = _source(base, arguments['source'], ('.zip',))
            data = _worker('.tools/sim-venv/bin/python', 'scripts/validate_cad_package.py', source)
        return {'schema_version': 1, 'status': 'ok', 'tool': name, 'data': data}
    except FacadeError as exc:
        return {'schema_version': 1, 'status': 'error', 'tool': name,
                'error': {'code': exc.code, 'message': str(exc)}}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {'schema_version': 1, 'status': 'error', 'tool': name,
                'error': {'code': 'tool_failed', 'message': str(exc)[:2000]}}


def serve_mcp(workspace: str | Path) -> int:
    """Legacy MCP stdio JSON-RPC, compatible with clients that initialize 2025-06-18."""
    for line in sys.stdin:
        if len(line) > 4 * 1024 * 1024:
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict) or request.get('jsonrpc') != '2.0':
                continue
            method = request.get('method')
            if method == 'notifications/initialized':
                continue
            identifier = request.get('id')
            if identifier is None:
                continue
            if method == 'initialize':
                result = {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'urdftools', 'version': '0.1.0'}}
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools': [{'name': name, **definition} for name, definition in TOOLS.items()]}
            elif method == 'tools/call':
                params = request.get('params') or {}
                envelope = call_tool(workspace, params.get('name'), params.get('arguments', {}))
                result = {'content': [{'type': 'text', 'text': json.dumps(envelope, ensure_ascii=False)}],
                          'structuredContent': envelope, 'isError': envelope['status'] == 'error'}
            else:
                response = {'jsonrpc': '2.0', 'id': identifier,
                            'error': {'code': -32601, 'message': 'Method not found'}}
                print(json.dumps(response, ensure_ascii=False), flush=True)
                continue
            print(json.dumps({'jsonrpc': '2.0', 'id': identifier, 'result': result}, ensure_ascii=False), flush=True)
        except (ValueError, TypeError, KeyError):
            continue
    return 0
