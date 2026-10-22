#!/usr/bin/env python3
"""Inspect a STEP/STP file with the isolated CAD worker and emit a JSON report."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from urdftools.cad.step_reader import StepImportError, inspect_step


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect STEP units, assembly hierarchy, colors, transforms and provenance.")
    parser.add_argument("input", help="local .step/.stp file")
    parser.add_argument("--output", help="write JSON report to this path instead of stdout")
    args = parser.parse_args()
    try:
        report = inspect_step(args.input)
    except (StepImportError, OSError, RuntimeError) as exc:
        error = {"status": "failed", "error_type": type(exc).__name__, "error": str(exc)}
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return 2
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
        print(json.dumps({"status": "written", "output": str(output), "source_sha256": report["source"]["sha256"]}, ensure_ascii=False))
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
