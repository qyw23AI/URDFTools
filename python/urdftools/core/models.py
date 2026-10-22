"""Versioned, immutable SI domain contracts (not a URDF import adapter)."""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import PurePosixPath
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

Finite = Annotated[float, Field(allow_inf_nan=False, strict=True)]
Hash = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Name = Annotated[str, Field(min_length=1)]
Unit = Literal['m', 'rad', 'kg', 'kg*m^2', 'm/s', 'rad/s', 'N', 'N*m', '1', 's', 'N*s/m', 'N*m*s/rad']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, revalidate_instances='always')


class Provenance(Contract):
    source_kind: Literal['measured', 'cad', 'vendor', 'inferred', 'default', 'unknown']
    source_ref: str | None
    version: str | None
    recorded_at: datetime
    assumptions: tuple[str, ...] = ()

    @field_validator('recorded_at')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError('timestamp must include timezone')
        return value


class ParameterEvidence(Contract):
    value: Finite | None
    unit: Unit
    provenance: Provenance
    uncertainty: tuple[Finite, Finite] | None = None

    @model_validator(mode='after')
    def evidence(self):
        if (self.value is None) != (self.provenance.source_kind == 'unknown'):
            raise ValueError('unknown requires null; known values require an explicit source')
        if self.uncertainty is not None:
            lo, hi = self.uncertainty
            if self.value is None or not lo <= self.value <= hi:
                raise ValueError('uncertainty must bound a known value')
        return self


def require_units(values, unit):
    if any(p.unit != unit for p in values):
        raise ValueError(f'expected SI unit {unit}')


Vector = tuple[ParameterEvidence, ParameterEvidence, ParameterEvidence]


class Transform(Contract):
    """Right handed; URDF fixed-axis roll/pitch/yaw in radians."""
    relative_to: UUID
    xyz: Vector
    rpy: Vector

    @model_validator(mode='after')
    def units(self):
        require_units(self.xyz, 'm')
        require_units(self.rpy, 'rad')
        return self


class Inertial(Contract):
    mass: ParameterEvidence
    origin: Transform  # COM position and tensor orientation, relative to link
    tensor: tuple[ParameterEvidence, ParameterEvidence, ParameterEvidence,
                  ParameterEvidence, ParameterEvidence, ParameterEvidence]  # xx,xy,xz,yy,yz,zz

    @model_validator(mode='after')
    def units(self):
        require_units((self.mass,), 'kg')
        require_units(self.tensor, 'kg*m^2')
        if self.mass.value is not None and self.mass.value < 0:
            raise ValueError('negative mass')
        return self


class AssetRef(Contract):
    id: UUID
    sha256: Hash
    relative_path: str
    mime: Name
    size: Annotated[int, Field(ge=0, strict=True)]
    source_url: str | None
    source_commit: str | None
    license_id: str | None

    @field_validator('relative_path')
    @classmethod
    def relative(cls, value):
        path = PurePosixPath(value)
        if not value or path.is_absolute() or '..' in path.parts or '\\' in value or ':' in value or '\x00' in value or str(path) != value or value == '.':
            raise ValueError('asset path must be a normalized project-relative POSIX path')
        return value


class Material(Contract):
    id: UUID
    name: Name
    rgba: tuple[Finite, Finite, Finite, Finite] | None
    provenance: Provenance

    @field_validator('rgba')
    @classmethod
    def color(cls, value):
        if value is not None and any(not 0 <= x <= 1 for x in value):
            raise ValueError('RGBA outside [0,1]')
        return value


class Geometry(Contract):
    id: UUID
    kind: Literal['box', 'sphere', 'cylinder', 'mesh']
    origin: Transform
    dimensions: tuple[ParameterEvidence, ...]  # box xyz; sphere r; cylinder r,length
    asset_id: UUID | None
    scale: tuple[Finite, Finite, Finite] | None
    material_id: UUID | None
    provenance: Provenance

    @model_validator(mode='after')
    def shape(self):
        require_units(self.dimensions, 'm')
        if len(self.dimensions) != {'box': 3, 'sphere': 1, 'cylinder': 2, 'mesh': 0}[self.kind]:
            raise ValueError('wrong primitive dimensions')
        if any(p.value is not None and p.value <= 0 for p in self.dimensions):
            raise ValueError('dimensions must be positive or unknown')
        if self.kind == 'mesh':
            if self.asset_id is None or self.scale is None or any(x <= 0 for x in self.scale):
                raise ValueError('mesh requires asset and explicit positive scale; negative scale unsupported')
        elif self.asset_id is not None or self.scale is not None:
            raise ValueError('primitive cannot reference mesh')
        return self


