#!/usr/bin/env python3
"""Build and actually exercise a relocatable Ubuntu x86_64 portable release.

The archive is self-contained for the shipped Python/Electron workers, but
external FreeCAD/SolidWorks integrations and redistribution clearance are
separate acceptance requirements. Never copy Codex caches or API credentials.
"""
import argparse
from datetime import datetime, timezone
from email.parser import Parser
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/Q01"
BASENAME = "URDFTools-0.1.0-linux-x86_64"
ENVS = (".venv", ".tools/cad-venv", ".tools/model-venv", ".tools/results-venv", ".tools/sim-venv")
DIRECTORIES = (".tools/python", *ENVS, "python", "scripts", "examples", "third_party", "dist/web",
               "apps/desktop/node_modules/electron/dist")
FILES = ("apps/desktop/main.cjs", "apps/desktop/preload.cjs", "apps/desktop/package.json", "docs/PORTABLE_RELEASE.md")


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def copy_directory(src, dest):
    def ignore(directory, names):
        return {name for name in names if name in {"__pycache__", ".pytest_cache", ".mypy_cache"} or name.endswith(".pyc")}
    shutil.copytree(src, dest, symlinks=True, ignore=ignore)


def audit(destination):
    """Fail closed on missing bundled license texts; metadata alone is not NOTICE."""
    entries = []
    gaps = []
    for env in ENVS:
        site = destination / env / "lib/python3.12/site-packages"
        if not site.is_dir():
            gaps.append({"environment": env, "error": "site-packages missing"})
            continue
        for info in sorted(site.glob("*.dist-info")):
            metadata_path = info / "METADATA"
            meta = Parser().parsestr(metadata_path.read_text(errors="replace") if metadata_path.exists() else "")
            name = meta.get("Name") or info.name
            version = meta.get("Version") or "unknown"
            license_name = meta.get("License-Expression") or meta.get("License")
            # Classifier names are hints only, not proof of a redistribution license.
            license_files = [str(path.relative_to(destination)) for path in info.rglob("*")
                             if path.is_file() and any(token in path.name.lower() for token in
                                                       ("license", "copying", "notice"))]
            entry = {"environment": env, "name": name, "version": version,
                     "license_metadata": (license_name or "")[:250],
                     "license_files": license_files}
            entries.append(entry)
            if not license_files and not (env == '.venv' and name == 'urdftools'):
                gaps.append({"environment": env, "name": name, "version": version,
                             "reason": "bundled dist-info has no license/notice text"})
    original = json.loads((destination / "third_party/manifest.json").read_text())
    # The old S01 manifest covers the development toolchain, not every optional worker.
    report = {"status": "passed" if not gaps else "incomplete",
              "installed_distribution_count": len(entries), "gaps": gaps,
              "s01_manifest_entries": len(original["entries"]),
              "scope": "Bundled runtime wheel notices; additional transitive/native and upstream clearance pending",
              "distributions": entries}
    (destination / "LICENSE-AUDIT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def build():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    staging = OUT / "builds" / stamp / BASENAME
    if staging.exists():
        raise ValueError("release directory already exists; refusing overwrite")
    for rel in (*DIRECTORIES, *FILES, "scripts/q01_portable_launch.sh"):
        if not (ROOT / rel).exists():
            raise ValueError("required bundled component missing: " + rel)
    for rel in DIRECTORIES:
        copy_directory(ROOT / rel, staging / rel)
    for rel in FILES:
        target = staging / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    shutil.copy2(ROOT / "scripts/q01_portable_launch.sh", staging / "launch.sh")
    (staging / "launch.sh").chmod(0o755)
    # Do not accidentally ship symlinks to Codex caches, system paths, or source checkout.
    interpreter_links = {staging / env / 'bin' / name for env in ENVS
                         for name in ('python', 'python3', 'python3.12')}
    for item in staging.rglob('*'):
        if item.is_symlink() and os.path.isabs(os.readlink(item)) and item not in interpreter_links:
            raise ValueError('external absolute symlink in portable bundle: ' + str(item.relative_to(staging)))
    runtime_hashes = json.loads((ROOT / "third_party/electron-runtime-files.json").read_text())
    for rel, digest in runtime_hashes.items():
        if sha256(staging / "apps/desktop/node_modules/electron/dist" / rel) != digest:
            raise ValueError("Electron runtime file mismatch: " + rel)
    license_report = audit(staging)
    (staging / 'RELEASE_STATUS.md').write_text(
        '# URDFTools 离线便携包（技术候选）\n\n'
        + '**第三方许可审查尚未完成，暂不公开再分发。**\n\n'
        + '使用方法见 docs/PORTABLE_RELEASE.md。\n'
        + f'当前检测到 {len(license_report["gaps"])} 项运行环境许可文本缺口；详见 LICENSE-AUDIT.json。\n')
    manifest = {"release": BASENAME, "built_at": stamp, "electron_files_verified": len(runtime_hashes),
                "python_binary_sha256": sha256(staging / ".tools/python/bin/python3.12"),
                "example_urdf_sha256": sha256(staging / "examples/robot_demo/robot.urdf"),
                "license_gap_count": len(license_report["gaps"]),
                "external_freecad_bundled": False,
                "runtime_source": "project-local pinned CPython/Electron/worker environments"}
    (staging / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    archive = staging.parent / (BASENAME + ".tar.zst")
    subprocess.run(["tar", "--zstd", "-cf", str(archive), "-C", str(staging.parent), BASENAME],
                   check=True, timeout=1200)
    pointer = {"release_dir": str(staging.relative_to(ROOT)), "archive": str(archive.relative_to(ROOT)),
               "archive_sha256": sha256(archive), **manifest}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(pointer, indent=2) + "\n")
    print(json.dumps({"status": "built", "archive_bytes": archive.stat().st_size, **pointer}))
    return 0


def smoke():
    pointer = json.loads((OUT / "latest.json").read_text())
    archive = ROOT / pointer["archive"]
    if sha256(archive) != pointer["archive_sha256"]:
        raise ValueError("release archive SHA256 mismatch")
    with tempfile.TemporaryDirectory(prefix="q01-extract-", dir=OUT) as temporary:
        temp = Path(temporary)
        # This archive is created by our own build() and SHA-fenced above.
        subprocess.run(["tar", "--zstd", "--no-same-owner", "-xf", str(archive), "-C", str(temp)],
                       check=True, timeout=600)
        release = temp / BASENAME
        home = temp / "fresh HOME"
        home.mkdir()
        env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "LANG": "C.UTF-8",
               "XDG_CONFIG_HOME": str(home / ".config"), "XDG_CACHE_HOME": str(home / ".cache"),
               "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
               "ALL_PROXY": "socks5://127.0.0.1:9", "NO_PROXY": "127.0.0.1,localhost",
               "URDFTOOLS_Q01_SMOKE": "1", "URDFTOOLS_SMOKE_ARTIFACT_DIR": str(OUT)}
        check = subprocess.run(["bash", str(release / "launch.sh"), "--check"],
                               env=env, text=True, capture_output=True, timeout=30)
        if check.returncode:
            raise ValueError("bundled Python check failed: " + check.stderr[-1500:])
        identity = json.loads(check.stdout.strip().splitlines()[-1])
        if identity["base_prefix"] != str(release / ".tools/python") or identity["python"] != "3.12.14":
            raise ValueError("bundled Python used external runtime: " + str(identity))
        # Run the actual packaged Electron binary and its actual importer, not a mocked UI.
        cmd = ["bash", str(release / "launch.sh"), "--smoke", "--ozone-platform=headless", "--disable-gpu"]
        result = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=100)
        logs = result.stdout + "\n" + result.stderr
        (OUT / "portable-smoke.log").write_text(logs)
        events = []
        for line in result.stdout.splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        event = next((item for item in events if item.get("event") == "q01_portable_example"), {})
        screenshot = OUT / "portable-example.png"
        passed = (result.returncode == 0 and event.get("status") == "ready" and
                  event.get("links") == 2 and event.get("joints") == 1 and
                  event.get("meshes", 0) >= 1 and event.get("isolated") is True and
                  event.get("sandbox") is True and screenshot.is_file() and screenshot.stat().st_size > 1000)
        report = {"status": "passed" if passed else "failed", "exit_code": result.returncode,
                  "python": identity, "gui": event,
                  "screenshot_sha256": sha256(screenshot) if screenshot.exists() else None,
                  "isolation": "fresh HOME + invalid external proxy; not network namespace isolation",
                  "release_sha256": pointer["archive_sha256"],
                  "log_tail": logs[-2200:]}
        (OUT / "portable-smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False))
        return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "smoke", "audit"))
    args = parser.parse_args()
    if args.action == "build":
        return build()
    if args.action == "smoke":
        return smoke()
    release = ROOT / json.loads((OUT / "latest.json").read_text())["release_dir"]
    report = audit(release)
    print(json.dumps({"status": report["status"], "packages": report["installed_distribution_count"],
                      "missing_notice_count": len(report["gaps"]), "examples": report["gaps"][:12]}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError, subprocess.TimeoutExpired) as exc:
        print("Q01_PORTABLE_FAILED: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
