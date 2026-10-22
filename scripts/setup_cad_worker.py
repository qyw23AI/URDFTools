#!/usr/bin/env python3
"""Create/update the isolated OCP worker from the hash-pinned CAD lock."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SEED_PYTHON = ROOT / ".tools/python/bin/python"
ENV_DIR = ROOT / ".tools/cad-venv"
ENV_PYTHON = ENV_DIR / "bin/python"
WHEELHOUSE = ROOT / ".tools/cad-wheelhouse"
LOCK = ROOT / "cad-requirements.lock"


def run(command: list[str], env: dict[str, str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="install only from the local .tools/cad-wheelhouse")
    args = parser.parse_args()
    if not LOCK.is_file():
        parser.error(f"missing CAD lock: {LOCK}")
    if not ENV_PYTHON.exists():
        if not SEED_PYTHON.is_file():
            print("Missing pinned .tools/python runtime; run scripts/bootstrap.py first.", file=sys.stderr)
            return 2
        base_env = {
            "PATH": str(ROOT / ".tools/python/bin") + ":/usr/bin:/bin",
            "HOME": str(ROOT / ".tools/cad-home"),
            "LANG": "C.UTF-8",
            "PYTHONNOUSERSITE": "1",
        }
        Path(base_env["HOME"]).mkdir(parents=True, exist_ok=True)
        run([str(SEED_PYTHON), "-m", "venv", str(ENV_DIR)], base_env)

    WHEELHOUSE.mkdir(parents=True, exist_ok=True)
    home = ROOT / ".tools/cad-home"
    home.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": str(ENV_DIR / "bin") + ":/usr/bin:/bin",
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_INDEX_URL": "https://pypi.org/simple",
        "PIP_NO_INPUT": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    }
    pip = [str(ENV_PYTHON), "-m", "pip"]
    if not args.offline:
        run(pip + ["download", "--require-hashes", "--only-binary=:all:", "--dest", str(WHEELHOUSE), "-r", str(LOCK)], env)
    elif not list(WHEELHOUSE.glob("*.whl")):
        print(f"Offline CAD wheelhouse is empty: {WHEELHOUSE}", file=sys.stderr)
        return 2
    run(pip + ["install", "--require-hashes", "--only-binary=:all:", "--no-index", "--find-links", str(WHEELHOUSE), "-r", str(LOCK)], env)
    run(pip + ["check"], env)
    verify = (
        "import importlib.metadata as m, json, platform; import OCP; "
        "from OCP.STEPCAFControl import STEPCAFControl_Reader; "
        "print(json.dumps({'python':platform.python_version(),'cadquery-ocp-novtk':m.version('cadquery-ocp-novtk'),"
        "'cadquery-ocp-proxy':m.version('cadquery-ocp-proxy'),'numpy':m.version('numpy'),"
        "'PyYAML':m.version('PyYAML'),'ocp_import':'ok'}))"
    )
    result = subprocess.run([str(ENV_PYTHON), "-c", verify], cwd=ROOT, env=env, text=True, capture_output=True)
    print(result.stdout, end="")
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        return result.returncode
    report = json.loads(result.stdout.strip().splitlines()[-1])
    expected = {
        "python": "3.12.14",
        "cadquery-ocp-novtk": "8.0.1.1.0",
        "cadquery-ocp-proxy": "8.0.1.1.0",
        "numpy": "2.3.4",
        "PyYAML": "6.0.3",
    }
    if any(report.get(key) != value for key, value in expected.items()) or report.get("ocp_import") != "ok":
        print(f"CAD worker version mismatch: {report}", file=sys.stderr)
        return 1
    print("CAD worker ready; application .venv was not modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
