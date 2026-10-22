#!/usr/bin/env python3
"""Install locked npm packages and a reviewed Electron archive, without install hooks."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile

from bootstrap import ROOT, clean_environment


def install(cache, npm_cache, offline):
    pin = json.loads((ROOT / "apps/desktop/runtime-lock.json").read_text())
    archive = cache / pin["archive"]
    if not archive.is_file():
        raise ValueError(f"missing Electron {pin['version']} archive: {archive}; prepare --electron-cache using apps/desktop/runtime-lock.json; no implicit runtime download")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != pin["sha256"]:
        raise ValueError("Electron archive SHA256 differs from reviewed runtime-lock.json")
    env = clean_environment()
    env["PATH"] = str(ROOT / ".tools/node/bin") + ":/usr/bin:/bin"
    config = ROOT / ".tools/npm-config"
    config.mkdir(exist_ok=True)
    for name in ("user", "global"):
        (config / name).write_text("")
    command = [str(ROOT / ".tools/node/bin/node"), str(ROOT / ".tools/npm/bin/npm-cli.js"),
               "ci", "--ignore-scripts", "--no-audit", "--no-fund", "--registry=https://registry.npmjs.org",
               "--userconfig", str(config / "user"), "--globalconfig", str(config / "global"),
               "--cache", str(npm_cache)]
    if offline:
        command.append("--offline")
    subprocess.run(command, cwd=ROOT / "apps/desktop", env=env, check=True, timeout=240)
    package = ROOT / "apps/desktop/node_modules/electron"
    if json.loads((package / "package.json").read_text())["version"] != pin["version"]:
        raise ValueError("Electron npm package version differs from runtime lock")
    staging = package / "dist.staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    try:
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                target = staging / member.filename
                mode = member.external_attr >> 16
                if not target.resolve().is_relative_to(staging.resolve()) or stat.S_ISLNK(mode):
                    raise ValueError("unsafe Electron archive member: " + member.filename)
                bundle.extract(member, staging)
                if not member.is_dir():
                    # Preserve executable bits, never set setuid/setgid bits.
                    target.chmod(0o755 if mode & 0o111 else 0o644)
        if (staging / "version").read_text().strip() != pin["version"]:
            raise ValueError("Electron archive version differs from runtime lock")
        shutil.rmtree(package / "dist", ignore_errors=True)
        staging.rename(package / "dist")
        (package / "path.txt").write_text("electron")
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(json.dumps({"installed": "electron", "version": pin["version"], "archive_sha256": pin["sha256"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--electron-cache", type=Path, default=ROOT / ".tools/electron-cache")
    parser.add_argument("--npm-cache", type=Path, default=ROOT / ".tools/npm-cache")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        install(args.electron_cache.resolve(), args.npm_cache.resolve(), args.offline)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("DESKTOP_DEPENDENCY_FAILED: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