class Link(Contract):
    id: UUID
    name: Name
    visual: tuple[Geometry, ...] = ()
    collision: tuple[Geometry, ...] = ()
    inertial: Inertial | None
    cad_part_ids: tuple[UUID, ...] = ()
    source_assembly_path: str | None = None
    provenance: Provenance

    @model_validator(mode='after')
    def frames(self):
        frames = [g.origin for g in (*self.visual, *self.collision)]
        if self.inertial:
            frames.append(self.inertial.origin)
        if any(f.relative_to != self.id for f in frames):
            raise ValueError('geometry/inertial frame must reference its link')
        return self


class JointLimits(Contract):
    lower: ParameterEvidence
    upper: ParameterEvidence
    effort: ParameterEvidence
    velocity: ParameterEvidence


class JointDynamics(Contract):
    damping: ParameterEvidence
    friction: ParameterEvidence


class Mimic(Contract):
    joint_id: UUID
    multiplier: ParameterEvidence
    offset: ParameterEvidence


class Joint(Contract):
    id: UUID
    name: Name
    type: Literal['fixed', 'revolute', 'continuous', 'prismatic', 'floating', 'planar']
    parent_id: UUID
    child_id: UUID
    origin: Transform  # parent -> joint; axis expressed in joint frame
    axis: Vector | None
    limits: JointLimits | None
    dynamics: JointDynamics | None
    mimic: Mimic | None
    provenance: Provenance

    @model_validator(mode='after')
    def semantics(self):
        if self.parent_id == self.child_id or self.origin.relative_to != self.parent_id:
            raise ValueError('invalid joint parent/frame')
        moving = self.type in ('revolute', 'continuous', 'prismatic', 'planar')
        if moving != (self.axis is not None):
            raise ValueError('moving joint requires explicit axis; fixed/floating has none')
        if self.axis is not None:
            require_units(self.axis, '1')
            if all(p.value is not None for p in self.axis):
                if not math.isclose(math.hypot(*(p.value for p in self.axis)), 1.0, abs_tol=1e-9):
                    raise ValueError('axis must be unit length')
        angular = self.type != 'prismatic'
        if self.limits:
            require_units((self.limits.lower, self.limits.upper), 'rad' if angular else 'm')
            require_units((self.limits.velocity,), 'rad/s' if angular else 'm/s')
            require_units((self.limits.effort,), 'N*m' if angular else 'N')
            lo, hi = self.limits.lower.value, self.limits.upper.value
            if lo is not None and hi is not None and lo > hi:
                raise ValueError('reversed joint limits')
            if any(p.value is not None and p.value < 0 for p in (self.limits.effort, self.limits.velocity)):
                raise ValueError('negative effort/velocity limit')
        if self.dynamics:
            require_units((self.dynamics.damping,), 'N*m*s/rad' if angular else 'N*s/m')
            require_units((self.dynamics.friction,), 'N*m' if angular else 'N')
        if self.mimic:
            require_units((self.mimic.multiplier,), '1')
            require_units((self.mimic.offset,), 'rad' if angular else 'm')
        return self


class Extension(Contract):
    namespace: Name
    payload: str  # opaque source XML/text; never executed
    source_asset_id: UUID | None
    source_span: tuple[Annotated[int, Field(ge=0)], Annotated[int, Field(ge=0)]] | None

    @model_validator(mode='after')
    def span(self):
        if self.source_span and self.source_span[0] > self.source_span[1]:
            raise ValueError('reversed source span')
        return self


