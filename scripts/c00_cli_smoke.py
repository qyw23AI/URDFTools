"""CLI-level acceptance of the real STEP inspector against both checked-in fixtures."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/C00"
OUTPUT = ROOT / "artifacts/C00/cli"
CASES = {
    "two_part_mm": {
        "file": FIXTURES / "two_part_mm.step",
        "unit": "mm",
        "parts": 2,
        "assemblies": 1,
        "missing_colors": 0,
        "dimensions": {"BasePart": [0.02, 0.01, 0.005], "OffsetPart": [0.01, 0.006, 0.004]},
    },
    "single_part_m": {
        "file": FIXTURES / "single_part_m.step",
        "unit": "m",
        "parts": 1,
        "assemblies": 0,
        "missing_colors": 1,
        "dimensions": {"MeterPart": [0.02, 0.01, 0.005]},
    },
}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    records = []
    for label, spec in CASES.items():
        report_path = OUTPUT / f"{label}.json"
        command = [sys.executable, str(ROOT / "scripts/cad_step_inspect.py"), str(spec["file"]), "--output", str(report_path)]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "python") + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=60)
        record = {"case": label, "command": command, "exit_code": result.returncode,
                  "stdout": result.stdout, "stderr": result.stderr, "report": str(report_path.relative_to(ROOT))}
        if result.returncode == 0 and report_path.is_file():
            parsed = json.loads(report_path.read_text(encoding="utf-8"))
            record["status"] = parsed.get("status")
            record["source_sha256"] = parsed.get("source", {}).get("sha256")
            record["unit"] = parsed.get("units", {}).get("source_length_unit")
            record["counts"] = parsed.get("counts")
            parts = {part["name"]: part for part in parsed.get("parts", [])}
            record["parts"] = sorted(parts)
            passed = (
                parsed.get("status") == "ready"
                and record["unit"] == spec["unit"]
                and parsed["counts"]["part_instance_count"] == spec["parts"]
                and parsed["counts"]["assembly_count"] == spec["assemblies"]
                and parsed["counts"]["missing_color_count"] == spec["missing_colors"]
                and parsed["adapter"]["status"] == "matched"
                and set(parts) == set(spec["dimensions"])
            )
            if passed:
                for name, expected_dimensions in spec["dimensions"].items():
                    actual = parts[name]["bounds"]["dimensions_m"]
                    passed = passed and len(actual) == 3 and all(abs(a - b) < 1e-6 for a, b in zip(actual, expected_dimensions))
            record["status"] = "passed" if passed else "failed"
        else:
            record["status"] = "failed"
        records.append(record)
        print(json.dumps({"case": label, "status": record["status"], "unit": record.get("unit"),
                          "counts": record.get("counts"), "source_sha256": record.get("source_sha256")}, ensure_ascii=False))
    report = {"status": "passed" if all(record["status"] == "passed" for record in records) else "failed", "checks": records}
    (ROOT / "artifacts/C00/cli-smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
