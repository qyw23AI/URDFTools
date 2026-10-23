"""Conservative URDF E0/E1 checker. No default values are invented for unknown physics."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import xml.etree.ElementTree as ET

RULE_VERSION = "1.0"


def _numbers(raw: str | None, count: int) -> tuple[float, ...] | None:
    try:
        values = tuple(float(v) for v in raw.split()) if raw is not None else ()
    except (ValueError, OverflowError):
        return None
    return values if len(values) == count and all(math.isfinite(v) for v in values) else None


def _det3(a: list[list[float]]) -> float:
    return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
            - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
            + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))


def symmetric_eigenvalues(a: list[list[float]]) -> tuple[float, float, float]:
    """Analytic eigenvalues of a finite real symmetric 3x3 matrix."""
    off2 = a[0][1] ** 2 + a[0][2] ** 2 + a[1][2] ** 2
    if off2 == 0:
        return tuple(sorted((a[0][0], a[1][1], a[2][2])))
    q = sum(a[i][i] for i in range(3)) / 3
    p = math.sqrt((sum((a[i][i] - q) ** 2 for i in range(3)) + 2 * off2) / 6)
    if p == 0:
        return (q, q, q)
    b = [[(a[i][j] - (q if i == j else 0)) / p for j in range(3)]
         for i in range(3)]
    r = max(-1.0, min(1.0, _det3(b) / 2))
    phi = math.acos(r) / 3
    high = q + 2 * p * math.cos(phi)
    low = q + 2 * p * math.cos(phi + 2 * math.pi / 3)
    mid = 3 * q - high - low
    return tuple(sorted((low, mid, high)))


def scan_urdf(path: str | Path, design_context: dict | None = None) -> dict:
    """Scan source URDF and optionally trusted SI design context, without changing input."""
    path = Path(path)
    source = path.read_bytes()
    source_hash = hashlib.sha256(source).hexdigest()
    root = ET.fromstring(source)
    if root.tag != "robot":
        raise ValueError("Expected <robot> root")
    context = design_context or {}
    findings: list[dict] = []

    def emit(rule: str, location: str, observed, *, reference=None, unit=None,
             certainty="definite", category="physical_inconsistency", severity="error",
             action="Verify the source URDF and correct the offending element."):
        findings.append({
            "rule_id": rule, "rule_version": RULE_VERSION,
            "status": "fail" if severity == "error" else "unknown",
            "category": category, "severity": severity, "certainty": certainty,
            "location": location, "observed": observed, "reference": reference,
            "unit": unit, "source_sha256": source_hash, "source": str(path),
            "next_action": action,
        })

    link_nodes = root.findall("link")
    joint_nodes = root.findall("joint")
    names = [link.get("name") for link in link_nodes]
    joint_names = [joint.get("name") for joint in joint_nodes]
    for group, group_names in (("link", names), ("joint", joint_names)):
        for name in group_names:
            if not name or group_names.count(name) > 1:
                emit("invalid_name", f"{group}/{name or '(missing)'}", name,
                     category="description_error")
    known_links = set(names)
    children = []
    edges = {}
    for joint in joint_nodes:
        name = joint.get("name") or "(unnamed)"
        parent = joint.find("parent")
        child = joint.find("child")
        parent_name = parent.get("link") if parent is not None else None
        child_name = child.get("link") if child is not None else None
        if parent_name not in known_links or child_name not in known_links or parent_name == child_name:
            emit("invalid_joint_topology", name, {"parent": parent_name, "child": child_name},
                 category="description_error")
        if child_name in children:
            emit("duplicate_joint_child", name, child_name, category="description_error")
        children.append(child_name)
        edges.setdefault(parent_name, []).append(child_name)
        if joint.get("type") not in {"revolute", "continuous", "prismatic", "fixed", "floating", "planar"}:
            emit("invalid_joint_type", name, joint.get("type"), category="description_error")
        if joint.get("type") in {"revolute", "continuous", "prismatic"}:
            axis_node = joint.find("axis")
            # URDF has an implicit (1,0,0) if <axis> omitted. Do not flag that as a zero vector.
            axis = _numbers(axis_node.get("xyz"), 3) if axis_node is not None else (1.0, 0.0, 0.0)
            if axis is None or math.hypot(*axis) <= 1e-12:
                emit("invalid_joint_axis", name, axis_node.get("xyz") if axis_node is not None else None,
                     reference="nonzero finite 3-vector", category="description_error")
            else:
                expected = context.get("joint_axes", {}).get(name)
                expected_xyz = _numbers(" ".join(map(str, expected)), 3) if isinstance(expected, list) else None
                if expected_xyz and math.hypot(*expected_xyz) > 0:
                    cosine = sum(x*y for x, y in zip(axis, expected_xyz)) / (
                        math.hypot(*axis) * math.hypot(*expected_xyz))
                    if cosine < 1 - 1e-6:
                        emit("context_axis_mismatch", name, list(axis), reference=list(expected_xyz),
                             certainty="context_dependent", unit="direction",
                             action="Verify the joint frame and rotation axis against trusted CAD metadata.")
        if joint.get("type") in {"revolute", "prismatic"}:
            limit = joint.find("limit")
            if limit is None or any(_numbers(limit.get(key), 1) is None for key in ("lower", "upper", "effort", "velocity")):
                emit("invalid_joint_limit", name, None, category="description_error")

    roots = known_links - set(children)
    if len(roots) != 1 or len(children) != len(joint_nodes):
        emit("invalid_robot_tree", "robot", {"roots": sorted(str(x) for x in roots)},
             reference="one root, one parent per child", category="description_error")
    elif roots:
        visited, waiting = set(), list(roots)
        while waiting:
            current = waiting.pop()
            if current in visited:
                break
            visited.add(current)
            waiting.extend(edges.get(current, []))
        if visited != known_links:
            emit("invalid_robot_tree", "robot", sorted(str(x) for x in known_links - visited),
                 category="description_error")

    dynamic_children = {j.find("child").get("link") for j in joint_nodes
                        if j.get("type") not in ("fixed",) and j.find("child") is not None}
    for link in link_nodes:
        name = link.get("name") or "(unnamed)"
        inertial = link.find("inertial")
        if inertial is None:
            if name in dynamic_children:
                emit("missing_dynamic_inertia", name, None, category="missing_data",
                     severity="warning", certainty="context_dependent",
                     action="Provide measured or CAD mass and COM/inertia before a dynamics conclusion.")
            continue
        mass_node = inertial.find("mass")
        mass = _numbers(mass_node.get("value"), 1) if mass_node is not None else None
        if not mass or mass[0] <= 0:
            emit("invalid_mass", name, mass, reference="positive kg", unit="kg")
        inertia = inertial.find("inertia")
        keys = ("ixx", "ixy", "ixz", "iyy", "iyz", "izz")
        tensor = [_numbers(inertia.get(key), 1) if inertia is not None else None for key in keys]
        if any(t is None for t in tensor):
            emit("invalid_inertia", name, None, unit="kg*m^2", reference="finite 3x3 inertia tensor")
        else:
            xx, xy, xz, yy, yz, zz = (v[0] for v in tensor)
            eig = symmetric_eigenvalues([[xx, xy, xz], [xy, yy, yz], [xz, yz, zz]])
            scale = max(abs(v[0]) for v in tensor)
            tolerance = max(1e-16, scale * 1e-8)
            if eig[0] < -tolerance:
                emit("negative_inertia", name, list(eig), unit="kg*m^2",
                     reference="principal moments >= 0")
            elif eig[2] > eig[0] + eig[1] + tolerance:
                emit("inertia_triangle_violation", name, list(eig), unit="kg*m^2",
                     reference="max principal moment <= sum of other two")
        origin = inertial.find("origin")
        if origin is not None and (
            (origin.get("xyz") is not None and _numbers(origin.get("xyz"), 3) is None) or
            (origin.get("rpy") is not None and _numbers(origin.get("rpy"), 3) is None)
        ):
            emit("invalid_inertial_origin", name, origin.attrib, category="description_error")

        for index, visual in enumerate(link.findall("visual")):
            box = visual.find("./geometry/box")
            if box is None:
                continue
            sizes = _numbers(box.get("size"), 3)
            if sizes is None or any(x <= 0 for x in sizes):
                emit("invalid_visual_size", f"{name}/visual/box", box.get("size"),
                     category="description_error")
                continue
            expected = context.get("link_visual_box_sizes_m", {}).get(name)
            expected_xyz = _numbers(" ".join(map(str, expected)), 3) if isinstance(expected, list) else None
            if expected_xyz and all(x > 0 for x in expected_xyz):
                ratios = [x/y for x, y in zip(sizes, expected_xyz)]
                if any(abs(math.log(ratio)) > math.log(1.05) for ratio in ratios):
                    emit("context_scale_mismatch", f"{name}/visual/box", list(sizes),
                         reference=list(expected_xyz), unit="m",
                         certainty="context_dependent",
                         action="Check CAD/URDF length units; do not automatically rescale geometry.")

    return {
        "schema_version": 1, "input_sha256": source_hash, "input": str(path),
        "design_context_supplied": bool(context), "finding_count": len(findings),
        "findings": findings, "result": "findings" if findings else "no_findings",
        "limitations": ["No mechanical truth or training suitability inferred from static checks.",
                        "Geometry size and axis direction require trusted external design context."],
    }
