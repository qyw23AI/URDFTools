"""C03 physical STEP to self-contained URDF/ROS package export.

This exporter never infers density or actuator limits. Its STL meshes are visual;
collision proxies are explicit bounding boxes and recorded as approximations.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path
import struct
import tempfile
from typing import Any, Mapping
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

from .mass_properties import aggregate_mass_properties, calculate_solid_mass_properties
from .step2urdf_adapter import load_step
from .wizard import inspect_conversion_draft, validate_configuration


class ExportError(ValueError):
    pass


def _number(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ExportError(f'{label} must be a finite positive number') from exc
    if not math.isfinite(result) or result <= 0:
        raise ExportError(f'{label} must be a finite positive number')
    return result


def _vec(values) -> str:
    return ' '.join(format(float(value), '.12g') for value in values)


def _binary_stl(vertices: np.ndarray, faces: np.ndarray, origin_m: np.ndarray) -> bytes:
    if len(faces) == 0 or len(vertices) == 0:
        raise ExportError('STEP part has no tessellated triangles')
    if len(faces) > 1_000_000:
        raise ExportError('STEP tessellation exceeds the triangle limit')
    points = vertices.astype(np.float64) / 1000.0 - origin_m
    if not np.isfinite(points).all() or np.any(faces < 0) or np.any(faces >= len(points)):
        raise ExportError('STEP tessellation contains invalid vertices or faces')
    stream = io.BytesIO()
    stream.write(b'URDFTools CAD visual mesh'.ljust(80, b'\0'))
    stream.write(struct.pack('<I', len(faces)))
    for face in faces:
        triangle = points[face]
        normal = np.cross(triangle[1]-triangle[0], triangle[2]-triangle[0])
        length = float(np.linalg.norm(normal))
        if not math.isfinite(length) or length <= 1e-15:
            raise ExportError('STEP tessellation contains a degenerate triangle')
        normal /= length
        stream.write(struct.pack('<12fH', *normal, *triangle.reshape(-1), 0))
    data = stream.getvalue()
    if len(data) > 64 * 1024 * 1024:
        raise ExportError('One exported STL exceeds the 64 MiB import limit')
    return data


def _link_origins(config: Mapping[str, Any]) -> dict[str, np.ndarray]:
    origins = {config['root']: np.zeros(3)}
    for joint in config['joints']:
        origins[joint['child']] = np.asarray(joint['origin_m'], dtype=float)
    return origins


def _valid_inertia(matrix: np.ndarray, name: str) -> None:
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise ExportError(f'{name}: inertia tensor is non-finite')
    values = np.linalg.eigvalsh((matrix + matrix.T) / 2)
    if np.min(values) <= 0:
        raise ExportError(f'{name}: inertia tensor is not positive definite')
    if max(values) > sum(values) - max(values) + max(values) * 1e-6:
        raise ExportError(f'{name}: inertia tensor violates triangle inequality')


def build_package_files(step: str | Path, config: Mapping[str, Any], densities_kg_m3: Mapping[str, Any]) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Build deterministic bytes in memory; caller writes ZIP or directory only on success."""
    draft = inspect_conversion_draft(step)
    validate_configuration(draft, config, require_confirmed=True)
    if not isinstance(densities_kg_m3, Mapping):
        raise ExportError('Explicit density is required for every CAD part')
    names = {part['name'] for part in draft['parts']}
    if set(densities_kg_m3) != names:
        raise ExportError('Explicit density assignment must cover every CAD part exactly')
    densities = {name: _number(densities_kg_m3[name], f'{name} density kg/m^3') for name in sorted(names)}
    for joint in config['joints']:
        if joint['type'] != 'fixed':
            _number(joint.get('effort'), f'{joint["name"]} effort')
            _number(joint.get('velocity'), f'{joint["name"]} velocity')
    parts = {part.name: part for part in load_step(str(step))}
    source_hash = hashlib.sha256()
    with Path(step).open('rb') as source_stream:
        for chunk in iter(lambda: source_stream.read(1024 * 1024), b''):
            source_hash.update(chunk)
    if source_hash.hexdigest() != draft['source_sha256']:
        raise ExportError('STEP source changed during export; retry from the new file')
    if set(parts) != names:
        raise ExportError('CAD part names changed during export')
    origins = _link_origins(config)
    robot = ET.Element('robot', name='urdftools_robot')
    robot.append(ET.Comment('Collision boxes are conservative visual-bounds proxies; inspect before simulation.'))
    files: dict[str, bytes] = {}
    link_summaries = []
    part_summaries = []
    for link in config['links']:
        name = link['name']
        link_el = ET.SubElement(robot, 'link', name=name)
        origin = origins[name]
        property_rows = []
        for part_name in link['parts']:
            part = parts[part_name]
            props = calculate_solid_mass_properties(part.shape, densities[part_name], name=part_name, approximate=bool(part.approximate))
            if props['status'] != 'known':
                raise ExportError(f'{part_name}: closed valid CAD solid required; {props["status"]}')
            local_props = dict(props)
            local_props['center_of_mass_m'] = (np.asarray(props['center_of_mass_m']) - origin).tolist()
            property_rows.append(local_props)
            vertices, faces = part.mesh()
            mesh_path = f'meshes/{part_name}.stl'
            if mesh_path in files:
                raise ExportError('Duplicate mesh path')
            files[mesh_path] = _binary_stl(vertices, faces, origin)
            visual = ET.SubElement(link_el, 'visual', name=part_name)
            ET.SubElement(visual, 'origin', xyz='0 0 0', rpy='0 0 0')
            ET.SubElement(ET.SubElement(visual, 'geometry'), 'mesh', filename=mesh_path)
            if part.color is not None:
                material = ET.SubElement(visual, 'material', name=f'{part_name}_color')
                ET.SubElement(material, 'color', rgba=_vec([*part.color, 1.0]))
            low = np.asarray(part.bbox_min, dtype=float) / 1000.0
            high = np.asarray(part.bbox_max, dtype=float) / 1000.0
            dimensions = high - low
            if np.any(dimensions <= 0) or not np.isfinite(dimensions).all():
                raise ExportError(f'{part_name}: invalid collision bounding box')
            collision = ET.SubElement(link_el, 'collision', name=f'{part_name}_proxy')
            ET.SubElement(collision, 'origin', xyz=_vec((low + high) / 2 - origin), rpy='0 0 0')
            ET.SubElement(ET.SubElement(collision, 'geometry'), 'box', size=_vec(dimensions))
            part_summaries.append({'name': part_name, 'link': name,
                'density_kg_m3': densities[part_name], 'mass_kg': props['mass_kg'],
                'center_of_mass_world_m': props['center_of_mass_m'],
                'visual_mesh': mesh_path, 'visual_mesh_sha256': hashlib.sha256(files[mesh_path]).hexdigest(),
                'collision': 'axis_aligned_world_bbox_proxy'})
        aggregate = aggregate_mass_properties(property_rows)
        if not aggregate['mass_complete']:
            raise ExportError(f'{name}: mass properties are incomplete')
        mass = aggregate['total_mass_kg']
        inertia = np.asarray(aggregate['inertia_about_total_com_kg_m2'], dtype=float)
        _valid_inertia(inertia, name)
        inertial = ET.SubElement(link_el, 'inertial')
        ET.SubElement(inertial, 'origin', xyz=_vec(aggregate['center_of_mass_m']), rpy='0 0 0')
        ET.SubElement(inertial, 'mass', value=format(mass, '.12g'))
        ET.SubElement(inertial, 'inertia', **{key: format(float(inertia[i, j]), '.12g') for key, i, j in
            [('ixx',0,0),('ixy',0,1),('ixz',0,2),('iyy',1,1),('iyz',1,2),('izz',2,2)]})
        link_summaries.append({'name': name, 'mass_kg': mass, 'center_of_mass_local_m': aggregate['center_of_mass_m'],
            'inertia_com_kg_m2': inertia.tolist(), 'parts': list(link['parts'])})
    for joint in config['joints']:
        element = ET.SubElement(robot, 'joint', name=joint['name'], type=joint['type'])
        ET.SubElement(element, 'parent', link=joint['parent'])
        ET.SubElement(element, 'child', link=joint['child'])
        xyz = origins[joint['child']] - origins[joint['parent']]
        ET.SubElement(element, 'origin', xyz=_vec(xyz), rpy='0 0 0')
        if joint['type'] != 'fixed':
            ET.SubElement(element, 'axis', xyz=_vec(joint['axis']))
            bounds = joint.get('limits')
            attrs = {'effort': format(_number(joint['effort'], 'effort'), '.12g'),
                     'velocity': format(_number(joint['velocity'], 'velocity'), '.12g')}
            if bounds is not None:
                attrs.update(lower=format(float(bounds[0]), '.12g'), upper=format(float(bounds[1]), '.12g'))
            ET.SubElement(element, 'limit', **attrs)
    files['robot.urdf'] = ET.tostring(robot, encoding='utf-8', xml_declaration=True) + b'\n'
    files['CMakeLists.txt'] = ('''cmake_minimum_required(VERSION 3.8)
project(urdftools_robot)
find_package(ament_cmake REQUIRED)
install(DIRECTORY meshes DESTINATION share/${PROJECT_NAME})
install(FILES robot.urdf metadata.json DESTINATION share/${PROJECT_NAME})
ament_package()
''').encode()
    files['package.xml'] = ('''<package format="3"><name>urdftools_robot</name><version>0.1.0</version><description>URDFTools exported robot</description><maintainer email="local@example.invalid">Local user</maintainer><license>UNSPECIFIED</license><buildtool_depend>ament_cmake</buildtool_depend></package>\n''').encode()
    metadata = {'schema_version': 1, 'source_sha256': draft['source_sha256'],
        'source_filename': draft['source_name'], 'configuration_sha256': hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest(),
        'source_length_unit': draft['source_length_unit'], 'units': 'SI',
        'status': 'exported_pending_independent_validation',
        'license_status': 'user_must_supply_model_license_before_distribution',
        'collision_geometry': 'axis-aligned bounding-box proxies; not CAD-exact',
        'links': link_summaries, 'parts': part_summaries,
        'total_mass_kg': sum(item['mass_kg'] for item in link_summaries),
        'joint_count': len(config['joints']),
        'warnings': ['Collision boxes can overestimate occupied volume.', 'STEP alone does not specify motor dynamics, friction or contact parameters.']}
    files['metadata.json'] = json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n'
    if any(len(data) > 64 * 1024 * 1024 for data in files.values()) or sum(map(len, files.values())) > 512 * 1024 * 1024:
        raise ExportError('Package exceeds importer size limits')
    return files, metadata


