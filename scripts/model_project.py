#!/usr/bin/env python3
"""Apply one allowlisted modeling recipe as a new immutable project revision."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from urdftools.modeling.core import apply_project, ModelingError


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recipe',type=Path)
    parser.add_argument('--project',required=True,type=Path)
    parser.add_argument('--expected-revision',required=True,type=int)
    args=parser.parse_args()
    try:
        if args.recipe.stat().st_size > 4*1024*1024:
            raise ModelingError('Model recipe exceeds 4 MiB')
        result=apply_project(args.project,json.loads(args.recipe.read_text()),expected_revision=args.expected_revision)
        print(json.dumps(result,ensure_ascii=False))
        return 0
    except (ModelingError,OSError,ValueError,TypeError) as exc:
        print(json.dumps({'status':'failed','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
