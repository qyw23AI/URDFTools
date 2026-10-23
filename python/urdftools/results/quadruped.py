"""Deterministic quadruped metrics from externally recorded time series."""
from __future__ import annotations

import math

from .jobs import ImportFailure

FEET = ("front_left", "front_right", "rear_left", "rear_right")


def evaluate_quadruped(frames: list[dict], foot_mapping: dict[str, str]) -> dict:
    """Times are seconds; speeds m/s; no model or video inference is used."""
    if set(foot_mapping) != set(FEET) or len(set(foot_mapping.values())) != 4 or any(not isinstance(v, str) or not v for v in foot_mapping.values()):
        raise ImportFailure("Four distinct explicit foot mappings required")
    if not isinstance(frames, list) or len(frames) < 2:
        raise ImportFailure("At least two recorded frames required")
    times = []
    for frame in frames:
        if not isinstance(frame, dict):
            raise ImportFailure("Frame must be an object")
        try:
            t = float(frame["time_s"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ImportFailure("Missing or invalid timestamp") from exc
        if not math.isfinite(t) or (times and t <= times[-1]):
            raise ImportFailure("Timestamps must strictly increase")
        times.append(t)
    duration = times[-1] - times[0]

    def contact_at(frame, role):
        source = foot_mapping[role]
        contacts = frame.get("contact")
        if contacts is None or source not in contacts:
            return None
        value = contacts[source]
        if type(value) is not bool:
            raise ImportFailure("Contact must be boolean")
        return value

    duty = {}
    stride_hz = {}
    slip_m = {}
    for role in FEET:
        contact = [contact_at(frame, role) for frame in frames]
        if any(c is None for c in contact):
            duty[role] = stride_hz[role] = slip_m[role] = None
            continue
        duty[role] = sum((times[i+1]-times[i]) for i in range(len(times)-1) if contact[i]) / duration
        touchdowns = [times[i] for i in range(1, len(times)) if contact[i] and not contact[i-1]]
        stride_hz[role] = ((len(touchdowns)-1)/(touchdowns[-1]-touchdowns[0])) if len(touchdowns) >= 2 else None
        speed = []
        for frame in frames:
            values = frame.get("foot_speed_m_s")
            if values is None or foot_mapping[role] not in values:
                speed = []
                break
            try:
                v = float(values[foot_mapping[role]])
            except (ValueError, TypeError) as exc:
                raise ImportFailure("Invalid foot speed") from exc
            if not math.isfinite(v) or v < 0:
                raise ImportFailure("Foot speed must be finite and nonnegative")
            speed.append(v)
        slip_m[role] = sum(speed[i]*(times[i+1]-times[i]) for i in range(len(times)-1) if contact[i]) if speed else None

    tracking = None
    if all("command_speed_m_s" in f and "body_speed_m_s" in f for f in frames):
        differences = []
        for frame in frames:
            try:
                command = float(frame["command_speed_m_s"])
                actual = float(frame["body_speed_m_s"])
            except (TypeError, ValueError) as exc:
                raise ImportFailure("Invalid body or command speed") from exc
            if not math.isfinite(command) or not math.isfinite(actual):
                raise ImportFailure("Non-finite body or command speed")
            differences.append((command-actual)**2)
        tracking = math.sqrt(sum(differences)/len(differences))
    falls = None
    if all("fallen" in f for f in frames):
        values = [f["fallen"] for f in frames]
        if any(type(v) is not bool for v in values):
            raise ImportFailure("fallen must be boolean")
        falls = int(values[0]) + sum(values[i] and not values[i-1] for i in range(1, len(values)))
    unknown = []
    if any(v is None for v in duty.values()): unknown.append("contact_or_duty")
    if any(v is None for v in stride_hz.values()): unknown.append("stride_frequency")
    if any(v is None for v in slip_m.values()): unknown.append("foot_speed_or_slip")
    if tracking is None: unknown.append("tracking")
    if falls is None: unknown.append("falls")
    return {"duration_s": duration, "foot_mapping": dict(foot_mapping), "duty_factor": duty,
            "stride_hz": stride_hz, "slip_distance_m": slip_m, "tracking_rmse_m_s": tracking,
            "fall_events": falls, "torque_saturation": None, "unknown": unknown}
