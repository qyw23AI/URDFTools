#!/usr/bin/env python3
"""Export a human-confirmed STEP assembly as a self-contained URDF/ROS ZIP."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from urdftools.cad.exporter import write_package_zip, write_package_directory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('step', type=Path)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--densities', type=Path, required=True, help='JSON mapping exact CAD part name to kg/m^3')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--format', choices=['zip','directory'], default='zip')
    args = parser.parse_args()
    try:
        writer = write_package_zip if args.format == 'zip' else write_package_directory
        result = writer(args.step, json.loads(args.config.read_text()),
                        json.loads(args.densities.read_text()), args.output)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'status': 'failed', 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