def write_package_zip(step: str | Path, config: Mapping[str, Any], densities_kg_m3: Mapping[str, Any], destination: str | Path) -> dict[str, Any]:
    files, metadata = build_package_files(step, config, densities_kg_m3)
    target = Path(destination)
    if target.suffix.lower() != '.zip':
        raise ExportError('Destination must end in .zip')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f'.{target.name}.', suffix='.partial', dir=target.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name in sorted(files):
                entry = zipfile.ZipInfo(f'urdftools_robot/{name}', date_time=(2020, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_STORED if name.endswith('.stl') else zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, files[name], compress_type=entry.compress_type, compresslevel=6)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return {'path': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        'metadata': metadata, 'files': sorted(files)}


def write_package_directory(step: str | Path, config: Mapping[str, Any], densities_kg_m3: Mapping[str, Any], destination: str | Path) -> dict[str, Any]:
    """Write the same self-contained package as a new directory without overwriting files."""
    import shutil
    files, metadata = build_package_files(step, config, densities_kg_m3)
    target = Path(destination)
    if target.exists():
        raise ExportError('Destination directory already exists; choose a new path')
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.urdftools-package-', dir=target.parent))
    try:
        for name, data in files.items():
            path = stage/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        stage.rename(target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(name.encode()+b'\0'+hashlib.sha256(files[name]).digest())
    return {'path': str(target), 'sha256': digest.hexdigest(),
            'metadata': metadata, 'files': sorted(files)}
