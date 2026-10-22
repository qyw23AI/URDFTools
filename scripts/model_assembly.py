#!/usr/bin/env python3
"""Export a committed M00 revision as a named STEP assembly."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from urdftools.modeling.assembly import export_revision_assembly, AssemblyError

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('revision',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    try:
        print(json.dumps(export_revision_assembly(args.revision,args.output),ensure_ascii=False))
        return 0
    except (AssemblyError,OSError,ValueError,KeyError) as exc:
        print(json.dumps({'status':'failed','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
