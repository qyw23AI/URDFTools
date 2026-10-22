#!/usr/bin/env python3
"""Desktop bridge: suggest to isolated preview, or apply a reviewed proposal."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from urdftools.agent.providers import CodexCliProvider
from urdftools.agent.tools import preview_recipe, apply_preview


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['suggest', 'apply'])
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text())
    if args.action == 'suggest':
        current = json.loads((args.project / 'current.json').read_text())
        revision = current['revision']
        if revision != request['expected_revision']:
            raise ValueError('Model version changed before suggestion')
        recipe = json.loads((args.project / 'revisions' / f'{revision:06d}' / 'recipe.json').read_text())
        suggestion = CodexCliProvider(timeout=180).suggest(recipe, revision, request['instruction'])
        preview = preview_recipe(args.project, suggestion)
        print(json.dumps({'proposal_id': preview['proposal_id'], 'diff': preview['diff'],
                          'report': preview['report'], 'recipe': suggestion['recipe'],
                          'rationale': suggestion['rationale'], 'status': 'preview_only'}, ensure_ascii=False))
    else:
        if request.get('human_confirmed') is not True:
            raise ValueError('Explicit human confirmation required')
        result = apply_preview(args.project, request['proposal_id'], human_confirmed=True)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
