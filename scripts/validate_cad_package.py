#!/usr/bin/env python3
"""Independent package parser + MuJoCo compiler; run with project sim venv."""
import json
from pathlib import Path
import sys
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'python'))
from urdftools.cad.package_validation import validate_package_zip

try:
    result = validate_package_zip(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False))
except (OSError, ValueError, KeyError, ImportError, zipfile.BadZipFile, ET.ParseError) as exc:
    print(json.dumps({'status':'failed','message':str(exc)}, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(2)
