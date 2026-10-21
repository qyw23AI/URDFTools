import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1]


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copy2(SOURCE / "scheduler.py", self.root / "scheduler.py")
        (self.root / "prompt.md").write_text("Create feature.txt with hello.\n")
        self.fake = self.root / "codex-fake"
        self.fake.write_text("""#!/usr/bin/env python3
import json, pathlib, sys
root = pathlib.Path(__file__).resolve().parent
if sys.argv[1:3] == ['login', 'status']:
    print('Logged in using ChatGPT')
    sys.exit(0)
(root / 'invocation.json').write_text(json.dumps(sys.argv[1:]))
(root / 'feature.txt').write_text('hello\\n')
print('\\n')
""")
        self.fake.chmod(0o755)
        self.config = {"codex_bin": str(self.fake), "phases": [{
            "id": "one", "level": "ordinary", "prompt_file": "prompt.md",
            "tests": [[sys.executable, "-c", "assert open('feature.txt').read() == 'hello\\n'"]]
        }]}
        self.save_config()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.root, check=True)

    def save_config(self):
        (self.root / "scheduler.json").write_text(json.dumps(self.config))

    def invoke(self, *args):
        return subprocess.run([sys.executable, "scheduler.py", *args], cwd=self.root,
                              text=True, capture_output=True)

    def test_model_routing_and_checkpoint(self):
        for level, model, effort in [
            ("ordinary", "gpt-6.1-sol", "medium"),
            ("complex", "gpt-6.1-sol", "high"),
            ("critical", "gpt-6-astra", "high"),
            ("critical_xhigh", "gpt-6-astra", "xhigh"),
        ]:
            with self.subTest(level=level):
                self.config["phases"][0]["level"] = level
                self.save_config()
                result = self.invoke("run", "--dry-run")
                self.assertEqual(result.returncode, 0, result.stderr)
                command = json.loads(result.stdout)["command"]
                self.assertIn(model, command)
                self.assertIn("model_reasoning_effort=" + effort, command)
        self.config["phases"][0]["level"] = "ordinary"
        self.save_config()
        result = self.invoke("run")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        state = json.loads((self.root / ".scheduler/state.json").read_text())
        self.assertEqual(state["completed"], ["one"])
        self.assertEqual(state["attempts"][0]["result"], "completed")
        self.assertEqual(self.invoke("status").returncode, 0)
        self.assertEqual(self.invoke("run").returncode, 0)
        commit_count = subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=self.root)
        self.assertEqual(commit_count.strip(), b"2")


if __name__ == "__main__":
    unittest.main()
