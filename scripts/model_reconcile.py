#!/usr/bin/env python3
"""Produce a review-only CAD return diff; never change model or link mapping."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from urdftools.modeling.reconcile import compare_cad_versions,ReconcileError

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline',type=Path)
    parser.add_argument('returned',type=Path)
    parser.add_argument('--baseline-sha256',required=True)
    parser.add_argument('--mapping',type=Path)
    args=parser.parse_args()
    try:
        mapping=json.loads(args.mapping.read_text()) if args.mapping else None
        print(json.dumps(compare_cad_versions(args.baseline,args.returned,
          expected_baseline_sha256=args.baseline_sha256,link_mapping=mapping),ensure_ascii=False))
        return 0
    except (ReconcileError,OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'status':'failed','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
