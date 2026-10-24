#!/usr/bin/env python3
"""Bounded read-only MuJoCo settling of an imported URDF on a ground plane."""
import argparse
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

import mujoco


def settle(source: Path, requested: dict[str, float], use_limits: dict[str, bool] | None = None) -> dict:
    if source.suffix.lower() != '.urdf' or not source.is_file() or source.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('A bounded imported URDF is required')
    robot = ET.parse(source).getroot()
    if robot.tag != 'robot':
        raise ValueError('Invalid URDF root')
    # MuJoCo does not use visual DAE textures for dynamics. Keep collision and
    # inertial definitions intact, removing only visual elements in a derivative.
    for link in robot.findall('link'):
        for visual in list(link.findall('visual')):
            link.remove(visual)
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.urdf', prefix='.gravity-',
                                     dir=source.parent, delete=False) as output:
        derivative = Path(output.name)
        output.write(ET.tostring(robot, encoding='utf-8', xml_declaration=True))
    try:
        spec = mujoco.MjSpec.from_file(str(derivative))
        base = spec.worldbody.first_body()
        if base is None:
            raise ValueError('URDF has no root body')
        base.add_freejoint()
        spec.worldbody.add_geom(name='viewer_ground', type=mujoco.mjtGeom.mjGEOM_PLANE,
                                size=[5, 5, 0.1], pos=[0, 0, 0],
                                friction=[1, 0.005, 0.0001], rgba=[0.3, 0.35, 0.4, 1])
        model = spec.compile()
        model.opt.timestep = 0.002
        model.opt.gravity[:] = [0, 0, -9.81]
        ground_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, 'viewer_ground')
        if ground_id < 0:
            raise ValueError('Physical ground plane was not compiled')
        # An overdamped ground contact and post-impact velocity damping keep
        # this no-controller landing preview from repeatedly springing upward.
        model.geom_solref[ground_id] = [0.02, 2.0]
        model.geom_priority[ground_id] = 1
        for name, enabled in (use_limits or {}).items():
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if jid > 0 and not enabled:
                model.jnt_limited[jid] = 0
        data = mujoco.MjData(model)
        if model.nq < 7 or model.jnt_type[0] != mujoco.mjtJoint.mjJNT_FREE:
            raise ValueError('Floating base could not be compiled')
        for name, value in requested.items():
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if jid < 0 or jid == 0:
                continue
            address = int(model.jnt_qposadr[jid])
            bounded = float(value)
            if model.jnt_limited[jid]:
                lower, upper = map(float, model.jnt_range[jid])
                bounded = max(lower, min(upper, bounded))
            data.qpos[address] = bounded
        mujoco.mj_forward(model, data)
        moving_geoms = [i for i in range(model.ngeom) if model.geom_bodyid[i] != 0]
        if not moving_geoms:
            raise ValueError('URDF has no collision geometry for ground contact')
        def ground_clearance():
            return min(float(mujoco.mj_geomDistance(model, data, ground_id, i, 100.0, None))
                       for i in moving_geoms)
        # This is a gravity-settling preview of the pose already shown on the
        # viewer floor, not a drop test. Begin at contact without an artificial
        # 4 cm lift that would add impact energy and a visible first-frame jump.
        data.qpos[2] += 0.0001 - ground_clearance()
        mujoco.mj_forward(model, data)
        def frame(seconds):
            values = {}
            for jid in range(1, model.njnt):
                if int(model.jnt_type[jid]) not in (int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE)):
                    continue
                name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, jid)
                if name:
                    values[name] = float(data.qpos[model.jnt_qposadr[jid]])
            return {'time': round(seconds, 4), 'position': [float(x) for x in data.qpos[:3]],
                    'quaternion_wxyz': [float(x) for x in data.qpos[3:7]], 'joints': values,
                    'ground_clearance': ground_clearance()}
        frames = [frame(0.0)]
        frame_interval = max(1, round(1 / (30 * model.opt.timestep)))
        limited_joints = [jid for jid in range(1, model.njnt) if model.jnt_limited[jid] and
                          int(model.jnt_type[jid]) in (int(mujoco.mjtJoint.mjJNT_HINGE),
                                                       int(mujoco.mjtJoint.mjJNT_SLIDE))]
        stable_samples = 0
        previous_pose = None
        sample_interval = int(0.25 / model.opt.timestep)
        max_steps = int(10.0 / model.opt.timestep)
        steps = 0
        for steps in range(1, max_steps + 1):
            mujoco.mj_step(model, data)
            # The imported URDF limits are soft in MuJoCo. Keep the viewer pose
            # within the same hard bounds used by its URDF joint controls.
            projected = False
            for jid in limited_joints:
                address = int(model.jnt_qposadr[jid])
                lower, upper = map(float, model.jnt_range[jid])
                bounded = max(lower, min(upper, float(data.qpos[address])))
                if bounded != float(data.qpos[address]):
                    data.qpos[address] = bounded
                    data.qvel[int(model.jnt_dofadr[jid])] = 0.0
                    projected = True
            if projected:
                mujoco.mj_forward(model, data)
            clearance = ground_clearance()
            # MuJoCo contacts are soft and may otherwise sink several cm into
            # the plane. Project only the floating base's vertical position;
            # retain joint angles, orientation, and horizontal motion.
            if clearance < -0.0005:
                data.qpos[2] += -clearance + 0.0001
                data.qvel[2] = max(0.0, float(data.qvel[2]))
                mujoco.mj_forward(model, data)
                clearance = ground_clearance()
            ground_contacts = sum(1 for contact in data.contact[:data.ncon]
                                  if ground_id in (contact.geom1, contact.geom2))
            if ground_contacts or clearance < 0.002:
                data.qvel[:] *= 0.97
                # Treat the ground impact as inelastic in this preview. The
                # support projection above still allows the base to follow
                # changing joint geometry without passing through the plane.
                data.qvel[2] = min(0.0, float(data.qvel[2]))
            if steps % frame_interval == 0:
                frames.append(frame(steps * model.opt.timestep))
            speed = max((abs(float(value)) for value in data.qvel), default=0.0)
            if steps >= int(1.0 / model.opt.timestep) and steps % sample_interval == 0:
                pose = [float(value) for value in data.qpos]
                if previous_pose and (ground_contacts or clearance < 0.002) and max(abs(a - b) for a, b in zip(pose, previous_pose)) < 0.002:
                    stable_samples += 1
                    if stable_samples >= 3:
                        break
                else:
                    stable_samples = 0
                previous_pose = pose
        if not all(float(x) == float(x) and abs(float(x)) < 1e5 for x in data.qpos):
            raise ValueError('Gravity simulation became unstable')
        ground_contacts = sum(1 for contact in data.contact[:data.ncon]
                              if ground_id in (contact.geom1, contact.geom2))
        final_clearance = ground_clearance()
        if not ground_contacts and final_clearance > 0.002:
            raise ValueError('Robot did not contact the physical ground plane')
        if frames[-1]['time'] < steps * model.opt.timestep:
            frames.append(frame(steps * model.opt.timestep))
        joints = {}
        for jid in range(1, model.njnt):
            if int(model.jnt_type[jid]) not in (int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE)):
                continue
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, jid)
            if name:
                value = float(data.qpos[model.jnt_qposadr[jid]])
                if model.jnt_limited[jid]:
                    lower, upper = map(float, model.jnt_range[jid])
                    value = max(lower, min(upper, value))
                joints[name] = value
        return {'status': 'settled' if stable_samples >= 3 else 'grounded',
                'engine': f'MuJoCo {mujoco.__version__}',
                'position': [float(x) for x in data.qpos[:3]],
                'quaternion_wxyz': [float(x) for x in data.qpos[3:7]],
                'joints': joints, 'contacts': int(data.ncon), 'ground_contacts': int(ground_contacts),
                'ground_clearance': final_clearance,
                'joint_count': len(joints), 'max_speed': speed,
                'simulated_seconds': steps * model.opt.timestep, 'frames': frames}
    finally:
        derivative.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--joints', default='{}')
    parser.add_argument('--limits', default='{}')
    args = parser.parse_args()
    values = json.loads(args.joints)
    limits = json.loads(args.limits)
    if not isinstance(values, dict) or len(values) > 256 or any(
        not isinstance(k, str) or len(k) > 160 or type(v) not in (int, float) or abs(v) > 100
        for k, v in values.items()
    ):
        parser.error('Invalid joint pose')
    if not isinstance(limits, dict) or len(limits) > 256 or any(
        not isinstance(k, str) or len(k) > 160 or type(v) is not bool for k, v in limits.items()
    ):
        parser.error('Invalid joint limits')
    print(json.dumps(settle(args.model, values, limits)))


if __name__ == '__main__':
    main()
