"""Deterministic original fixtures, CC0-1.0; no measured robot/benchmark data."""
import json
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).parent


def uid(i):
    return str(UUID(int=i))


def provenance(kind='default'):
    return dict(source_kind=kind, source_ref='fixture:original-S02-CC0-1.0',
                version='1', recorded_at='2026-10-22T00:00:00Z', assumptions=['synthetic fixture; not real measurements'])


def parameter(value, unit):
    return dict(value=value, unit=unit, provenance=provenance('unknown' if value is None else 'default'), uncertainty=None)


def vector(values, unit):
    return [parameter(x, unit) for x in values]


def transform(parent, xyz=(0., 0., 0.), rpy=(0., 0., 0.)):
    return dict(relative_to=uid(parent), xyz=vector(xyz, 'm'), rpy=vector(rpy, 'rad'))


def link(i, name, mass):
    return dict(id=uid(i), name=name, visual=[], collision=[], cad_part_ids=[],
                inertial=dict(mass=parameter(mass, 'kg'), origin=transform(i, (0.0125, -0.025, 0.05), (0.1, 0.2, -0.3)),
                              tensor=vector((0.013, -0.001, 0.002, 0.022, -0.003, 0.03), 'kg*m^2')),
                provenance=provenance())


def joint(i, parent, child, name, xyz):
    return dict(id=uid(i), name=name, type='revolute', parent_id=uid(parent), child_id=uid(child),
                origin=transform(parent, xyz, (0.1, -0.2, 0.3)), axis=vector((0., 1., 0.), '1'),
                limits=dict(lower=parameter(-1.2, 'rad'), upper=parameter(1.5, 'rad'),
                            velocity=parameter(3.4, 'rad/s'), effort=parameter(None, 'N*m')),
                dynamics=None, mimic=None, provenance=provenance())


def document(name, links, joints):
    return dict(schema_version=2, id=uid(1), name=name, units='SI', handedness='right', up_axis='Z',
                origin='synthetic_fixture', links=links, joints=joints, materials=[], assets=[],
                extensions=[dict(namespace='fixture:custom', payload='<fixture keep="yes"/>', source_asset_id=None, source_span=None)],
                provenance=provenance())


def main():
    double = document('自制双连杆', [link(10, 'base', 2.5), link(11, 'arm', 0.75)],
                      [joint(100, 10, 11, 'hinge', (0.125, -0.25, 0.5))])
    links, joints = [link(10, 'body', 5.125)], []
    for n, leg in enumerate(('FL', 'FR', 'RL', 'RR')):
        hip, foot = 11 + 2*n, 12 + 2*n
        links += [link(hip, leg+'_upper', 0.625), link(foot, leg+'_lower', 0.3125)]
        joints += [joint(100+2*n, 10, hip, leg+'_hip', (0.2 if n < 2 else -0.2, 0.1 if n % 2 == 0 else -0.1, 0.)),
                   joint(101+2*n, hip, foot, leg+'_knee', (0., 0., -0.25))]
    quadruped = document('自制四足树', links, joints)
    old = dict(double)
    old['schema_version'] = 1
    old['unit_system'] = old.pop('units')
    for name, data in [('double_link.json', double), ('quadruped.json', quadruped), ('double_link_v1.json', old)]:
        (ROOT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
