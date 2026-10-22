#!/usr/bin/env python3
"""Convert IGES or BREP solid geometry to STEP with a machine-readable loss report."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from urdftools.cad.exchange import convert_to_step, ExchangeError


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--brep-unit',choices=['mm','m'])
    args=parser.parse_args()
    try:
        print(json.dumps(convert_to_step(args.source,args.output,brep_unit=args.brep_unit),ensure_ascii=False))
        return 0
    except (ExchangeError,OSError) as exc:
        print(json.dumps({'status':'failed','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
