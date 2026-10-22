#!/usr/bin/env python3
"""A00 real ChatGPT Codex suggestion to isolated CAD preview acceptance."""
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from urdftools.agent.providers import CodexCliProvider
from urdftools.agent.tools import preview_recipe, apply_preview
from urdftools.modeling.core import apply_project

recipe = {'schema_version': 1, 'parts': [{'name': 'Body', 'material': 'user declared',
    'density_kg_m3': 2700, 'profile': {'kind': 'rectangle', 'width_mm': 20, 'height_mm': 10},
    'operation': {'kind': 'extrude', 'distance_mm': 5}, 'placement_mm': [0, 0, 0]}]}
with tempfile.TemporaryDirectory(prefix='a00-real-cli-') as tmp:
    project = Path(tmp) / 'project'
    first = apply_project(project, recipe, expected_revision=0)
    before = (project / 'current.json').read_bytes()
    suggestion = CodexCliProvider(timeout=180).suggest(
        recipe, 1, 'Increase Body profile width_mm from 20 to 30. Keep all other values unchanged.')
    assert suggestion['recipe']['parts'][0]['profile']['width_mm'] == 30
    assert suggestion['recipe']['parts'][0]['profile']['height_mm'] == 10
    proposal = preview_recipe(project, suggestion)
    assert (project / 'current.json').read_bytes() == before
    assert proposal['report']['parts'][0]['mass_kg'] > first['report']['parts'][0]['mass_kg']
    accepted = apply_preview(project, proposal['proposal_id'], human_confirmed=True)
    assert accepted['revision'] == 2
    print(json.dumps({'provider': 'ChatGPT Codex CLI', 'preview_only': True,
                      'width_mm': 30, 'mass_kg_before': first['report']['parts'][0]['mass_kg'],
                      'mass_kg_after': accepted['report']['parts'][0]['mass_kg'],
                      'revision_after_confirmation': accepted['revision']}))
