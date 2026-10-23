#!/usr/bin/env python3
"""Read-only JSON static URDF diagnostics; use --context only for trusted SI design data."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from urdftools.evaluation.static import scan_urdf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("urdf", type=Path)
    parser.add_argument("--context", type=Path,
                        help="JSON design context: joint_axes and link_visual_box_sizes_m")
    args = parser.parse_args()
    context = json.loads(args.context.read_text()) if args.context else None
    report = scan_urdf(args.urdf, context)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
