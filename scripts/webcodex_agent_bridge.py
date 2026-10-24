#!/usr/bin/env python3
"""Desktop/WebCodex handoff: native file queue; no model CLI or HTTP inference."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from urdftools.agent.webcodex_bridge import WebCodexBridge, WebBridgeError
from urdftools.agent.providers import ProviderError
from urdftools.diagnosis.agent_explain import ExplanationProviderError


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store",type=Path,default=ROOT/"artifacts/WebCodexAgent")
    sub=parser.add_subparsers(dest="action",required=True)
    analysis=sub.add_parser("create-analysis")
    analysis.add_argument("--instruction",required=True)
    analysis.add_argument("--mode",choices=["webcodex","cli"],default="webcodex")
    analysis.add_argument("--diagnosis",type=Path,default=ROOT/"artifacts/D00/diagnosis-graph.json")
    analysis.add_argument("--mechanical",type=Path,default=ROOT/"artifacts/D02/mechanical-report.json")
    imported=sub.add_parser('create-urdf')
    imported.add_argument('--instruction',required=True)
    imported.add_argument('--mode',choices=["webcodex","cli"],default="webcodex")
    imported.add_argument('--urdf',required=True,type=Path)
    result_analysis=sub.add_parser('create-result-analysis')
    result_analysis.add_argument('--instruction',required=True)
    result_analysis.add_argument('--mode',choices=['webcodex','cli'],default='webcodex')
    result_analysis.add_argument('--result-store',required=True,type=Path)
    result_analysis.add_argument('--reference',required=True)
    result_analysis.add_argument('--candidate',required=True)
    model=sub.add_parser("create-model")
    model.add_argument("--instruction",required=True)
    model.add_argument("--mode",choices=["webcodex","cli"],default="webcodex")
    model.add_argument("--project",type=Path,required=True)
    model.add_argument("--revision",type=int,required=True)
    status=sub.add_parser("status")
    status.add_argument("--id",required=True)
    cli=sub.add_parser("run-cli")
    cli.add_argument("--id",required=True)
    submit=sub.add_parser("submit")
    submit.add_argument("--id",required=True)
    submit.add_argument("--response",type=Path,required=True)
    args=parser.parse_args()
    try:
        store=WebCodexBridge(args.store)
        if args.action=="create-analysis":
            result=store.create_diagnosis(instruction=args.instruction,
                      diagnosis_file=args.diagnosis,mechanical_file=args.mechanical,mode=args.mode)
        elif args.action=='create-urdf':
            result=store.create_imported_urdf(instruction=args.instruction,urdf_file=args.urdf,mode=args.mode)
        elif args.action=='create-result-analysis':
            result=store.create_result_comparison(result_store=args.result_store,
                reference_id=args.reference,candidate_id=args.candidate,
                instruction=args.instruction,mode=args.mode)
        elif args.action=="create-model":
            result=store.create_model(instruction=args.instruction,
                        model_project=args.project,expected_revision=args.revision,mode=args.mode)
        elif args.action=="status":
            result=store.status(args.id)
        elif args.action=="run-cli":
            result=store.run_codex_cli(args.id)
        else:
            if args.response.is_symlink() or not args.response.is_file() or args.response.stat().st_size>4*1024*1024:
                raise WebBridgeError("Bounded response JSON file required")
            result=store.submit(args.id,json.loads(args.response.read_bytes()))
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    except (WebBridgeError, ProviderError, ExplanationProviderError,
            OSError, KeyError, ValueError) as exc:
        print(json.dumps({"status":"error","error":{"type":type(exc).__name__,"message":str(exc)[:500]}}),
              file=sys.stderr)
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
