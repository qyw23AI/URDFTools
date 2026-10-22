#!/usr/bin/env python3
"""Compute mass properties from STEP B-rep solids with explicit material density."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from urdftools.cad.mass_properties import MassPropertiesError, compute_step_mass_properties


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="local .step/.stp CAD B-rep")
    parser.add_argument("--density", type=float, help="explicit uniform material density in kg/m^3")
    parser.add_argument("--densities-json", help="JSON object mapping exact adapter part names to density kg/m^3 or null")
    parser.add_argument("--output", help="write JSON report to this path instead of stdout")
    args = parser.parse_args()
    if args.density is not None and args.densities_json:
        parser.error("Use either --density or --densities-json, not both.")
    assignments = None
    try:
        if args.densities_json:
            loaded = json.loads(Path(args.densities_json).read_text(encoding="utf-8"))
            if not isinstance(loaded, dict) or any(not isinstance(key, str) for key in loaded):
                raise MassPropertiesError("--densities-json must contain a JSON object with part-name keys.")
            assignments = loaded
        report = compute_step_mass_properties(args.input, assignments, default_density_kg_m3=args.density)
    except (MassPropertiesError, OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
        print(json.dumps({"status": "written", "output": str(output), "mass_complete": report["assembly"]["mass_complete"],
                          "source_sha256": report["source"]["sha256"]}, ensure_ascii=False))
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