class RobotDocument(Contract):
    schema_version: Literal[2]
    id: UUID
    name: Name
    units: Literal['SI']
    handedness: Literal['right']
    up_axis: Literal['Z']
    origin: Literal['user_upload', 'public_import', 'synthetic_fixture']
    links: tuple[Link, ...]
    joints: tuple[Joint, ...]
    materials: tuple[Material, ...] = ()
    assets: tuple[AssetRef, ...] = ()
    extensions: tuple[Extension, ...] = ()
    provenance: Provenance

    @model_validator(mode='after')
    def graph(self):
        entities = [self, *self.links, *self.joints, *self.materials, *self.assets,
                    *(g for link in self.links for g in (*link.visual, *link.collision))]
        ids = [e.id for e in entities]
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate UUID')
        for group in (self.links, self.joints, self.materials):
            if len({e.name for e in group}) != len(group):
                raise ValueError('duplicate name')
        links = {e.id for e in self.links}
        parents = {}
        children = {i: [] for i in links}
        for joint in self.joints:
            if joint.parent_id not in links or joint.child_id not in links or joint.child_id in parents:
                raise ValueError('dangling reference or multiple parents')
            parents[joint.child_id] = joint.parent_id
            children[joint.parent_id].append(joint.child_id)
        roots = links - parents.keys()
        if len(roots) != 1:
            raise ValueError('robot must have exactly one root')
        visited, stack = set(), list(roots)
        while stack:
            node = stack.pop()
            if node in visited:
                raise ValueError('cycle')
            visited.add(node)
            stack.extend(children[node])
        if visited != links:
            raise ValueError('disconnected graph or cycle; closed chains unsupported')
        joints = {j.id: j for j in self.joints}
        for joint in self.joints:
            seen, cursor = set(), joint
            while cursor.mimic:
                if cursor.id in seen or cursor.mimic.joint_id not in joints:
                    raise ValueError('mimic cycle or dangling reference')
                seen.add(cursor.id)
                target = joints[cursor.mimic.joint_id]
                if cursor.type not in ('revolute', 'continuous', 'prismatic') or target.type not in ('revolute', 'continuous', 'prismatic') or (cursor.type == 'prismatic') != (target.type == 'prismatic'):
                    raise ValueError('incompatible mimic joints')
                cursor = target
        assets, materials = {a.id for a in self.assets}, {m.id for m in self.materials}
        if len({a.relative_path for a in self.assets}) != len(self.assets):
            raise ValueError('duplicate asset path')
        for link in self.links:
            for geometry in (*link.visual, *link.collision):
                if geometry.asset_id is not None and geometry.asset_id not in assets:
                    raise ValueError('dangling asset')
                if geometry.material_id is not None and geometry.material_id not in materials:
                    raise ValueError('dangling material')
        if any(e.source_asset_id is not None and e.source_asset_id not in assets for e in self.extensions):
            raise ValueError('dangling extension source')
        return self


def document_digest(document):
    import hashlib
    import json
    encoded = json.dumps(document.model_dump(mode='json'), sort_keys=True,
                         separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


class RobotSnapshot(Contract):
    id: UUID
    content_hash: Hash
    parent_id: UUID | None
    document: RobotDocument
    created_at: datetime

    @field_validator('created_at')
    @classmethod
    def aware(cls, value):
        return Provenance.aware(value)


    @model_validator(mode='after')
    def hash_matches(self):
        if self.content_hash != document_digest(self.document):
            raise ValueError('snapshot content hash mismatch')
        return self


class ProjectSettings(Contract):
    display_angle_unit: Literal['rad', 'deg']


class ProjectManifest(Contract):
    schema_version: Literal[2]
    id: UUID
    title: Name
    robot_snapshot_ids: tuple[UUID, ...]
    active_snapshot: UUID | None
    source_assets: tuple[AssetRef, ...]
    settings: ProjectSettings

    @model_validator(mode='after')
    def snapshots(self):
        if len(set(self.robot_snapshot_ids)) != len(self.robot_snapshot_ids):
            raise ValueError('duplicate snapshot ID')
        if self.active_snapshot is not None and self.active_snapshot not in self.robot_snapshot_ids:
            raise ValueError('active snapshot is not registered')
        return self


class ReplaceLink(Contract):
    kind: Literal['replace_link']
    link: Link


class ReplaceJoint(Contract):
    kind: Literal['replace_joint']
    joint: Joint


Operation = Annotated[ReplaceLink | ReplaceJoint, Field(discriminator='kind')]


class EditTransaction(Contract):
    id: UUID
    base_snapshot: UUID
    base_hash: Hash
    operations: Annotated[tuple[Operation, ...], Field(min_length=1)]
    preview_snapshot: RobotSnapshot
    validation: Literal['valid']
    actor: Literal['ui', 'agent']
    confirmed_at: datetime | None

    @field_validator('confirmed_at')
    @classmethod
    def aware(cls, value):
        return None if value is None else Provenance.aware(value)


class ServiceError(Contract):
    code: Name
    message: str
    details: tuple[str, ...]
    remediation: str | None


class OperationResult(Contract):
    operation_id: UUID
    status: Literal['succeeded', 'failed', 'queued', 'blocked_input', 'blocked_hardware']
    result: RobotSnapshot | None
    findings: tuple[str, ...]
    artifact_refs: tuple[AssetRef, ...]
    job_id: UUID | None
    error: ServiceError | None
