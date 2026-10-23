"""Conservative G1/H1 URDF assessment; never infer dynamic gait stability."""
from __future__ import annotations
import hashlib
import math
import xml.etree.ElementTree as ET

from urdftools.evaluation.quadruped import _area, _mul, _mv, _nums, _origin, _rpy
from urdftools.evaluation.static import symmetric_eigenvalues

PROFILES = {
    "g1": (29, ("hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll"), "ankle_roll_link"),
    "h1": (19, ("hip_yaw", "hip_roll", "hip_pitch", "knee", "ankle"), "ankle_link"),
}
SIDES = ("left", "right")


def _finite(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) >= 1e90:
        raise ValueError("bounded finite number required")
    return float(v)


def _xy(v):
    if not isinstance(v, list) or len(v) != 2:
        raise ValueError("expected [x,y] in metres")
    return tuple(_finite(x) for x in v)


def _hull(points):
    pts = sorted(set(points))
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    lower, upper = [], []
    for v in pts:
        while len(lower) > 1 and cross(lower[-2], lower[-1], v) <= 0:
            lower.pop()
        lower.append(v)
    for v in reversed(pts):
        while len(upper) > 1 and cross(upper[-2], upper[-1], v) <= 0:
            upper.pop()
        upper.append(v)
    return lower[:-1]+upper[:-1]


def _contains(points, xy):
    poly = _hull(points)
    if len(poly) < 3 or _area(poly) <= 1e-10:
        return None
    for i, a in enumerate(poly):
        b = poly[(i+1) % len(poly)]
        if (b[0]-a[0])*(xy[1]-a[1])-(b[1]-a[1])*(xy[0]-a[0]) < -1e-10:
            return False
    return True


def _foot_geometry(link):
    """Collision existence and local XY proxy, not actual pressure/contact patch."""
    points, valid, invalid, unresolved = [], 0, 0, 0
    for c in link.findall("collision"):
        geo = c.find("geometry")
        if geo is None or len(geo) != 1:
            invalid += 1
            continue
        shape = geo[0]
        try:
            xyz, rpy = _origin(c)
            rot = _rpy(rpy)
            local = []
            if shape.tag == "box":
                size = _nums(shape.get("size"), 3)
                if size is None or min(size) <= 0:
                    raise ValueError("invalid box")
                local = [(x*size[0]/2, y*size[1]/2, 0.) for x in (-1, 1) for y in (-1, 1)]
            elif shape.tag == "sphere":
                radius = _nums(shape.get("radius"), 1)
                if radius is None or radius[0] <= 0:
                    raise ValueError("invalid sphere")
                local = [(0., 0., 0.)]
            elif shape.tag == "cylinder":
                r, h = _nums(shape.get("radius"), 1), _nums(shape.get("length"), 1)
                if r is None or h is None or min(r[0], h[0]) <= 0:
                    raise ValueError("invalid cylinder")
                unresolved += 1
            elif shape.tag == "mesh":
                if not shape.get("filename"):
                    raise ValueError("mesh filename required")
                unresolved += 1
            else:
                raise ValueError("unsupported collision")
            for pt in local:
                v = _mv(rot, pt)
                points.append((xyz[0]+v[0], xyz[1]+v[1]))
            valid += 1
        except (ValueError, OverflowError):
            invalid += 1
    return valid, invalid, unresolved, _area(points)


