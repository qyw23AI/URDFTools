#!/usr/bin/env python3
"""Pin the original H1 source assets from a local staging directory against a Git tree.

Run after obtaining the vendor files from the fixed upstream commit. This script
does not fetch network resources, rewrite existing fixtures, or claim hardware validity.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "5994d4faef0a9cadd3287f8de0199a67eeb2a259"
UPSTREAM = "https://github.com/unitreerobotics/unitree_ros"
STAGING = ROOT / ".tools/r02-staging"
SOURCE_REPO = ROOT / ".tools/reference-clones/unitree_ros"
DEST = ROOT / "tests/fixtures/R02"


def pin_assets(staging: Path = STAGING, repo: Path = SOURCE_REPO,
               dest: Path = DEST) -> dict:
    assert subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                   text=True).strip() == COMMIT
    urdf = staging / "h1.urdf"
    raw = urdf.read_bytes()
    assert len(raw) < 4 * 1024 * 1024 and b"<!DOCTYPE" not in raw.upper()
    root = ET.fromstring(raw)
    assert root.get("name") == "h1_description"
    refs = sorted({mesh.get("filename") for mesh in root.findall(".//mesh")})
    prefix = "package://h1_description/"
    assert len(refs) == 21 and all(ref.startswith(prefix) for ref in refs)
    files = ["urdf/h1.urdf", "package.xml"] + [ref[len(prefix):] for ref in refs]
    assert len(files) == len(set(files))
    records = []
    for rel in files:
        rel_path = Path(rel)
        assert not rel_path.is_absolute() and ".." not in rel_path.parts
        source = urdf if rel == "urdf/h1.urdf" else staging / rel_path
        data = source.read_bytes()
        assert 0 < len(data) < 64 * 1024 * 1024
        upstream_path = "robots/h1_description/" + rel
        env = {**os.environ, "GIT_NO_LAZY_FETCH": "1"}
        blob = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD:" + upstream_path],
            env=env, text=True).strip()
        actual_blob = hashlib.sha1(b"blob " + str(len(data)).encode() + bytes([0]) + data).hexdigest()
        assert blob == actual_blob, (rel, blob, actual_blob)
        target = dest / "h1_description" / rel_path
        if target.exists():
            assert target.read_bytes() == data, f"Refusing to overwrite {target}"
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        records.append({"path": rel, "upstream_path": upstream_path, "size": len(data),
                        "git_blob_sha1": blob, "sha256": hashlib.sha256(data).hexdigest()})
    license_data = (ROOT / "tests/fixtures/S06/UNITREE_LICENSE").read_bytes()
    license_dest = dest / "UNITREE_LICENSE"
    if license_dest.exists():
        assert license_dest.read_bytes() == license_data
    else:
        license_dest.write_bytes(license_data)
    manifest = {
        "schema_version": 1, "source_repository": UPSTREAM,
        "source_commit": COMMIT, "license": "BSD-3-Clause",
        "license_sha256": hashlib.sha256(license_data).hexdigest(),
        "source_category": "public_import",
        "fixture_purpose": "Real vendor geometry for viewer/compile; no hardware calibration or training reference.",
        "model": "unitree_h1_without_hands", "files": records,
    }
    manifest_path = dest / "h1_source_manifest.json"
    encoded = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if manifest_path.exists():
        assert manifest_path.read_text() == encoded, "Manifest mismatch; refusing to overwrite"
    else:
        manifest_path.write_text(encoded)
    return manifest


if __name__ == "__main__":
    manifest = pin_assets()
    print(json.dumps({"status": "passed", "file_count": len(manifest["files"]),
                      "total_bytes": sum(item["size"] for item in manifest["files"])}))
