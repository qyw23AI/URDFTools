"""Humanoid-only metrics from explicit external sensors and semantic mappings."""
from __future__ import annotations

import math
from pathlib import Path
import xml.etree.ElementTree as ET

from .jobs import ImportFailure

CORE_ROLES = ("left_hip", "left_knee", "left_ankle", "right_hip", "right_knee", "right_ankle")


def validate_action_semantics(urdf: str | Path, roles: dict[str, str], action_joints: list[str]) -> dict:
    """Action dimensions are supplied by the experiment, never inferred from model name."""
    if set(roles) != set(CORE_ROLES) or len(set(roles.values())) != 6:
        raise ImportFailure("Six distinct left/right leg semantic roles required")
    try:
        root = ET.parse(urdf).getroot()
    except (OSError, ET.ParseError) as exc:
        raise ImportFailure("Invalid source URDF") from exc
    if root.tag != "robot":
        raise ImportFailure("Expected URDF robot")
    movable = {joint.get("name") for joint in root.findall("joint") if joint.get("type") not in {"fixed", None}}
    if not set(roles.values()).issubset(movable):
        raise ImportFailure("Semantic role points to unknown or fixed joint")
    if not isinstance(action_joints, list) or not action_joints or len(set(action_joints)) != len(action_joints) or not set(action_joints).issubset(movable):
        raise ImportFailure("Action joints must be a unique known movable subset")
    return {"urdf_movable_joints": len(movable), "action_dimensions": len(action_joints),
            "roles": dict(roles), "action_joints": list(action_joints)}


def _inside(point, polygon):
    if not isinstance(point, (list, tuple)) or len(point) != 2 or not isinstance(polygon, (list, tuple)) or len(polygon) < 3:
        raise ImportFailure("COM and support polygon require 2D coordinates")
    coordinates = [point, *polygon]
    try:
        coordinates = [[float(x), float(y)] for x, y in coordinates]
    except (TypeError, ValueError) as exc:
        raise ImportFailure("Invalid support coordinates") from exc
    if any(not math.isfinite(v) for xy in coordinates for v in xy):
        raise ImportFailure("Non-finite support coordinates")
    x, y = coordinates[0]
    vertices = coordinates[1:]
    inside = False
    for i, (ax, ay) in enumerate(vertices):
        bx, by = vertices[(i+1) % len(vertices)]
        cross = (bx-ax)*(y-ay)-(by-ay)*(x-ax)
        if abs(cross) < 1e-10 and min(ax,bx)-1e-10 <= x <= max(ax,bx)+1e-10 and min(ay,by)-1e-10 <= y <= max(ay,by)+1e-10:
            return True
        if (ay > y) != (by > y) and x < (bx-ax)*(y-ay)/(by-ay)+ax:
            inside = not inside
    return inside


def evaluate_humanoid(frames: list[dict], foot_mapping: dict[str, str]) -> dict:
    if set(foot_mapping) != {"left", "right"} or len(set(foot_mapping.values())) != 2:
        raise ImportFailure("Distinct left and right foot sources required")
    if not isinstance(frames, list) or len(frames) < 2:
        raise ImportFailure("At least two frames required")
    times = []
    for frame in frames:
        try:
            t = float(frame["time_s"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ImportFailure("Invalid timestamp") from exc
        if not math.isfinite(t) or (times and t <= times[-1]):
            raise ImportFailure("Times must strictly increase")
        times.append(t)
    duration = times[-1] - times[0]
    modes = {"left_only": 0.0, "right_only": 0.0, "double": 0.0, "flight": 0.0}
    contacts = []
    for frame in frames:
        source = frame.get("contact")
        if not isinstance(source, dict) or any(foot_mapping[k] not in source for k in ("left", "right")):
            contacts = []
            break
        left, right = source[foot_mapping["left"]], source[foot_mapping["right"]]
        if type(left) is not bool or type(right) is not bool:
            raise ImportFailure("Contact samples must be boolean")
        contacts.append((left, right))
    if contacts:
        for i, (left, right) in enumerate(contacts[:-1]):
            mode = "double" if left and right else "left_only" if left else "right_only" if right else "flight"
            modes[mode] += times[i+1]-times[i]
        modes = {k: v/duration for k, v in modes.items()}
        left_duty = modes["left_only"] + modes["double"]
        right_duty = modes["right_only"] + modes["double"]
        symmetry = abs(left_duty-right_duty)
    else:
        modes = {k: None for k in modes}
        symmetry = None
    trunk_rms = None
    if all("trunk_roll_rad" in f and "trunk_pitch_rad" in f for f in frames):
        values = []
        for frame in frames:
            try:
                roll, pitch = float(frame["trunk_roll_rad"]), float(frame["trunk_pitch_rad"])
            except (TypeError, ValueError) as exc:
                raise ImportFailure("Invalid trunk attitude") from exc
            if not math.isfinite(roll) or not math.isfinite(pitch):
                raise ImportFailure("Non-finite trunk attitude")
            values.append(roll*roll+pitch*pitch)
        trunk_rms = math.sqrt(sum(values)/len(values))
    support_inside = None
    if contacts and all("com_xy_m" in f and "support_polygon_xy_m" in f for f in frames[:-1]):
        supported, inside = 0, 0
        for frame, (left, right) in zip(frames[:-1], contacts[:-1]):
            if left or right:
                supported += 1
                inside += _inside(frame["com_xy_m"], frame["support_polygon_xy_m"])
        support_inside = inside/supported if supported else None
    unknown = []
    if not contacts: unknown.append("foot_contact")
    if trunk_rms is None: unknown.append("trunk_attitude")
    if support_inside is None: unknown.append("quasistatic_com_projection")
    return {"duration_s": duration, "foot_mapping": dict(foot_mapping), "support_mode_fraction": modes,
            "left_right_duty_difference": symmetry, "trunk_tilt_rms_rad": trunk_rms,
            "quasistatic_com_inside_fraction": support_inside, "dynamic_balance": None,
            "unknown": unknown}
