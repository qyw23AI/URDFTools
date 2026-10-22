import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from accept_phase import run_stage


class AcceptanceTests(unittest.TestCase):
    def run_fixture(self, pattern):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "result.json"
            proc = subprocess.run([sys.executable, "scripts/run_test_suite.py", "--directory", "tests/fixtures/acceptance", "--pattern", pattern, "--report", str(report)], cwd=ROOT, capture_output=True, text=True)
            return proc.returncode, json.loads(report.read_text())

    def test_empty_rejected(self):
        code, report = self.run_fixture("absent_*.py")
        self.assertEqual(code, 1)
        self.assertEqual(report["discovered"], 0)

    def test_all_skip_rejected(self):
        code, report = self.run_fixture("all_skipped.py")
        self.assertEqual(code, 1)
        self.assertEqual(report["skipped"], 1)
        self.assertEqual(report["passed"], 0)

    def test_failure_rejected(self):
        code, report = self.run_fixture("failing.py")
        self.assertEqual(code, 1)
        self.assertEqual(report["failed"], 1)

    def test_fixture_failure_has_zero_passes(self):
        code, report = self.run_fixture("setup_error.py")
        self.assertEqual(code, 1)
        self.assertEqual(report["discovered"], 1)
        self.assertEqual(report["executed"], 0)
        self.assertEqual(report["passed"], 0)
        self.assertEqual(report["failed"], 1)

    def test_numeric_pass_counted(self):
        code, report = self.run_fixture("passing.py")
        self.assertEqual(code, 0)
        self.assertEqual(report["discovered"], 1)
        self.assertEqual(report["passed"], 1)

    def test_future_phase_not_implemented(self):
        p = subprocess.run([sys.executable, "scripts/accept_phase.py", "S04"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("No implemented acceptance", p.stderr)

    def test_timeout_kills_real_descendants_and_keeps_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "orphan-output"
            child = "import time,pathlib; time.sleep(1); pathlib.Path(" + repr(str(marker)) + ").write_text('orphan')"
            parent = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child) + "]); print('started',flush=True); time.sleep(30)"
            code, output = run_stage([sys.executable, "-c", parent], timeout=0.3)
            self.assertEqual(code, 2)
            self.assertIn("started", output)
            self.assertIn("process group terminated", output)
            time.sleep(1)
            self.assertFalse(marker.exists(), "timed-out stage left an active child")

    def test_real_command_failure_keeps_exit_and_output(self):
        code, output = run_stage([sys.executable, "-c", "print(7 * 9); raise SystemExit(4)"])
        self.assertEqual(code, 4)
        self.assertEqual(output.strip(), "63")
