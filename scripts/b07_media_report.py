#!/usr/bin/env python3
"""Create a local sidecar for the desktop media evidence view."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from urdftools.results.media import inspect_video, locate_metric_event


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--episode", required=True)
    parser.add_argument("--camera", required=True)
    parser.add_argument("--offset", type=float, required=True)
    parser.add_argument("--fps", type=float)
    parser.add_argument("--events", type=Path, help="JSON list: experiment_time_s, metric, value, episode_id")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    video = inspect_video(args.video, episode_id=args.episode, camera=args.camera,
                          experiment_offset_s=args.offset, declared_fps=args.fps)
    events = []
    if args.events:
        for event in json.loads(args.events.read_text()):
            events.append(locate_metric_event(video, **event))
    report = {"schema_version": 1, "video": video, "events": events}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "passed", "video_sha256": video["source_sha256"],
                      "frames": video["frame_count"], "events": len(events), "output": str(args.output)}))


if __name__ == "__main__":
    main()
