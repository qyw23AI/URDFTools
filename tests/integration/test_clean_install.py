"""Install in a directory with no venv/node_modules, then run real processes.

Inputs are explicit local copies of public runtime seeds and hash-locked caches.
No source paths from another user project are used by the tests.
"""
import json
import os
from pathlib import Path
import selectors
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "artifacts/S01"


class CleanInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="urdftools-s01-", dir=EVIDENCE)
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.work = Path(cls.tmp.name) / "clean checkout"
        shutil.copytree(ROOT, cls.work, ignore=shutil.ignore_patterns(
            ".git", ".scheduler", ".tools", ".venv", "node_modules", "artifacts", "__pycache__", "dist", "*.egg-info", "build", ".agents", ".aws", ".codex"))
        cls.logs = []
        cls.env = {"PATH": "/usr/bin:/bin", "HOME": str(Path(cls.tmp.name)), "LANG": "C.UTF-8"}
        command = ["python3", "-E", "scripts/bootstrap.py", "--offline",
                   "--python-runtime", str(ROOT / ".tools/python"),
                   "--node-runtime", str(ROOT / ".tools/node"),
                   "--npm-source", str(ROOT / ".tools/npm"),
                   "--wheelhouse", str(ROOT / ".tools/wheelhouse"),
                   "--npm-cache", str(ROOT / ".tools/npm-cache"),
                   "--electron-cache", str(ROOT / ".tools/electron-cache")]
        # Real installation must survive poisoned ambient interpreter/package settings.
        cls.execute(command, env=cls.env | {
            "PYTHONHOME": "/nonexistent-s01-python", "PYTHONPATH": "/nonexistent-s01-hook",
            "NODE_OPTIONS": "--require=/nonexistent-s01-hook.cjs",
            "PIP_TARGET": "/nonexistent-s01-target", "npm_config_registry": "https://invalid.example",
            "NPM_CONFIG_USERCONFIG": "/nonexistent-s01-npmrc"})
        cls.python = cls.work / ".venv/bin/python"
        cls.node = cls.work / ".tools/node/bin/node"
        cls.env["PATH"] = str(cls.node.parent) + ":/usr/bin:/bin"
        cls.execute([str(cls.node), ".tools/npm/bin/npm-cli.js", "run", "build"])

    @classmethod
    def execute(cls, command, expected=0, env=None):
        p = subprocess.run(command, cwd=cls.work, env=cls.env if env is None else env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        cls.logs.append({"command": list(map(str, command)), "returncode": p.returncode, "output": p.stdout})
        (EVIDENCE / "clean-install-commands.json").write_text(json.dumps(cls.logs, indent=2))
        if p.returncode != expected:
            raise AssertionError(f"{command} exited {p.returncode}: {p.stdout}")
        return p.stdout

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_installed_cli_and_isolation(self):
        data = json.loads(self.execute([str(self.work / ".venv/bin/urdftools"), "doctor", "--json"]))
        self.assertEqual(data["python"], "3.12.14")
        self.assertTrue(data["isolated"])
        self.assertEqual(data["capabilities"], ["doctor", "health"])
        prefixes = json.loads(self.execute([str(self.python), "-c", "import sys,json;print(json.dumps([sys.prefix,sys.base_prefix,sys.path]))"]))
        self.assertTrue(prefixes[0].startswith(str(self.work)))
        self.assertTrue(prefixes[1].startswith(str(self.work / ".tools/python")))
        self.assertFalse(any("codex-runtimes" in p for p in prefixes[2]))
        self.execute([str(self.python), "-m", "pip", "check"])

    def test_real_http_auth_and_origin(self):
        token = "s01-test-session-" + "a" * 40
        with subprocess.Popen([str(self.python), "-m", "urdftools", "serve"], cwd=self.work, env=self.env | {"URDFTOOLS_SESSION_TOKEN": token}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as p:
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(p.stdout, selectors.EVENT_READ)
                    self.assertTrue(selector.select(15), "service did not announce listening")
                    line = p.stdout.readline()
                    if not line:
                        self.fail("Service could not start: " + p.stderr.read())
                    event = json.loads(line)
                self.assertEqual(event["host"], "127.0.0.1")
                url = f"http://127.0.0.1:{event['port']}/v1/health"
                headers = {"Authorization": "Bearer " + token}
                for _ in range(100):
                    try:
                        with urlopen(Request(url, headers=headers), timeout=2) as response:
                            data = json.load(response)
                        break
                    except ConnectionError:
                        time.sleep(0.02)
                else:
                    self.fail("service never became ready")
                self.assertEqual(data["application"], "URDFTools")
                for rejected, code in [({}, 401), ({"Authorization": "Bearer wrong"}, 401), (headers | {"Origin": "https://example.org"}, 403)]:
                    with self.assertRaises(HTTPError) as raised:
                        urlopen(Request(url, headers=rejected), timeout=3)
                    self.assertEqual(raised.exception.code, code)
                (EVIDENCE / "http-smoke.json").write_text(json.dumps({"listening": event, "health": data, "rejected_statuses": [401, 401, 403]}, indent=2))
            finally:
                p.terminate()
                p.wait(timeout=10)
                stderr = p.stderr.read()
                self.logs.append({"command": [str(self.python), "-m", "urdftools", "serve"], "stderr": stderr})

    def test_web_build_and_render(self):
        # Real React SSR checks DOM content; a browser mount remains the Electron gate.
        output = self.execute([str(self.node), "tests/web/shell.test.mjs"])
        # Vite SSR builds under node --test's child isolation can terminate the
        # file before cases register. Require actual per-case counts here.
        self.assertIn("ℹ tests 2", output)
        self.assertIn("ℹ pass 2", output)

    def test_web_preview(self):
        port = int(os.environ.get("S01_WEB_PORT", "4173"))
        command = [str(self.node), "node_modules/vite/bin/vite.js", "preview", "apps/web", "--outDir", "../../dist/web", "--host", "127.0.0.1", "--port", str(port), "--strictPort"]
        with subprocess.Popen(command, cwd=self.work, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as p:
            try:
                for _ in range(100):
                    try:
                        with urlopen(f"http://127.0.0.1:{port}", timeout=2) as r:
                            html = r.read().decode()
                        break
                    except OSError:
                        if p.poll() is not None:
                            self.fail(p.stdout.read())
                        time.sleep(0.05)
                else:
                    self.fail("preview failed to start")
                self.assertIn('id="root"', html)
                import re
                script = re.search(r'src="(\./assets/[^\"]+\.js)"', html).group(1)
                with urlopen(f"http://127.0.0.1:{port}/" + script[2:], timeout=3) as r:
                    bundle = r.read().decode()
                self.assertIn("尚未打开工程", bundle)
                self.assertGreater(len(bundle), 10000)
                (EVIDENCE / "web-smoke.json").write_text(json.dumps({"html": html, "javascript_bytes": len(bundle.encode()), "ssr": "passed", "browser_mount": "not_verified"}, indent=2, ensure_ascii=False))
            finally:
                p.terminate()
                p.wait(timeout=10)

    def test_desktop_real_render_and_interaction(self):
        self.execute([str(self.python), "scripts/desktop_smoke.py", "--artifacts-dir",
                      str(EVIDENCE / "clean-desktop")])
        report = json.loads((EVIDENCE / "clean-desktop/report.json").read_text())
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["render"]["selected"], "评估")
        self.assertTrue(report["render"]["sandbox"])

    def test_offline_failure_explains_dependency(self):
        with tempfile.TemporaryDirectory(dir=self.tmp.name) as tmp:
            fresh = Path(tmp)
            (fresh / "scripts").mkdir()
            shutil.copy(ROOT / "scripts/bootstrap.py", fresh / "scripts/bootstrap.py")
            shutil.copy(ROOT / "toolchain.json", fresh / "toolchain.json")
            p = subprocess.run(["python3", "scripts/bootstrap.py", "--offline"], cwd=fresh, env=self.env, capture_output=True, text=True)
            self.assertEqual(p.returncode, 2)
            self.assertIn("missing python 3.12.14 runtime", p.stderr)
            self.assertIn("--python-runtime", p.stderr)
            (EVIDENCE / "offline-negative.log").write_text(p.stderr)

    def test_desktop_missing_and_corrupt_cache_fail_before_install(self):
        with tempfile.TemporaryDirectory(dir=self.tmp.name) as tmp:
            command = [str(self.python), "scripts/setup_desktop.py", "--offline", "--electron-cache", tmp]
            missing = self.execute(command, expected=2)
            self.assertIn("missing Electron 39.2.7 archive", missing)
            pin = json.loads((self.work / "apps/desktop/runtime-lock.json").read_text())
            (Path(tmp) / pin["archive"]).write_bytes(b"corrupt runtime fixture")
            corrupt = self.execute(command, expected=2)
            self.assertIn("SHA256 differs", corrupt)

    def test_service_missing_credential_fails(self):
        p = subprocess.run([str(self.python), "-m", "urdftools", "serve"], cwd=self.work, env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 2)
        self.assertEqual(json.loads(p.stderr)["code"], "missing_session_token")
