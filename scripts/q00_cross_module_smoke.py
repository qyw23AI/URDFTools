#!/usr/bin/env python3
"""Q00 real desktop STEP -> URDF -> reimport/viewer -> static+MuJoCo evaluation;
also exercise interactive model edit/undo/redo. No RL or hardware claims."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from accept_phase import ROOT, run_stage
sys.path.insert(0, str(ROOT / "python"))
from urdftools.importers import ImportService
from urdftools.evaluation.static import scan_urdf


def require(condition, detail):
    if not condition:
        raise AssertionError(detail)


def event_from(log, name):
    for line in log.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("event") == name:
            return record
    return None


def main():
    output = ROOT / "artifacts/Q00"
    output.mkdir(parents=True, exist_ok=True)
    report = {"status": "failed", "origin": "real_C00_STEP_fixture_not_hardware",
              "steps": [], "limitations": [
                  "Synthetic STEP and UI interactions are not real robot validation.",
                  "No external training data or automatic ChatGPT background model call."
              ]}
    try:
        # Actual UI actions; these scripts verify screenshots and observed Electron events.
        for script, label, expected in (
            ("c03_desktop_smoke.py", "cad_wizard_export", ROOT/"artifacts/C03/desktop/robot.zip"),
            ("m01_desktop_smoke.py", "human_edit_undo_redo", ROOT/"artifacts/M01/desktop/robot.zip"),
        ):
            code, log = run_stage([sys.executable, str(ROOT/"scripts"/script)], timeout=270)
            (output/(label+".log")).write_text(log)
            require(code == 0 and expected.stat().st_size > 1000,
                    f"{label} Electron UI failed (exit={code}): {log[-1800:]}")
            report["steps"].append({"id": label, "zip_sha256": hashlib.sha256(expected.read_bytes()).hexdigest(),
                                    "bytes": expected.stat().st_size})
        archive = ROOT/"artifacts/C03/desktop/robot.zip"
        with tempfile.TemporaryDirectory(prefix="q00-e2e-", dir=ROOT/".tools") as temp:
            work = Path(temp)
            imported = ImportService(work/"imports").ingest(archive)
            require(imported["status"] == "ready" and len(imported["models"]) == 1, imported)
            require(len(imported["models"][0]["resources"]) == 2, "Imported ZIP lost CAD meshes")
            with zipfile.ZipFile(archive) as package:
                robot_bytes = package.read("urdftools_robot/robot.urdf")
                package.extractall(work/"extracted")
            urdf = work/"extracted/urdftools_robot/robot.urdf"
            parsed = ET.fromstring(robot_bytes)
            require(len(parsed.findall("link")) == 2 and len(parsed.findall("joint")) == 1,
                    "STEP-derived link/joint tree changed")
            evaluation = scan_urdf(urdf)
            require(evaluation["input_sha256"] == hashlib.sha256(robot_bytes).hexdigest(),
                    "Static evaluation did not use exported URDF")
            errors = [finding for finding in evaluation["findings"] if finding["status"] == "fail"]
            require(not errors, f"Exported URDF static evaluation errors: {errors}")
            sim = [str(ROOT/".tools/sim-venv/bin/python"),
                   str(ROOT/"scripts/validate_cad_package.py"), str(archive)]
            code, log = run_stage(sim, timeout=100)
            require(code == 0, f"MuJoCo package evaluation failed: {log[-1500:]}")
            validated = json.loads(log.strip().splitlines()[-1])
            require(validated["status"] == "passed" and
                    validated["mujoco_floating"]["mass_kg"] > 0,
                    f"Missing real dynamics validation: {validated}")
            report["steps"].append({"id": "reimport_and_evaluate", "import": imported["status"],
                                    "urdf_sha256": evaluation["input_sha256"],
                                    "static_findings": evaluation["finding_count"],
                                    "mujoco_floating_mass_kg": validated["mujoco_floating"]["mass_kg"]})
            # Negative cases on derived temporary files: no changes to the original ZIP.
            joint = parsed.find("joint")
            require(joint is not None and joint.get("type") == "revolute", "No movable CAD joint")
            axis = joint.find("axis")
            require(axis is not None, "No axis in CAD joint")
            axis.set("xyz", "0 0 0")
            bad_urdf = work/"invalid_axis.urdf"
            bad_urdf.write_bytes(ET.tostring(parsed))
            bad_findings = scan_urdf(bad_urdf)["findings"]
            require(any(item["rule_id"] == "invalid_joint_axis" for item in bad_findings),
                    "Static evaluator missed a zero joint axis")
            unsafe = work/"traversal.zip"
            with zipfile.ZipFile(unsafe, "w") as package:
                package.writestr("../escape.urdf", robot_bytes)
            rejected = ImportService(work/"rejects").ingest(unsafe)
            require(rejected["status"] == "failed", "ZIP path traversal was accepted")
            missing_mesh = work/"missing_mesh.zip"
            with zipfile.ZipFile(archive) as original, zipfile.ZipFile(missing_mesh, "w") as broken:
                for item in original.infolist():
                    if item.filename.endswith("/meshes/OffsetPart.stl"):
                        continue
                    broken.writestr(item, original.read(item))
            absent = ImportService(work/"missing").ingest(missing_mesh)
            require(absent["status"] == "failed" and any(
                f["code"] == "missing_resource" for model in absent["models"] for f in model["findings"]),
                "Missing CAD mesh was not located")
            invalid_archive = work/"corrupted.zip"
            invalid_archive.write_bytes(b"PK\\x03\\x04invalid")
            corrupt = ImportService(work/"corrupt").ingest(invalid_archive)
            require(corrupt["status"] == "failed", "Corrupt ZIP was accepted")
            report["steps"].append({"id": "negative_axis_zip_traversal_missing_mesh_corrupt", "zero_axis_detected": True,
                                    "traversal_rejected": True, "missing_mesh_detected": True,
                                    "corrupted_zip_rejected": True})
        # A third real Electron session drags the ZIP made by the CAD wizard, moves its joint.
        with tempfile.TemporaryDirectory(prefix="q00-viewer-", dir=ROOT/".tools") as home:
            env = dict(os.environ, PATH=str(ROOT/".tools/node/bin")+":/usr/bin:/bin",
                       HOME=home, LANG="C.UTF-8", NO_PROXY="127.0.0.1,localhost",
                       HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9",
                       ALL_PROXY="socks5://127.0.0.1:9",
                       URDFTOOLS_VIEWER_SMOKE=str(archive),
                       URDFTOOLS_Q00_VIEWER_SMOKE="1",
                       URDFTOOLS_SMOKE_ARTIFACT_DIR=str(output))
            command = [str(ROOT/"apps/desktop/node_modules/electron/dist/electron"),
                       str(ROOT/"apps/desktop"), "--smoke", "--ozone-platform=headless",
                       "--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader"]
            code, log = run_stage(command, env=env, timeout=130)
        (output/"viewer-electron.log").write_text(log)
        viewer = event_from(log, "desktop_q00_viewer_smoke")
        require(code == 0 and viewer and viewer["jointPoseChanged"] and viewer["meshCount"] >= 2
                and (output/"cad-roundtrip-viewer.png").stat().st_size > 2000,
                f"Real ZIP drag/viewer joint UI failed: {log[-2500:]}")
        report["steps"].append({"id": "exported_zip_electron_viewer_offline_proxy", **viewer})
        report["status"] = "passed"
    except Exception as error:
        report["error"] = str(error)
    (output/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
