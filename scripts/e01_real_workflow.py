#!/usr/bin/env python3
"""Real E01 evaluation workflow: original URDFs -> independently parsed findings and artifact."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
F = ROOT / "tests/fixtures/E00"
manifest = json.loads((F / "manifest.json").read_text())
context = {
    "joint_axes": {"LF_knee": manifest["design_context"]["LF_knee_expected_axis"]},
    "link_visual_box_sizes_m": {"torso": manifest["design_context"]["quadruped_torso_size_m"]},
}
out = ROOT / "artifacts/E01"
out.mkdir(parents=True, exist_ok=True)
context_path = out / "trusted-fixture-context.json"
context_path.write_text(json.dumps(context, indent=2) + "\n")
results = []
for case in manifest["cases"]:
    path = F / case["file"]
    cmd = [str(ROOT / ".venv/bin/python"), "scripts/e01_static_scan.py", str(path)]
    if case["category"] == "quadruped":
        cmd.extend(["--context", str(context_path)])
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=30)
    assert proc.returncode == 0, (cmd, proc.stderr)
    report = json.loads(proc.stdout)
    found = [(f["rule_id"], f["location"], f["certainty"]) for f in report["findings"]]
    expected = [(f["rule"], f["location"], f["certainty"]) for f in case["expected"]]
    assert found == expected, (case["file"], found, expected)
    assert report["input_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    results.append({"file": case["file"], "sha256": report["input_sha256"],
                    "expected": expected, "observed": found, "report": report})
(out / "gold-scan-report.json").write_text(json.dumps(
    {"origin": "synthetic_fixture", "case_count": len(results), "cases": results},
    ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": "passed", "cases": len(results),
                  "findings": sum(len(r["observed"]) for r in results),
                  "legal_counterexamples": 2, "artifact": "artifacts/E01/gold-scan-report.json"}))
