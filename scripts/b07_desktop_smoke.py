#!/usr/bin/env python3
"""Real Electron media playback, source hash and metric seek smoke."""
import json
import os
from fractions import Fraction
from pathlib import Path
import sys
import tempfile

import av
import numpy as np

from accept_phase import ROOT, run_stage
sys.path.insert(0, str(ROOT / "python"))
from urdftools.results.media import inspect_video, locate_metric_event


def main():
    destination = ROOT / "artifacts/B07/desktop"
    destination.mkdir(parents=True, exist_ok=True)
    build_env = os.environ.copy()
    build_env["PATH"] = str(ROOT / ".tools/node/bin") + ":" + build_env.get("PATH", "")
    build_cmd = [str(ROOT / ".tools/node/bin/node"), str(ROOT / ".tools/npm/bin/npm-cli.js"), "run", "build"]
    build_code, build_log = run_stage(build_cmd, env=build_env, timeout=60)
    (destination / "build.log").write_text(build_log)
    if build_code:
        print(json.dumps({"status": "failed", "stage": "frontend-build", "exit_code": build_code}))
        return 1
    with tempfile.TemporaryDirectory(prefix="b07-", dir=ROOT / ".tools") as folder:
        folder = Path(folder)
        video = folder / "clip.webm"
        with av.open(str(video), "w") as output:
            stream = output.add_stream("libvpx", rate=10)
            stream.width = stream.height = 64
            stream.pix_fmt = "yuv420p"
            stream.time_base = Fraction(1, 10)
            for index, pts in enumerate((0, 1, 2, 4, 5)):
                frame = av.VideoFrame.from_ndarray(np.full((64,64,3), index*40, dtype=np.uint8), format="rgb24")
                frame.pts = pts
                frame.time_base = Fraction(1, 10)
                for packet in stream.encode(frame): output.mux(packet)
            for packet in stream.encode(): output.mux(packet)
        report = inspect_video(video, episode_id="episode-1", camera="front", experiment_offset_s=5, declared_fps=10)
        event = locate_metric_event(report, episode_id="episode-1", experiment_time_s=5.4, metric="fall", value=1)
        sidecar = folder / "report.json"
        sidecar.write_text(json.dumps({"schema_version": 1, "video": report, "events": [event]}))
        env = {"PATH": str(ROOT / ".tools/node/bin") + ":/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": str(folder),
               "URDFTOOLS_SMOKE_ARTIFACT_DIR": str(destination), "URDFTOOLS_MEDIA_SMOKE": str(video),
               "URDFTOOLS_MEDIA_REPORT": str(sidecar)}
        command = [str(ROOT / "apps/desktop/node_modules/electron/dist/electron"), str(ROOT / "apps/desktop"),
                   "--smoke", "--ozone-platform=headless", "--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader"]
        code, log = run_stage(command, env=env, timeout=90)
    (destination / "electron.log").write_text(log)
    events = []
    for line in log.splitlines():
        try: events.append(json.loads(line))
        except ValueError: pass
    smoke = next((item for item in events if item.get("event") == "desktop_media_smoke"), None)
    passed = code == 0 and smoke is not None and smoke.get("hashVerified") and smoke.get("frameWarning") and (destination / "media-view.png").is_file()
    (destination / "report.json").write_text(json.dumps({"status": "passed" if passed else "failed", "exit_code": code,
                                                          "event": smoke, "source_sha256": report["source_sha256"]}, indent=2) + "\n")
    print(json.dumps({"status": "passed" if passed else "failed", "electron_event": smoke}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
