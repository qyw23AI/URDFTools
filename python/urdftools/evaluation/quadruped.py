"""Conservative quadruped URDF checks; never infer motor calibration or gait."""
from __future__ import annotations
import hashlib
import math
import xml.etree.ElementTree as ET

LEGS = ("FL", "FR", "RL", "RR")
STAGES = ("hip", "thigh", "calf")


def _nums(raw, n):
    if raw is None:
        return None
    try:
        v = tuple(float(x) for x in raw.split())
    except (ValueError, OverflowError):
        return None
    return v if len(v) == n and all(math.isfinite(x) and abs(x) < 1e90 for x in v) else None


def _origin(joint):
    origin = joint.find("origin")
    if origin is None:
        return (0., 0., 0.), (0., 0., 0.)
    xyz = _nums(origin.get("xyz", "0 0 0"), 3)
    rpy = _nums(origin.get("rpy", "0 0 0"), 3)
    if xyz is None or rpy is None:
        raise ValueError("invalid joint origin")
    return xyz, rpy


def _mul(a, b):
    return tuple(tuple(sum(a[i][k]*b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def _mv(a, v):
    return tuple(sum(a[i][k]*v[k] for k in range(3)) for i in range(3))


def _rpy(v):
    r, p, y = v
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    return ((cy*cp, cy*sp*sr-sy*cr, cy*sp*cr+sy*sr),
            (sy*cp, sy*sp*sr+cy*cr, sy*sp*cr-cy*sr),
            (-sp, cp*sr, cp*cr))


def _axis_rotation(v, q):
    x, y, z = v
    c, t, si = math.cos(q), 1-math.cos(q), math.sin(q)
    return ((c+t*x*x, t*x*y-si*z, t*x*z+si*y),
            (t*y*x+si*z, c+t*y*y, t*y*z-si*x),
            (t*z*x-si*y, t*z*y+si*x, c+t*z*z))


def _area(points):
    pts = sorted(set(points))
    if len(pts) < 3:
        return 0.
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    lo, hi = [], []
    for pt in pts:
        while len(lo) > 1 and cross(lo[-2], lo[-1], pt) <= 0:
            lo.pop()
        lo.append(pt)
    for pt in reversed(pts):
        while len(hi) > 1 and cross(hi[-2], hi[-1], pt) <= 0:
            hi.pop()
        hi.append(pt)
    hull = lo[:-1]+hi[:-1]
    return abs(sum(hull[i][0]*hull[(i+1)%len(hull)][1] -
                   hull[(i+1)%len(hull)][0]*hull[i][1] for i in range(len(hull)))/2)


def evaluate_contact_trace(trace):
    """Geometric quasi-static COM test on supplied time-series; not a gait classifier."""
    if not isinstance(trace, dict) or set(trace) != {"source_kind", "frame", "samples"}:
        raise ValueError("contact trace needs source_kind, frame, samples")
    if trace["source_kind"] not in ("synthetic_fixture", "simulation", "measured") or trace["frame"] != "world":
        raise ValueError("explicit source_kind and world frame required")
    samples = trace["samples"]
    if not isinstance(samples, list) or not 2 <= len(samples) <= 10000:
        raise ValueError("bounded contact trace with at least two samples required")
    outside, insufficient, transitions = [], [], 0
    last_t, last_contacts = -math.inf, None
    for i, sample in enumerate(samples):
        if not isinstance(sample, dict) or set(sample) != {"t_s", "com_xy_m", "feet_xy_m", "contacts"}:
            raise ValueError("invalid trace sample fields")
        t = sample["t_s"]
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t <= last_t:
            raise ValueError("timestamps must strictly increase")
        last_t = t
        com = sample["com_xy_m"]
        feet = sample["feet_xy_m"]
        contacts = sample["contacts"]
        if not isinstance(com, list) or len(com)!=2 or _nums(" ".join(map(str, com)), 2) is None:
            raise ValueError("invalid COM xy")
        if not isinstance(feet, dict) or set(feet) != set(LEGS):
            raise ValueError("exactly four named foot positions required")
        for leg in LEGS:
            v = feet[leg]
            if not isinstance(v, list) or len(v)!=2 or _nums(" ".join(map(str, v)), 2) is None:
                raise ValueError("invalid foot xy")
        if not isinstance(contacts, list) or any(x not in LEGS for x in contacts) or len(set(contacts))!=len(contacts):
            raise ValueError("invalid contact set")
        current = frozenset(contacts)
        if last_contacts is not None and current != last_contacts:
            transitions += 1
        last_contacts = current
        if len(current)<3:
            insufficient.append(i)
            continue
        pts = sorted(set(tuple(feet[leg]) for leg in current))
        if len(pts)<3 or _area(pts)<1e-10:
            insufficient.append(i)
            continue
        # For a convex polygon, the point must lie on the same side of every edge.
        def cross(a,b,c):
            return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        hull = []
        for v in pts:
            while len(hull)>1 and cross(hull[-2],hull[-1],v)<=0:
                hull.pop()
            hull.append(v)
        upper=[]
        for v in reversed(pts):
            while len(upper)>1 and cross(upper[-2],upper[-1],v)<=0:
                upper.pop()
            upper.append(v)
        polygon = hull[:-1]+upper[:-1]
        if any(cross(polygon[j], polygon[(j+1)%len(polygon)], com)<-1e-10
               for j in range(len(polygon))):
            outside.append(i)
    return {"source_kind_declared": trace["source_kind"], "frame": "world",
            "sample_count": len(samples), "quasistatic_outside_indices": outside,
            "indeterminate_support_indices": insufficient, "contact_transition_count": transitions,
            "quasistatic_projection_status": "fail" if outside else
                ("unknown" if len(insufficient)==len(samples) else "pass"),
            "gait_quality_status": "unknown",
            "caveat": "Quasi-static geometric projection only; running can be dynamically stable outside polygon. "
                      "Source kind is caller-declared, not independently verified."}


def evaluate_quadruped_xml(xml: str, contact_trace=None) -> dict:
    """Only read supplied XML. 'passed' means no known structural failure, not RL readiness."""
    if not isinstance(xml, str) or not 0 < len(xml.encode("utf-8")) <= 4*1024*1024:
        raise ValueError("bounded XML string required")
    if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise ValueError("DTD/entities forbidden")
    robot = ET.fromstring(xml)
    if robot.tag != "robot":
        raise ValueError("expected robot root")
    links, joints = robot.findall("link"), robot.findall("joint")
    link_names, joint_names = [x.get("name") for x in links], [x.get("name") for x in joints]
    lm = {x.get("name"): x for x in links}
    jm = {x.get("name"): x for x in joints}
    checks = []
    def record(rule, obj, status, observed=None, note=None):
        checks.append(dict(rule_id=rule, object=obj, status=status, observed=observed, note=note))

    unique = all(link_names) and all(joint_names) and len(lm)==len(links) and len(jm)==len(joints)
    record("unique_names", "robot", "pass" if unique else "fail")
    parents = {}
    valid = True
    for j in joints:
        p, c = j.find("parent"), j.find("child")
        pn, cn = p.get("link") if p is not None else None, c.get("link") if c is not None else None
        if pn not in lm or cn not in lm or pn == cn or cn in parents:
            valid = False
        else:
            parents[cn] = (pn, j)
    roots = set(lm) - set(parents)
    if len(roots) != 1 or len(parents) != len(joints):
        valid = False
    if valid:
        for link in lm:
            visited, cur = set(), link
            while cur in parents and cur not in visited:
                visited.add(cur)
                cur = parents[cur][0]
            if cur in visited or cur not in roots:
                valid = False
    record("kinematic_tree", "robot", "pass" if valid else "fail",
           {"roots": sorted(str(x) for x in roots), "edges": len(parents)})
    active = [j for j in joints if j.get("type") in ("revolute", "continuous", "prismatic")]
    record("actuated_dof", "robot", "pass" if len(active)==12 else "fail", len(active),
           "Mimic and actuator coupling not established by URDF joint count")
    positions = {}
    for leg in LEGS:
        names = [f"{leg}_{part}_joint" for part in STAGES]
        foot_name = f"{leg}_foot"
        if any(n not in jm for n in names) or foot_name not in lm:
            record("leg_roles", leg, "fail", {"expected_joints": names, "foot": foot_name})
            continue
        path, visited, cur = [], set(), foot_name
        while cur in parents and cur not in visited:
            visited.add(cur)
            par, joint = parents[cur]
            path.append(joint)
            cur = par
        path.reverse()
        moving = [j.get("name") for j in path if j.get("type") != "fixed"]
        chain_ok = valid and moving == names and all(jm[n].get("type")=="revolute" for n in names)
        record("leg_chain", leg, "pass" if chain_ok else "fail", moving)
        collisions = lm[foot_name].findall("collision")
        contact = False
        for c in collisions:
            geo = c.find("geometry")
            if geo is None:
                continue
            for shape in geo:
                if shape.tag == "sphere":
                    v = _nums(shape.get("radius"), 1)
                    contact |= v is not None and v[0] > 0
                elif shape.tag == "box":
                    v = _nums(shape.get("size"), 3)
                    contact |= v is not None and all(x > 0 for x in v)
                elif shape.tag == "cylinder":
                    r, h = _nums(shape.get("radius"), 1), _nums(shape.get("length"), 1)
                    contact |= r is not None and h is not None and r[0] > 0 and h[0] > 0
                elif shape.tag == "mesh":
                    contact |= bool(shape.get("filename"))
        record("foot_collision", foot_name, "pass" if contact else "fail", len(collisions),
               "Geometry present, collision fidelity not measured")
        for n in names:
            j = jm[n]
            ax = j.find("axis")
            axis = _nums(ax.get("xyz") if ax is not None else "1 0 0", 3)
            record("joint_axis", n, "pass" if axis is not None and math.hypot(*axis)>1e-9 else "fail", axis)
            limit = j.find("limit")
            lo = _nums(limit.get("lower"), 1) if limit is not None else None
            hi = _nums(limit.get("upper"), 1) if limit is not None else None
            record("joint_range", n, "pass" if lo and hi and lo[0]<hi[0] else "fail",
                   [lo[0], hi[0]] if lo and hi else None, "rad")
            for field in ("effort", "velocity"):
                v = _nums(limit.get(field), 1) if limit is not None else None
                record("urdf_"+field, n, "unknown" if v is None else ("pass" if v[0]>0 else "fail"),
                       v[0] if v else None, "URDF limit only, not measured actuator curve")
        if chain_ok:
            try:
                pos = (0., 0., 0.)
                rot = ((1.,0.,0.),(0.,1.,0.),(0.,0.,1.))
                for j in path:
                    offset, rpy = _origin(j)
                    delta = _mv(rot, offset)
                    pos = tuple(pos[i]+delta[i] for i in range(3))
                    rot = _mul(rot, _rpy(rpy))
                    if j.get("type")=="revolute":
                        limit = j.find("limit")
                        lo = _nums(limit.get("lower"), 1) if limit is not None else None
                        hi = _nums(limit.get("upper"), 1) if limit is not None else None
                        q = (lo[0]+hi[0])/2 if lo and hi else 0.
                        axis_node = j.find("axis")
                        axis = _nums(axis_node.get("xyz") if axis_node is not None else "1 0 0", 3)
                        if axis is None or math.hypot(*axis)<1e-9:
                            raise ValueError("bad axis")
                        norm = math.hypot(*axis)
                        rot = _mul(rot, _axis_rotation(tuple(x/norm for x in axis), q))
                if not all(math.isfinite(x) for x in pos):
                    raise ValueError("bad FK")
                positions[leg] = [round(x, 8) for x in pos]
            except (ValueError, OverflowError):
                record("nominal_foot_fk", leg, "unknown", note="invalid or missing frame data")
    if len(positions)==4:
        area = _area([(v[0],v[1]) for v in positions.values()])
        record("nominal_foot_spread", "robot", "pass" if area>1e-5 else "fail",
               {"area_m2": area, "foot_xyz_m": positions},
               "Joint-limit midpoints; geometric spread only, NOT stability")
    else:
        record("nominal_foot_spread", "robot", "unknown")
    record("motor_calibration", "robot", "unknown", note="No motor torque-speed/thermal calibration supplied")
    record("dynamic_balance_and_gait", "robot", "unknown", note="Requires timed contacts, COM and dynamic trajectories")
    trace_report = evaluate_contact_trace(contact_trace) if contact_trace is not None else None
    if trace_report is not None:
        record("quasistatic_com_projection", "contact_trace", trace_report["quasistatic_projection_status"],
               trace_report["quasistatic_outside_indices"], "Geometry-only warning; dynamic stability not inferred")
    counts = {status: sum(x["status"]==status for x in checks) for status in ("pass","fail","unknown")}
    return {"rule_version": "1.0.0", "source_sha256": hashlib.sha256(xml.encode()).hexdigest(),
            "source_kind": "caller_supplied_urdf", "checks": checks, "counts": counts,
            "contact_trace_analysis": trace_report,
            "passed": counts["fail"]==0,
            "reason": "structural_findings" if counts["fail"] else "structural_checks_passed_with_unknowns",
            "caveat": "Not proof of safe gait, balance, motor capability or RL readiness"}
