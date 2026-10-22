"""CLI acceptance of mass-property reports on box, sphere assembly, rotated box and unknown material."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/C01"
OUTPUT = ROOT / "artifacts/C01/cli"
CASES = [
    ("box", FIXTURES / "box_mm.step", ["--density", "1000"], "Box20x10x5"),
    ("double-sphere", FIXTURES / "offset_double_sphere_mm.step", ["--density", "1000"], "OffsetDoubleSphere"),
    ("rotated-box", FIXTURES / "rotated_box_mm.step", ["--density", "1000"], "RotatedBox"),
    ("unknown-material", FIXTURES / "box_mm.step", [], "Box20x10x5"),
]


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    records = []
    for label, fixture, density_args, part_name in CASES:
        report_path = OUTPUT / f"{label}.json"
        command = [sys.executable, str(ROOT / "scripts/cad_step_mass.py"), str(fixture), *density_args, "--output", str(report_path)]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "python") + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=60)
        record = {"case": label, "command": command, "exit_code": result.returncode,
                  "stdout": result.stdout, "stderr": result.stderr, "report": str(report_path.relative_to(ROOT))}
        passed = result.returncode == 0 and report_path.is_file()
        if passed:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            record["status"] = report.get("status")
            record["assembly"] = report.get("assembly")
            parts = {part["name"]: part for part in report.get("parts", [])}
            passed = report.get("status") == "ready"
            if label == "box":
                passed = passed and part_name in parts and abs(parts[part_name]["mass_kg"] - 0.001) < 1e-10 and report["assembly"]["mass_complete"]
            elif label == "double-sphere":
                passed = passed and len(parts) == 2 and abs(report["assembly"]["center_of_mass_m"][0] - 0.025) < 1e-8
            elif label == "rotated-box":
                passed = passed and part_name in parts and abs(parts[part_name]["inertia_com_kg_m2"][0][1] + 1.25e-8) < 1e-12
            elif label == "unknown-material":
                passed = passed and part_name in parts and parts[part_name]["mass_kg"] is None and parts[part_name]["inertia_com_kg_m2"] is None
                passed = passed and report["assembly"]["total_mass_kg"] is None and not report["assembly"]["mass_complete"]
        record["status"] = "passed" if passed else "failed"
        records.append(record)
        print(json.dumps({"case": label, "status": record["status"], "exit_code": result.returncode}, ensure_ascii=False))
    report = {"status": "passed" if all(item["status"] == "passed" for item in records) else "failed", "checks": records}
    (ROOT / "artifacts/C01/cli-smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
