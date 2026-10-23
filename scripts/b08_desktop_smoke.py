#!/usr/bin/env python3
"""Four real Electron imports, matching comparisons, video streaming and restart recovery."""
import json
import os
from pathlib import Path
import sys
import tempfile

from accept_phase import ROOT, run_stage
sys.path.insert(0, str(ROOT / "tests/b08"))
from test_desktop_bundle import DesktopBundleTests


def main():
    artifacts = ROOT / "artifacts/B08/desktop"
    artifacts.mkdir(parents=True, exist_ok=True)
    build_env = os.environ.copy()
    build_env["PATH"] = str(ROOT / ".tools/node/bin") + ":" + build_env.get("PATH", "")
    node = str(ROOT / ".tools/node/bin/node")
    npm = str(ROOT / ".tools/npm/bin/npm-cli.js")
    code, log = run_stage([node, npm, "run", "build"], env=build_env, timeout=60)
    (artifacts / "build.log").write_text(log)
    if code:
        print(json.dumps({"status": "failed", "stage": "frontend-build", "exit_code": code}))
        return 1
    with tempfile.TemporaryDirectory(prefix="b08-desktop-", dir=ROOT / ".tools") as folder:
        base = Path(folder)
        fixtures = DesktopBundleTests()
        fixtures.root = base
        store = base / "store"
        results = []
        for category in ("quadruped", "humanoid"):
            for role in ("standard", "user"):
                source = fixtures.bundle(category, role)
                run_id = f"{category}-{role}"
                env = {"PATH": str(ROOT / ".tools/node/bin") + ":/usr/bin:/bin", "LANG": "C.UTF-8",
                       "HOME": str(base), "URDFTOOLS_B08_SMOKE_SOURCE": str(source),
                       "URDFTOOLS_B08_SMOKE_STORE": str(store), "URDFTOOLS_B08_SMOKE_RUN_ID": run_id,
                       "URDFTOOLS_SMOKE_ARTIFACT_DIR": str(artifacts)}
                if role == "user":
                    env["URDFTOOLS_B08_SMOKE_REFERENCE"] = f"{category}-standard"
                    env["URDFTOOLS_B08_SMOKE_CANDIDATE"] = run_id
                command = [str(ROOT / "apps/desktop/node_modules/electron/dist/electron"),
                           str(ROOT / "apps/desktop"), "--smoke", "--ozone-platform=headless",
                           "--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader"]
                exit_code, output = run_stage(command, env=env, timeout=90)
                (artifacts / f"{run_id}.log").write_text(output)
                events = []
                for line in output.splitlines():
                    try: events.append(json.loads(line))
                    except ValueError: pass
                smoke = next((item for item in events if item.get("event") == "b08_desktop_smoke"), None)
                video = next((item for item in events if item.get("event") == "b08_video_protocol"), None)
                okay = (exit_code == 0 and smoke is not None and smoke.get("persisted") and
                        (role != "user" or video is not None and video.get("status") == 200) and
                        (artifacts / f"b08-{run_id}.png").is_file())
                results.append({"run_id": run_id, "status": "passed" if okay else "failed",
                                "exit_code": exit_code, "event": smoke, "video": video})
                if not okay:
                    break
            if results[-1]["status"] != "passed":
                break
    report = {"status": "passed" if len(results) == 4 and all(item["status"] == "passed" for item in results) else "failed",
              "runs": results, "synthetic_fixture": True, "verified_reference_count": 0}
    (artifacts / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
