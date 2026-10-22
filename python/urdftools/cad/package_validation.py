"""Independent URDF ZIP validation with optional MuJoCo compilation.

This module deliberately does not import the CAD exporter or OCP. It parses the
written package anew and compares URDF kinematics and mass to exported metadata.
"""
from __future__ import annotations

import hashlib
import json
import math
import stat
from pathlib import Path, PurePosixPath
import tempfile
import xml.etree.ElementTree as ET
import zipfile

import numpy as np


class PackageValidationError(ValueError):
    pass


def _vector(raw: str | None, length: int, label: str) -> np.ndarray:
    if raw is None:
        raise PackageValidationError(f'{label} is missing')
    try:
        values = np.array([float(value) for value in raw.split()], dtype=float)
    except ValueError as exc:
        raise PackageValidationError(f'{label} is not numeric') from exc
    if values.shape != (length,) or not np.isfinite(values).all():
        raise PackageValidationError(f'{label} must contain {length} finite values')
    return values


def _rpy_matrix(rpy: np.ndarray) -> np.ndarray:
    roll, pitch, yaw = rpy
    cx, sx = math.cos(roll), math.sin(roll)
    cy, sy = math.cos(pitch), math.sin(pitch)
    cz, sz = math.cos(yaw), math.sin(yaw)
    return np.array([[cz*cy, cz*sy*sx-sz*cx, cz*sy*cx+sz*sx],
                     [sz*cy, sz*sy*sx+cz*cx, sz*sy*cx-cz*sx],
                     [-sy, cy*sx, cy*cx]])


def _origin(element: ET.Element | None) -> tuple[np.ndarray, np.ndarray]:
    if element is None:
        return np.zeros(3), np.eye(3)
    return _vector(element.get('xyz', '0 0 0'), 3, 'origin xyz'), _rpy_matrix(_vector(element.get('rpy', '0 0 0'), 3, 'origin rpy'))


def _near(a, b, label: str, *, atol: float = 1e-8, rtol: float = 1e-6) -> None:
    if not np.allclose(a, b, atol=atol, rtol=rtol):
        raise PackageValidationError(f'{label} mismatch: {a} != {b}')


