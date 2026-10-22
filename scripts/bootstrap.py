#!/usr/bin/env python3
"""Prepare a project-local, pinned toolchain. Run with system Python >=3.10.

Offline inputs are explicit; never search user projects or inherit API credentials.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def clean_environment():
    """Do not let ambient Python/npm hooks, credentials or indexes affect setup."""
    return {key: value for key, value in os.environ.items()
            if key in {"PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TERM"}}


def run(command, env=None):
    print("+ " + " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ROOT, env=env, check=True, timeout=240)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--python-runtime", type=Path, help="CPython install root (bin/python3)")
    p.add_argument("--node-runtime", type=Path, help="Node install root (bin/node)")
    p.add_argument("--npm-source", type=Path, help="npm package root with bin/npm-cli.js")
    p.add_argument("--wheelhouse", type=Path)
    p.add_argument("--npm-cache", type=Path)
    p.add_argument("--electron-cache", type=Path)
    p.add_argument("--offline", action="store_true")
    args = p.parse_args()
    env = clean_environment()
    pins = json.loads((ROOT / "toolchain.json").read_text())
    tools = ROOT / ".tools"
    tools.mkdir(exist_ok=True)
    provenance = {}
    for name, source, probe in [("python", args.python_runtime, ["bin/python3", "--version"]),
                                 ("node", args.node_runtime, ["bin/node", "--version"])]:
        target = tools / name
        if not target.exists():
            if not source or not (source / probe[0]).is_file():
                raise ValueError(f"missing {name} {pins[name]} runtime: supply --{name}-runtime; offline mode cannot download it")
            version = subprocess.check_output([str(source / probe[0]), probe[1]], text=True, env=env).strip()
            if version.lstrip("Python ").lstrip("v") != pins[name]:
                raise ValueError(f"{name} version mismatch: expected {pins[name]}, got {version}")
            if hashlib.sha256((source / probe[0]).read_bytes()).hexdigest() != pins["binary_sha256"][name]:
                raise ValueError(f"{name} runtime binary differs from the reviewed seed; do not update pins implicitly")
            staging = tools / (name + ".staging")
            if staging.exists():
                shutil.rmtree(staging)
            shutil.copytree(source, staging, ignore=shutil.ignore_patterns("site-packages", "__pycache__", "node_modules"), symlinks=True)
            for link in staging.rglob("*"):
                if link.is_symlink() and (os.path.isabs(os.readlink(link)) or not link.exists()):
                    link.unlink()
            staging.rename(target)
            provenance[name] = {"seed": str(source.resolve()), "version": version,
                                "binary_sha256": hashlib.sha256((target / probe[0]).read_bytes()).hexdigest()}
        version = subprocess.check_output([str(target / probe[0]), probe[1]], text=True, env=env).strip()
        if version.lstrip("Python ").lstrip("v") != pins[name]:
            raise ValueError(f"installed {name} version mismatch: {version}")
        if hashlib.sha256((target / probe[0]).read_bytes()).hexdigest() != pins["binary_sha256"][name]:
            raise ValueError(f"installed {name} runtime binary hash mismatch")
    npm = tools / "npm"
    if not npm.exists():
        if not args.npm_source:
            raise ValueError("missing npm 10.9.9: supply --npm-source (public npm package)")
        if json.loads((args.npm_source / "package.json").read_text())["version"] != pins["npm"]:
            raise ValueError("npm seed version mismatch")
        shutil.copytree(args.npm_source, npm)
    if json.loads((npm / "package.json").read_text())["version"] != pins["npm"]:
        raise ValueError("installed npm version mismatch")
    previous = tools / "provenance.json"
    old = json.loads(previous.read_text()) if previous.exists() else {}
    previous.write_text(json.dumps(old | provenance, indent=2) + "\n")
    venv = ROOT / ".venv"
    python = venv / "bin/python"
    if not python.exists():
        run([tools / "python/bin/python3", "-m", "venv", "--without-pip", venv], env)
    # Bootstrap pip from a hash-verified locked wheel, without writing to the seed.
    wheelhouse = args.wheelhouse.resolve() if args.wheelhouse else tools / "wheelhouse"
    pip_line = next(l for l in (ROOT / "requirements.lock").read_text().splitlines() if l.startswith("pip=="))
    pip_version = pip_line.split("==")[1].split()[0]
    pip_wheel = wheelhouse / f"pip-{pip_version}-py3-none-any.whl"
    if not pip_wheel.is_file():
        raise ValueError(f"missing locked pip wheel: {pip_wheel}; populate wheelhouse using requirements.lock on a networked machine")
    if hashlib.sha256(pip_wheel.read_bytes()).hexdigest() != pip_line.split("sha256:")[1]:
        raise ValueError("pip wheel hash mismatch")
    env.update(PYTHONPATH=str(pip_wheel), PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK="1")
    pip_args = [python, "-m", "pip", "install", "--require-hashes", "-r", "requirements.lock"]
    if args.offline:
        pip_args += ["--no-index", "--find-links", wheelhouse]
    run(pip_args, env)
    env.pop("PYTHONPATH")
    run([python, "-m", "pip", "install", "--no-deps", "--no-build-isolation", "."], env)
    node = tools / "node/bin/node"
    env["PATH"] = str(node.parent) + os.pathsep + env.get("PATH", "/usr/bin:/bin")
    cache = args.npm_cache.resolve() if args.npm_cache else tools / "npm-cache"
    # npm rejects loading the same path twice as user and global configuration.
    config = tools / "npm-config"
    config.mkdir(exist_ok=True)
    for name in ("user", "global"):
        (config / name).write_text("")
    npm_args = [node, npm / "bin/npm-cli.js", "ci", "--ignore-scripts", "--no-audit", "--no-fund",
                "--userconfig", config / "user", "--globalconfig", config / "global", "--cache", cache]
    if args.offline:
        npm_args.append("--offline")
    run(npm_args, env)
    desktop_args = [python, ROOT / "scripts/setup_desktop.py", "--npm-cache", cache,
                    "--electron-cache", args.electron_cache.resolve() if args.electron_cache else tools / "electron-cache"]
    if args.offline:
        desktop_args.append("--offline")
    run(desktop_args, env)
    print("Toolchain ready. Build with .tools/node/bin/node .tools/npm/bin/npm-cli.js run build")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"DEPENDENCY_SETUP_FAILED: {exc}\nOffline inputs: Python/Node/npm seeds, hash-locked wheels, npm tarball cache. See docs/TOOLCHAIN.md.", file=sys.stderr)
        raise SystemExit(2)