def evaluate_humanoid_trace(trace, joint_limits):
    """Caller-supplied world-frame sole polygons; quasi-static only."""
    if not isinstance(trace, dict) or set(trace) != {"source_kind", "frame", "samples"}:
        raise ValueError("trace requires source_kind, frame, samples")
    if trace["source_kind"] not in ("synthetic_fixture", "simulation", "measured") or trace["frame"] != "world":
        raise ValueError("explicit source_kind and world frame required")
    samples = trace["samples"]
    if not isinstance(samples, list) or not 2 <= len(samples) <= 10000:
        raise ValueError("2..10000 samples required")
    outside, unknown, violations = [], [], []
    switches, last_t, last_contacts = 0, -math.inf, None
    max_roll, max_pitch, posture_count, joint_count = 0., 0., 0, 0
    for i, sample in enumerate(samples):
        allowed = {"t_s", "com_xy_m", "sole_polygons_xy_m", "contacts",
                   "torso_rpy_rad", "joint_positions_rad"}
        if not isinstance(sample, dict) or not {"t_s", "com_xy_m", "sole_polygons_xy_m", "contacts"} <= sample.keys() or not sample.keys() <= allowed:
            raise ValueError("invalid trace sample fields")
        t = _finite(sample["t_s"])
        if t <= last_t:
            raise ValueError("timestamps must increase")
        last_t = t
        com = _xy(sample["com_xy_m"])
        polygons, contacts = sample["sole_polygons_xy_m"], sample["contacts"]
        if not isinstance(polygons, dict) or set(polygons) != set(SIDES):
            raise ValueError("left/right sole polygons required")
        if not isinstance(contacts, list) or any(x not in SIDES for x in contacts) or len(set(contacts)) != len(contacts):
            raise ValueError("invalid contact list")
        current = frozenset(contacts)
        if last_contacts is not None and current != last_contacts:
            switches += 1
        last_contacts = current
        points = []
        for side in SIDES:
            vertices = polygons[side]
            if not isinstance(vertices, list) or len(vertices) > 128:
                raise ValueError("bounded sole vertices required")
            coords = [_xy(v) for v in vertices]
            if side in current:
                points.extend(coords)
        inside = _contains(points, com)
        if inside is None:
            unknown.append(i)
        elif not inside:
            outside.append(i)
        if "torso_rpy_rad" in sample:
            angles = sample["torso_rpy_rad"]
            if not isinstance(angles, list) or len(angles) != 3:
                raise ValueError("three torso angles required")
            roll, pitch, _ = (_finite(v) for v in angles)
            max_roll, max_pitch = max(max_roll, abs(roll)), max(max_pitch, abs(pitch))
            posture_count += 1
        if "joint_positions_rad" in sample:
            q = sample["joint_positions_rad"]
            if not isinstance(q, dict) or len(q) > 100 or any(name not in joint_limits for name in q):
                raise ValueError("only declared knee/ankle joints permitted")
            for name, val in q.items():
                val = _finite(val)
                lo, hi = joint_limits[name]
                if lo is not None and hi is not None and not lo-1e-9 <= val <= hi+1e-9:
                    violations.append({"sample_index": i, "joint": name,
                                       "value_rad": val, "declared_limits_rad": [lo, hi]})
            joint_count += 1
    return {
        "source_kind_declared": trace["source_kind"], "frame": "world",
        "sample_count": len(samples), "contact_transition_count": switches,
        "quasistatic_projection_status": "fail" if outside else "unknown" if unknown else "pass",
        "quasistatic_outside_indices": outside, "indeterminate_support_indices": unknown,
        "joint_limit_status": "fail" if violations else "pass" if joint_count else "unknown",
        "joint_limit_violations": violations,
        "max_abs_torso_roll_rad": max_roll if posture_count else None,
        "max_abs_torso_pitch_rad": max_pitch if posture_count else None,
        "posture_samples": posture_count, "joint_samples": joint_count,
        "gait_quality_status": "unknown", "dynamic_balance_status": "unknown",
        "caveat": "World-frame supplied polygons, not pressure/ZMP measurements. "
                  "COM outside a quasi-static support polygon does not prove a fall. "
                  "Caller-declared source labels are not verified; gait is unknown.",
    }


def _nominal_com(lm, parents, roots):
    """Mass-weighted URDF COM at q=0 in root frame, not a balance prediction."""
    if len(roots) != 1:
        return None
    identity = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))
    poses = {next(iter(roots)): ((0., 0., 0.), identity)}
    remaining = dict(parents)
    try:
        while remaining:
            progressed = False
            for child, (parent, joint) in list(remaining.items()):
                if parent not in poses:
                    continue
                xyz, rpy = _origin(joint)
                pos, rot = poses[parent]
                offset = _mv(rot, xyz)
                poses[child] = (tuple(pos[i]+offset[i] for i in range(3)), _mul(rot, _rpy(rpy)))
                del remaining[child]
                progressed = True
            if not progressed:
                return None
        weighted = [0., 0., 0.]
        total = 0.
        for name, link in lm.items():
            inertial = link.find("inertial")
            if inertial is None:
                continue
            mass_el = inertial.find("mass")
            m = _nums(mass_el.get("value"), 1) if mass_el is not None else None
            if m is None or m[0] <= 0:
                return None
            origin = inertial.find("origin")
            offset = _nums(origin.get("xyz", "0 0 0"), 3) if origin is not None else (0., 0., 0.)
            if offset is None:
                return None
            pos, rot = poses[name]
            com = _mv(rot, offset)
            for k in range(3):
                weighted[k] += m[0]*(pos[k]+com[k])
            total += m[0]
        if total <= 0 or not all(math.isfinite(x) for x in weighted):
            return None
        return {"root_frame": next(iter(roots)), "xyz_m": [x/total for x in weighted],
                "included_mass_kg": total, "joint_positions": "all_zero"}
    except (ValueError, KeyError, OverflowError):
        return None