def validate_package_zip(path: str | Path) -> dict:
    """Read files, recompute zero-pose FK/COM, then compile fixed and floating MuJoCo variants."""
    import mujoco
    archive_path = Path(path)
    with tempfile.TemporaryDirectory(prefix='urdftools-c03-validate-') as directory:
        root = Path(directory)
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if len(members) > 10000 or not members:
                raise PackageValidationError('ZIP member count invalid')
            seen = set()
            total = 0
            for member in members:
                name = PurePosixPath(member.filename)
                if (name.is_absolute() or '..' in name.parts or name.parts[0] != 'urdftools_robot'
                    or '\\' in member.filename or ':' in member.filename or member.filename in seen):
                    raise PackageValidationError('Unsafe or duplicate ZIP path')
                seen.add(member.filename)
                mode = stat.S_IFMT(member.external_attr >> 16)
                if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise PackageValidationError('ZIP links and special files are forbidden')
                if member.file_size > max(1, member.compress_size) * 200:
                    raise PackageValidationError('ZIP compression ratio exceeds import limit')
                total += member.file_size
                if member.file_size > 64*1024*1024 or total > 512*1024*1024:
                    raise PackageValidationError('ZIP member exceeds import limit')
            archive.extractall(root)
        package = root/'urdftools_robot'
        meta = json.loads((package/'metadata.json').read_text())
        tree = ET.parse(package/'robot.urdf')
        robot = tree.getroot()
        if robot.tag != 'robot':
            raise PackageValidationError('URDF root is missing')
        links = {item.get('name'): item for item in robot.findall('link')}
        if len(links) != len(robot.findall('link')) or set(links) != {item['name'] for item in meta['links']}:
            raise PackageValidationError('URDF link inventory differs from metadata')
        for part in meta['parts']:
            mesh = package/part['visual_mesh']
            if not mesh.is_file() or hashlib.sha256(mesh.read_bytes()).hexdigest() != part['visual_mesh_sha256']:
                raise PackageValidationError(f'{part["name"]}: mesh missing or changed')
        expected_mass = float(meta['total_mass_kg'])
        parsed_mass = 0.0
        link_inertial = {}
        for name, link in links.items():
            inertial = link.find('inertial')
            if inertial is None or inertial.find('mass') is None or inertial.find('inertia') is None:
                raise PackageValidationError(f'{name}: inertial record missing')
            mass = float(inertial.find('mass').get('value'))
            if not math.isfinite(mass) or mass <= 0:
                raise PackageValidationError(f'{name}: mass invalid')
            tensor = inertial.find('inertia')
            ixx, ixy, ixz, iyy, iyz, izz = [float(tensor.get(key)) for key in ('ixx','ixy','ixz','iyy','iyz','izz')]
            matrix = np.array([[ixx,ixy,ixz],[ixy,iyy,iyz],[ixz,iyz,izz]])
            if not np.isfinite(matrix).all() or np.min(np.linalg.eigvalsh(matrix)) <= 0:
                raise PackageValidationError(f'{name}: inertia invalid')
            com, rotation = _origin(inertial.find('origin'))
            link_inertial[name] = (mass, com, rotation)
            parsed_mass += mass
        _near(parsed_mass, expected_mass, 'total URDF mass')
        for item in meta['links']:
            mass, com, _ = link_inertial[item['name']]
            _near(mass, item['mass_kg'], f'{item["name"]} mass')
            _near(com, item['center_of_mass_local_m'], f'{item["name"]} COM')
        joints = robot.findall('joint')
        if len(joints) != meta['joint_count']:
            raise PackageValidationError('Joint count differs from metadata')
        by_parent: dict[str, list[tuple[str,np.ndarray,np.ndarray]]] = {name: [] for name in links}
        children = set()
        movable = 0
        for joint in joints:
            parent_node, child_node = joint.find('parent'), joint.find('child')
            if parent_node is None or child_node is None:
                raise PackageValidationError('Joint parent or child missing')
            parent, child = parent_node.get('link'), child_node.get('link')
            if parent not in links or child not in links or child in children:
                raise PackageValidationError('Joint tree invalid')
            children.add(child)
            translation, rotation = _origin(joint.find('origin'))
            by_parent[parent].append((child, translation, rotation))
            if joint.get('type') != 'fixed':
                movable += 1
                axis = _vector(joint.find('axis').get('xyz') if joint.find('axis') is not None else None, 3, 'joint axis')
                _near(np.linalg.norm(axis), 1.0, 'joint axis norm', atol=1e-3)
        roots = set(links)-children
        if len(roots) != 1:
            raise PackageValidationError('URDF has no unique root')
        root_name = next(iter(roots))
        pose = {root_name: (np.zeros(3), np.eye(3))}
        queue = [root_name]
        while queue:
            parent = queue.pop(0)
            parent_pos, parent_rot = pose[parent]
            for child, translation, rotation in by_parent[parent]:
                if child in pose:
                    raise PackageValidationError('URDF joint cycle')
                pose[child] = (parent_pos + parent_rot@translation, parent_rot@rotation)
                queue.append(child)
        if len(pose) != len(links):
            raise PackageValidationError('URDF joint tree disconnected')
        world_com = sum((link_inertial[name][0] * (pose[name][0] + pose[name][1]@link_inertial[name][1])
                         for name in links), np.zeros(3))/parsed_mass
        part_com = sum((float(item['mass_kg'])*np.asarray(item['center_of_mass_world_m'])
                        for item in meta['parts']), np.zeros(3))/expected_mass
        _near(world_com, part_com, 'zero-pose world COM')
        urdf_path = package/'robot.urdf'
        raw = mujoco.MjModel.from_xml_path(str(urdf_path))
        spec = mujoco.MjSpec.from_file(str(urdf_path))
        base = spec.worldbody.first_body()
        if base is None or base.name != root_name:
            raise PackageValidationError('MuJoCo root body does not match URDF root')
        base.add_freejoint()
        floating = spec.compile()
        floating_mass = float(np.sum(floating.body_mass))
        _near(floating_mass, expected_mass, 'floating MuJoCo mass')
        if floating.njnt != movable+1:
            raise PackageValidationError('MuJoCo joint count changed during compilation')
        data = mujoco.MjData(floating)
        mujoco.mj_forward(floating, data)
        mujoco_com = sum((float(floating.body_mass[i])*data.xipos[i] for i in range(1,floating.nbody)), np.zeros(3))/floating_mass
        _near(mujoco_com, part_com, 'floating MuJoCo zero-pose COM', atol=1e-6)
        return {'status': 'passed', 'mujoco_version': mujoco.__version__,
                'link_count': len(links), 'joint_count': len(joints), 'movable_joint_count': movable,
                'mesh_count': len(meta['parts']), 'urdf_mass_kg': parsed_mass,
                'zero_pose_com_m': world_com.tolist(),
                'mujoco_raw': {'compiled': True, 'body_count': raw.nbody, 'joint_count': raw.njnt,
                               'dynamic_mass_kg': float(np.sum(raw.body_mass)),
                               'fixed_base_mass_excluded_kg': expected_mass - float(np.sum(raw.body_mass))},
                'mujoco_floating': {'compiled': True, 'body_count': floating.nbody,
                    'joint_count': floating.njnt, 'mass_kg': floating_mass,
                    'zero_pose_com_m': mujoco_com.tolist(), 'injected_freejoint': True},
                'training_ready': False,
                'remaining': ['collision proxies and contact/friction not validated against hardware',
                              'motor/control model not specified',
                              'raw URDF is fixed-base in MuJoCo; floating base requires explicit freejoint']}
