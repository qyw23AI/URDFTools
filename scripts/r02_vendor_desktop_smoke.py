#!/usr/bin/env python3
"""R02 real Electron/Three.js viewer smoke on the pinned G1 and H1 folders."""
import json
from pathlib import Path
import tempfile

from accept_phase import run_stage, ROOT


def event_from(log: str):
    for line in log.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("event") == "desktop_viewer_s06_smoke":
            return event
    return None


def main() -> int:
    dest = ROOT / "artifacts/R02/desktop"
    dest.mkdir(parents=True, exist_ok=True)
    cases = [
        ("g1", ROOT / "tests/fixtures/S06/reference_models/g1_description", 40, 39),
        ("h1", ROOT / "tests/fixtures/R02/h1_description", 25, 24),
    ]
    failures = []
    for label, fixture, links, joints in cases:
        with tempfile.TemporaryDirectory(prefix="r02-" + label + "-", dir=ROOT / ".tools") as home:
            env = {
                "PATH": str(ROOT / ".tools/node/bin") + ":/usr/bin:/bin",
                "LANG": "C.UTF-8", "HOME": home,
                "URDFTOOLS_SMOKE_ARTIFACT_DIR": str(dest),
                "URDFTOOLS_VIEWER_SMOKE": str(fixture),
                "URDFTOOLS_VIEWER_S06_SMOKE": label,
            }
            cmd = [str(ROOT / "apps/desktop/node_modules/electron/dist/electron"),
                str(ROOT / "apps/desktop"), "--smoke", "--ozone-platform=headless",
                "--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader"]
            code, log = run_stage(cmd, env=env, timeout=150)
        (dest / (label + "-viewer.log")).write_text(log)
        event = event_from(log)
        passed = (code == 0 and event is not None
            and event.get("model") == label
            and event.get("linkCount") == links and event.get("jointCount") == joints
            and event.get("assetsLoaded") is True and event.get("meshCount", 0) >= 5
            and event.get("jointPoseChanged") is True
            and event.get("collisionToggleVerified") is True
            and event.get("physicsUnchanged") is True
            and event.get("screenshotReady") is True
            and (dest / (label + "-viewer.png")).is_file()
            and (dest / (label + "-viewer-export.png")).is_file())
        (dest / (label + "-report.json")).write_text(
            json.dumps({"status": "passed" if passed else "failed",
                        "model": label, "exit_code": code, "event": event},
                       ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"model": label, "status": "passed" if passed else "failed",
                          "links": links, "joints": joints}))
        if not passed:
            failures.append(label)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