def evaluate_humanoid_xml(xml: str, contact_trace=None) -> dict:
    """Read-only assessment of G1/H1 XML and optional caller-supplied trace."""
    if not isinstance(xml, str) or not 0 < len(xml.encode("utf-8")) <= 4*1024*1024:
        raise ValueError("bounded XML required")
    if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise ValueError("DTD/entities forbidden")
    try:
        robot = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError("invalid URDF XML") from exc
    if robot.tag != "robot":
        raise ValueError("robot root required")
    links, joints = robot.findall("link"), robot.findall("joint")
    link_names = [x.get("name") for x in links]
    joint_names = [x.get("name") for x in joints]
    lm = {x.get("name"): x for x in links}
    jm = {x.get("name"): x for x in joints}
    checks = []
    def record(rule, obj, status, observed=None, note=None):
        checks.append({"rule_id": rule, "object": obj, "status": status,
                       "observed": observed, "note": note})
    unique = bool(links) and all(link_names) and all(joint_names) and len(lm)==len(links) and len(jm)==len(joints)
    record("unique_names", "robot", "pass" if unique else "fail")
    parents = {}
    valid = bool(unique)
    for joint in joints:
        p, c = joint.find("parent"), joint.find("child")
        pn = p.get("link") if p is not None else None
        cn = c.get("link") if c is not None else None
        if pn not in lm or cn not in lm or pn == cn or cn in parents:
            valid = False
        else:
            parents[cn] = (pn, joint)
    roots = set(lm)-set(parents)
    if len(roots) != 1 or len(parents) != len(joints):
        valid = False
    if valid:
        for link in lm:
            seen, cur = set(), link
            while cur in parents and cur not in seen:
                seen.add(cur)
                cur = parents[cur][0]
            if cur in seen or cur not in roots:
                valid = False
    record("kinematic_tree", "robot", "pass" if valid else "fail",
           {"roots": sorted(str(x) for x in roots), "edges": len(parents)})
    profile = "g1" if "left_ankle_roll_joint" in jm else "h1" if "left_ankle_joint" in jm else None
    record("model_profile", "robot", "pass" if profile else "fail", profile,
           "Only G1-29DOF and H1-19DOF naming profiles")
    if profile is None:
        raise ValueError("unsupported humanoid joint names")
    expected_dof, leg_roles, foot_suffix = PROFILES[profile]
    active = [j for j in joints if j.get("type") in ("revolute", "continuous", "prismatic")]
    record("actuated_dof", "robot", "pass" if len(active)==expected_dof else "fail", len(active),
           "URDF DOF count is not controller action count")
    tracked_limits = {}
    for side in SIDES:
        names = [side+"_"+role+"_joint" for role in leg_roles]
        foot = side+"_"+foot_suffix
        if foot not in lm or any(n not in jm for n in names):
            record("leg_roles", side, "fail", {"expected_joints": names, "foot": foot})
            continue
        path, seen, cur = [], set(), foot
        while cur in parents and cur not in seen:
            seen.add(cur)
            pn, j = parents[cur]
            path.append(j)
            cur = pn
        path.reverse()
        moving = [j.get("name") for j in path if j.get("type") != "fixed"]
        record("leg_chain", side, "pass" if valid and moving == names and
               all(jm[n].get("type")=="revolute" for n in names) else "fail", moving)
        good, bad, unresolved, area = _foot_geometry(lm[foot])
        record("sole_collision", foot, "pass" if good and not bad else "fail",
               {"valid": good, "invalid": bad}, "Collision present, not contact fidelity")
        record("sole_xy_proxy", foot, "pass" if area>1e-5 else "unknown",
               {"area_m2": area, "unresolved_shapes": unresolved},
               "Local XY geometry proxy, not world support or pressure patch")
        for name in names:
            j = jm[name]
            ax = j.find("axis")
            axis = _nums(ax.get("xyz") if ax is not None else "1 0 0", 3)
            record("joint_axis", name, "pass" if axis is not None and math.hypot(*axis)>1e-9 else "fail", axis)
            limit = j.find("limit")
            lo = _nums(limit.get("lower"), 1) if limit is not None else None
            hi = _nums(limit.get("upper"), 1) if limit is not None else None
            ok = lo is not None and hi is not None and lo[0]<hi[0]
            record("joint_range", name, "pass" if ok else "fail",
                   [lo[0], hi[0]] if lo and hi else None, "rad")
            if "knee" in name or "ankle" in name:
                tracked_limits[name] = (lo[0] if lo else None, hi[0] if hi else None)
            for field in ("effort", "velocity"):
                v = _nums(limit.get(field), 1) if limit is not None else None
                record("urdf_"+field, name, "unknown" if v is None else "pass" if v[0]>0 else "fail",
                       v[0] if v else None, "Declared limit, not measured actuator capability")
    total_mass, mass_count, missing = 0., 0, []
    for name, link in lm.items():
        inertial = link.find("inertial")
        if inertial is None:
            missing.append(name)
            continue
        mass_node, tensor = inertial.find("mass"), inertial.find("inertia")
        m = _nums(mass_node.get("value"), 1) if mass_node is not None else None
        mass_ok = m is not None and m[0] > 0
        record("link_mass", name, "pass" if mass_ok else "fail", m[0] if m else None, "kg")
        if mass_ok:
            total_mass += m[0]
            mass_count += 1
        parts = [_nums(tensor.get(k), 1) if tensor is not None else None
                 for k in ("ixx", "ixy", "ixz", "iyy", "iyz", "izz")]
        if any(v is None for v in parts):
            record("link_inertia", name, "fail", None, "Missing inertia tensor component")
            continue
        a, b, c, d, e, f = (v[0] for v in parts)
        try:
            eig = symmetric_eigenvalues([[a, b, c], [b, d, e], [c, e, f]])
            tol = max(1e-10, max(abs(x) for x in eig)*1e-5)
            good = eig[0]>=-tol and eig[2]<=eig[0]+eig[1]+tol
        except (ValueError, OverflowError):
            eig, good = None, False
        record("link_inertia", name, "pass" if good else "fail", list(eig) if eig else None,
               "kg*m² principal moments, PSD and triangle inequality (rounding tolerance)")
    record("declared_mass_sum", "robot", "pass" if mass_count and math.isfinite(total_mass) else "fail",
           {"kg": total_mass, "inertial_links": mass_count, "missing_inertial_links": missing},
           "Declared URDF sum, not measured weight or MuJoCo fixed-root mass")
    nominal_com = _nominal_com(lm, parents, roots) if valid else None
    record("declared_com_nominal", "robot",
           "unknown" if nominal_com is None or missing else "pass", nominal_com,
           "Root-frame q=0 partial mass-weighted COM; missing inertial links remain unknown. "
           "No ground frame, pressure distribution or dynamic stability inferred")
    if missing:
        record("missing_inertial_tags", "robot", "unknown", missing,
               "Fixed sensor frames may omit inertia; missing mass is not zero")
    record("motor_calibration", "robot", "unknown", note="No torque-speed or thermal calibration")
    record("dynamic_balance_and_gait", "robot", "unknown", note="No verified force/COM/dynamics trajectory")
    analysis = evaluate_humanoid_trace(contact_trace, tracked_limits) if contact_trace is not None else None
    if analysis is not None:
        record("quasistatic_com_projection", "contact_trace", analysis["quasistatic_projection_status"],
               analysis["quasistatic_outside_indices"], "Geometric criterion, not fall prediction")
        record("declared_joint_limit_trace", "contact_trace", analysis["joint_limit_status"],
               analysis["joint_limit_violations"], "Knee/ankle against declared URDF bounds only")
        record("torso_posture_trace", "contact_trace",
               "pass" if analysis["posture_samples"] else "unknown",
               {"max_abs_roll_rad": analysis["max_abs_torso_roll_rad"],
                "max_abs_pitch_rad": analysis["max_abs_torso_pitch_rad"]},
               "Descriptive angles, no dynamic stability threshold")
    counts = {s: sum(x["status"]==s for x in checks) for s in ("pass", "fail", "unknown")}
    return {"rule_version": "1.0.0", "source_sha256": hashlib.sha256(xml.encode()).hexdigest(),
            "source_kind": "caller_supplied_urdf", "profile": profile,
            "checks": checks, "counts": counts, "contact_trace_analysis": analysis,
            "passed": counts["fail"]==0,
            "reason": "structural_findings" if counts["fail"] else "structural_checks_passed_with_unknowns",
            "caveat": "Not evidence of mass accuracy, contact pressure, stable gait or RL readiness"}
