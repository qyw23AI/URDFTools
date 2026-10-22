import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

from urdftools.api import create_app
from urdftools.core import runtime_status

ROOT = Path(__file__).resolve().parents[2]


class ToolchainTests(unittest.TestCase):
    def test_weak_session_credential_rejected(self):
        with self.assertRaises(ValueError):
            create_app("short")
        self.assertEqual([r.path for r in create_app("a" * 64).routes], ["/v1/health"])

    def test_core_reports_only_implemented_capabilities(self):
        self.assertEqual(runtime_status()["units"], "SI")
        self.assertEqual(runtime_status()["capabilities"], ["doctor", "health"])

    def test_manifest_covers_locked_dependencies_and_notice_hashes(self):
        ledger = json.loads((ROOT / "third_party/manifest.json").read_text())["entries"]
        indexed = {(e["ecosystem"], e["name"], e["version"]): e for e in ledger if e.get("usage") != "development-tool"}
        lock = json.loads((ROOT / "package-lock.json").read_text())
        for path, package in lock["packages"].items():
            if not path:
                continue
            e = indexed[("npm", path.removeprefix("node_modules/"), package["version"])]
            self.assertEqual(e["integrity"], package["integrity"])
            self.assertEqual(e["source"], package["resolved"])
        desktop = json.loads((ROOT / "apps/desktop/package-lock.json").read_text())
        for path, package in desktop["packages"].items():
            if not path:
                continue
            name = json.loads((ROOT / "apps/desktop" / path / "package.json").read_text())["name"]
            e = indexed[("npm", name, package["version"])]
            self.assertEqual(e["integrity"], package["integrity"])
            self.assertTrue(package["resolved"].startswith("https://registry.npmjs.org/"))
        pin = json.loads((ROOT / "apps/desktop/runtime-lock.json").read_text())
        runtime = indexed[("runtime", "electron", pin["version"])]
        self.assertEqual(runtime["artifact_sha256"], pin["sha256"])
        sums = ROOT / "third_party/electron-SHASUMS256.txt"
        self.assertEqual(hashlib.sha256(sums.read_bytes()).hexdigest(), pin["checksum_file_sha256"])
        self.assertIn(pin["sha256"] + " *" + pin["archive"], sums.read_text())
        for line in (ROOT / "requirements.lock").read_text().splitlines():
            if line.startswith("#") or not line:
                continue
            name, rest = line.split("==")
            version, digest = rest.split(" --hash=sha256:")
            self.assertEqual(indexed[("pypi", name, version)]["artifact_sha256"], digest)
        for entry in ledger:
            for notice in entry["notices"]:
                actual = hashlib.sha256((ROOT / notice["path"]).read_bytes()).hexdigest()
                self.assertEqual(actual, notice["sha256"])

    def test_cached_npm_lock_is_deterministic(self):
        old = (ROOT / "package-lock.json").read_bytes()
        proc = subprocess.run([str(ROOT / ".tools/node/bin/node"), "scripts/lock_cached_npm.cjs"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual((ROOT / "package-lock.json").read_bytes(), old)
