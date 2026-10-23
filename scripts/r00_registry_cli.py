#!/usr/bin/env python3
"""User-controlled local reference model import and read-only catalog listing."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"python"))
from urdftools.reference.registry import ModelRegistry


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--store",required=True,type=Path)
    sub=parser.add_subparsers(dest="action",required=True)
    sub.add_parser("list")
    imp=sub.add_parser("import")
    imp.add_argument("--urdf",required=True,type=Path)
    imp.add_argument("--name",required=True)
    imp.add_argument("--version",required=True)
    imp.add_argument("--category",required=True)
    imp.add_argument("--origin",required=True)
    imp.add_argument("--license-id")
    imp.add_argument("--expected-sha256")
    args=parser.parse_args()
    with ModelRegistry(args.store) as r:
        if args.action=="list":
            response={"models":r.list_models()}
        else:
            response={"model":r.import_file(args.urdf,name=args.name,version=args.version,
                         category=args.category,origin=args.origin,
                         license_id=args.license_id,expected_sha256=args.expected_sha256)}
    print(json.dumps(response,sort_keys=True,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
