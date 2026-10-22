"""Human-confirmed STEP assembly to URDF preview configuration.

C02 preview geometry is bounding-box based and explicitly visual-only. C03 will
replace this with an exportable CAD/URDF package after physical validation.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
from typing import Any, Mapping
import xml.etree.ElementTree as ET

from .step2urdf_adapter import load_step
from .step_reader import inspect_step


class WizardError(ValueError):
    pass


def _finite_vector(values: Any, label: str, *, unit: bool = False) -> list[float]:
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise WizardError(f"{label} must contain exactly three numbers")
    try:
        result = [float(v) for v in values]
    except (TypeError, ValueError) as exc:
        raise WizardError(f"{label} must be numeric") from exc
    if not all(math.isfinite(v) for v in result):
        raise WizardError(f"{label} must be finite")
    if unit:
        norm = math.sqrt(sum(v * v for v in result))
        if not 0.999 <= norm <= 1.001:
            raise WizardError(f"{label} must be a unit vector")
    return result


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value):
        raise WizardError(f"{label} must be a valid URDF identifier")
    return value


def inspect_conversion_draft(source: str | Path) -> dict[str, Any]:
    """Read a real STEP file and expose reviewable parts and geometric axis hints."""
    path = Path(source).expanduser()
    if path.suffix.lower() not in {'.step', '.stp'} or not path.is_file():
        raise WizardError('Choose an existing STEP/STP file')
    inspected = inspect_step(path)
    if inspected['units']['unit_status'] != 'recognized':
        raise WizardError('STEP length unit is ambiguous; confirm and normalize units before conversion')
    if inspected['adapter']['status'] != 'matched':
        raise WizardError('STEP assembly and CAD part adapter disagree; manual reconciliation is required')
    digest = inspected['source']['sha256']
    parts = []
    for part in load_step(str(path)):
        low = [float(v) / 1000 for v in part.bbox_min]
        high = [float(v) / 1000 for v in part.bbox_max]
        hints = []
        for cylinder in part.cylinders:
            axis = _finite_vector([float(v) for v in cylinder.direction], 'cylinder axis', unit=True)
            hints.append({'axis': axis,
                          'point_m': [float(v) / 1000 for v in cylinder.point],
                          'radius_m': float(cylinder.radius) / 1000,
                          'surface_area_m2': float(cylinder.area) / 1_000_000,
                          'evidence': 'cylindrical_face', 'confirmed': False})
        parts.append({'name': part.name, 'bounds_min_m': low, 'bounds_max_m': high,
                      'center_m': [(a+b)/2 for a, b in zip(low, high)],
                      'axis_hints': hints, 'geometry_approximate': bool(part.approximate)})
    if not parts:
        raise WizardError('STEP file has no usable parts')
    return {'schema_version': 1, 'source_sha256': digest, 'source_name': path.name,
            'source_length_unit': inspected['units']['source_length_unit'], 'parts': parts, 'warning': 'Axis hints are geometric candidates, never confirmed joints.'}


def default_configuration(draft: Mapping[str, Any]) -> dict[str, Any]:
    """Create editable groups and an unconfirmed parent-child suggestion."""
    parts = draft['parts']
    links = [{'name': item['name'], 'parts': [item['name']]} for item in parts]
    root = links[0]['name']
    joints = []
    for index, item in enumerate(parts[1:], 1):
        parent = links[index-1]['name']
        hint = item['axis_hints'][0] if item['axis_hints'] else None
        joints.append({'name': f'{item["name"]}_joint', 'parent': parent,
                       'child': item['name'], 'type': 'fixed',
                       'axis': hint['axis'] if hint else [0.0, 0.0, 1.0],
                       'origin_m': hint['point_m'] if hint else item['center_m'],
                       'limits': None, 'confirmed': False,
                       'candidate_evidence': hint['evidence'] if hint else 'none'})
    return {'schema_version': 1, 'source_sha256': draft['source_sha256'],
            'root': root, 'links': links, 'joints': joints}


def validate_configuration(draft: Mapping[str, Any], config: Mapping[str, Any], *, require_confirmed: bool = False) -> dict[str, Any]:
    """Validate exact part coverage, a single rooted tree and explicit joint choices."""
    if config.get('schema_version') != 1 or config.get('source_sha256') != draft.get('source_sha256'):
        raise WizardError('Configuration does not match this STEP source')
    source_parts = {p['name'] for p in draft['parts']}
    if len(source_parts) != len(draft['parts']):
        raise WizardError('STEP part names are not unique')
    links = config.get('links')
    if not isinstance(links, list) or not links:
        raise WizardError('At least one link is required')
    if any(not isinstance(link, Mapping) for link in links):
        raise WizardError('Each link must be an object')
    names = [_identifier(link.get('name'), 'link name') for link in links]
    if len(set(names)) != len(names):
        raise WizardError('Link names must be unique')
    covered = []
    for link in links:
        group = link.get('parts')
        if not isinstance(group, list) or not group:
            raise WizardError('Every link must contain at least one CAD part')
        covered.extend(group)
    if len(covered) != len(set(covered)) or set(covered) != source_parts:
        raise WizardError('Every CAD part must appear in exactly one link')
    root = config.get('root')
    if root not in names:
        raise WizardError('Root link is missing')
    joints = config.get('joints')
    if not isinstance(joints, list) or len(joints) != len(names)-1:
        raise WizardError('A tree requires exactly one joint per non-root link')
    seen_children = set()
    seen_joint_names = set()
    for joint in joints:
        if not isinstance(joint, Mapping):
            raise WizardError('Each joint must be an object')
        jname = _identifier(joint.get('name'), 'joint name')
        if jname in seen_joint_names or jname in names:
            raise WizardError('Joint names must be unique and distinct from links')
        seen_joint_names.add(jname)
        parent, child = joint.get('parent'), joint.get('child')
        if parent not in names or child not in names or child == root or child in seen_children or parent == child:
            raise WizardError('Invalid or repeated parent/child joint relationship')
        seen_children.add(child)
        kind = joint.get('type')
        if kind not in {'fixed', 'revolute', 'prismatic', 'continuous'}:
            raise WizardError('Unsupported joint type')
        _finite_vector(joint.get('origin_m'), 'joint origin')
        _finite_vector(joint.get('axis'), 'joint axis', unit=True)
        limits = joint.get('limits')
        if kind in {'revolute', 'prismatic'}:
            if not isinstance(limits, (list, tuple)) or len(limits) != 2:
                raise WizardError('Movable joint requires lower and upper limits')
            try:
                lower, upper = float(limits[0]), float(limits[1])
            except (TypeError, ValueError, OverflowError) as exc:
                raise WizardError('Joint limits must be numeric') from exc
            if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
                raise WizardError('Joint limits must be finite and ordered')
        elif limits is not None:
            raise WizardError('Fixed and continuous joints must not have position limits')
        if not isinstance(joint.get('confirmed'), bool):
            raise WizardError('Joint confirmation must be boolean')
        if require_confirmed and not joint['confirmed']:
            raise WizardError(f'Joint {jname} still needs human confirmation')
    if seen_children != set(names)-{root}:
        raise WizardError('Every non-root link must have one parent')
    children = {name: [] for name in names}
    for joint in joints:
        children[joint['parent']].append(joint['child'])
    visited = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if node in visited:
            raise WizardError('Joint tree contains a cycle')
        visited.add(node)
        stack.extend(children[node])
    if visited != set(names):
        raise WizardError('Joint tree is disconnected')
    return {'link_count': len(names), 'joint_count': len(joints),
            'unconfirmed_joints': [j['name'] for j in joints if not j['confirmed']]}


def canonical_configuration(config: Mapping[str, Any]) -> str:
    return json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def preview_urdf(draft: Mapping[str, Any], config: Mapping[str, Any]) -> str:
    """Render deterministic visual-only boxes for live preview, never a final export."""
    validate_configuration(draft, config, require_confirmed=True)
    part_map = {part['name']: part for part in draft['parts']}
    root = config['root']
    link_origins = {root: [0.0, 0.0, 0.0]}
    for joint in config['joints']:
        link_origins[joint['child']] = _finite_vector(joint['origin_m'], 'joint origin')
    robot = ET.Element('robot', name='cad_preview')
    robot.append(ET.Comment('Visual-only bounding-box preview; not a physical CAD-to-URDF export.'))
    def vector(values):
        return ' '.join(format(float(value), '.12g') for value in values)
    for link in config['links']:
        link_el = ET.SubElement(robot, 'link', name=link['name'])
        origin = link_origins[link['name']]
        for part_name in link['parts']:
            part = part_map[part_name]
            size = [max(1e-6, hi-lo) for lo, hi in zip(part['bounds_min_m'], part['bounds_max_m'])]
            offset = [center-base for center, base in zip(part['center_m'], origin)]
            visual = ET.SubElement(link_el, 'visual', name=part_name)
            ET.SubElement(visual, 'origin', xyz=vector(offset), rpy='0 0 0')
            geometry = ET.SubElement(visual, 'geometry')
            ET.SubElement(geometry, 'box', size=vector(size))
    for joint in config['joints']:
        child = joint['child']
        parent = joint['parent']
        element = ET.SubElement(robot, 'joint', name=joint['name'], type=joint['type'])
        xyz = [a-b for a, b in zip(link_origins[child], link_origins[parent])]
        ET.SubElement(element, 'origin', xyz=vector(xyz), rpy='0 0 0')
        ET.SubElement(element, 'parent', link=parent)
        ET.SubElement(element, 'child', link=child)
        if joint['type'] != 'fixed':
            ET.SubElement(element, 'axis', xyz=vector(joint['axis']))
        if joint['type'] in {'revolute', 'prismatic'}:
            ET.SubElement(element, 'limit', lower=format(float(joint['limits'][0]), '.12g'),
                          upper=format(float(joint['limits'][1]), '.12g'), effort='1', velocity='1')
    return ET.tostring(robot, encoding='unicode', short_empty_elements=True) + '\n'
