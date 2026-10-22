#!/usr/bin/env python3
"""C02 command-line preview: inspect STEP, save editable config, render visual-only URDF."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from urdftools.cad.wizard import (WizardError, default_configuration,
    inspect_conversion_draft, preview_urdf, validate_configuration)


def main() -> int:
    parser = argparse.ArgumentParser(description='STEP joint grouping and visual-only preview')
    parser.add_argument('step', type=Path)
    parser.add_argument('--config', type=Path, help='Reuse an edited config JSON')
    parser.add_argument('--preview', type=Path, help='Write visual-only preview URDF; all joints must be confirmed')
    args = parser.parse_args()
    try:
        draft = inspect_conversion_draft(args.step)
        config = json.loads(args.config.read_text()) if args.config else default_configuration(draft)
        summary = validate_configuration(draft, config)
        if args.preview:
            output = preview_urdf(draft, config)
            args.preview.parent.mkdir(parents=True, exist_ok=True)
            args.preview.write_text(output)
        print(json.dumps({'draft': draft, 'configuration': config, 'validation': summary,
                          'preview_path': str(args.preview) if args.preview else None}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'status': 'failed', 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
