"""Read-only media timing and external metric event alignment."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
from statistics import median

from .jobs import ImportFailure, digest


def inspect_video(path: str | Path, *, episode_id: str, camera: str,
                  experiment_offset_s: float, declared_fps: float | None = None) -> dict:
    try:
        import av
    except ImportError as exc:
        raise ImportFailure("PyAV media reader unavailable") from exc
    path = Path(path).resolve(strict=True)
    if not path.is_file() or not episode_id or not camera or path.stat().st_size > 1024 * 1024 * 1024:
        raise ImportFailure("Bounded video file, episode and camera required")
    if not math.isfinite(experiment_offset_s):
        raise ImportFailure("Invalid experiment/video offset")
    if declared_fps is not None and (not math.isfinite(declared_fps) or declared_fps <= 0):
        raise ImportFailure("Invalid declared frame rate")
    timestamps = []
    try:
        with av.open(str(path), mode="r") as container:
            streams = [stream for stream in container.streams if stream.type == "video"]
            if len(streams) != 1:
                raise ImportFailure("Exactly one video stream required")
            stream = streams[0]
            for frame in container.decode(stream):
                if frame.pts is None or frame.time_base is None:
                    raise ImportFailure("Video frame lacks presentation timestamp")
                timestamp = float(frame.pts * frame.time_base)
                if not math.isfinite(timestamp) or (timestamps and timestamp <= timestamps[-1]):
                    raise ImportFailure("Video PTS must strictly increase")
                timestamps.append(timestamp)
                if len(timestamps) > 2_000_000:
                    raise ImportFailure("Video frame limit exceeded")
    except (OSError, av.error.FFmpegError) as exc:
        raise ImportFailure("Cannot decode video") from exc
    if len(timestamps) < 2:
        raise ImportFailure("At least two decodable frames required")
    intervals = [b-a for a, b in zip(timestamps, timestamps[1:])]
    frame_interval = median(intervals)
    nominal_fps = 1/frame_interval
    expected_interval = 1/declared_fps if declared_fps is not None else frame_interval
    gap_indices = [i+1 for i, delta in enumerate(intervals) if delta > 1.5 * expected_interval]
    fps_mismatch = declared_fps is not None and abs(nominal_fps-declared_fps)/declared_fps > 0.05
    return {"episode_id": episode_id, "camera": camera, "source_sha256": digest(path),
            "offset_s": experiment_offset_s, "frame_count": len(timestamps),
            "timestamps_s": timestamps, "duration_s": timestamps[-1]-timestamps[0],
            "observed_fps_median": nominal_fps, "declared_fps": declared_fps,
            "fps_mismatch": fps_mismatch, "suspected_gap_frame_indices": gap_indices,
            "variable_frame_rate": max(intervals)-min(intervals) > 0.05 * frame_interval,
            "torque_from_video": None, "energy_from_video": None}


def locate_metric_event(video: dict, *, episode_id: str, experiment_time_s: float,
                        metric: str, value: float) -> dict:
    if episode_id != video.get("episode_id") or not metric:
        raise ImportFailure("Metric event episode or name mismatch")
    if not math.isfinite(experiment_time_s) or not math.isfinite(value):
        raise ImportFailure("Non-finite metric event")
    video_time = experiment_time_s - video["offset_s"]
    timestamps = video["timestamps_s"]
    if video_time < timestamps[0] or video_time > timestamps[-1]:
        return {"status": "outside_video", "metric": metric, "experiment_time_s": experiment_time_s,
                "video_time_s": video_time, "frame_index": None}
    frame_index = min(range(len(timestamps)), key=lambda i: abs(timestamps[i]-video_time))
    return {"status": "located", "metric": metric, "value": value,
            "experiment_time_s": experiment_time_s, "video_time_s": video_time,
            "frame_index": frame_index, "frame_timestamp_s": timestamps[frame_index],
            "offset_error_s": timestamps[frame_index]-video_time}
