#!/usr/bin/env python3
"""E04 bounded no-training MuJoCo CPU probes with time-stamped state and diagram replay."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
import sys

import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "python"))
from scripts.e02_dynamics_smoke import make_robot

STEP = 0.002
STEPS = 1200
TARGET = np.array([0.4, 0.0])  # shoulder step only; elbow target remains zero
FONT = "diagrammatic state replay, NOT MuJoCo camera-rendered footage"


def run_servo(model_path: Path, *, kp: float, kd: float, disturbance=False) -> dict:
    model = mujoco.MjModel.from_xml_path(str(model_path))
    model.opt.timestep = STEP
    data = mujoco.MjData(model)
    path = []
    max_speed = 0.0
    peak_torque = 0.0
    for t in range(STEPS):
        mujoco.mj_forward(model, data)
        pulse = np.array([0.0, 0.0])
        if disturbance and 500 <= t < 550:
            pulse[0] = 2.0
        torque = np.clip(kp*(TARGET - data.qpos) - kd*data.qvel + data.qfrc_bias + pulse, -25, 25)
        data.qfrc_applied[:] = torque
        mujoco.mj_step(model, data)
        assert np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all(), "non-finite simulated state"
        max_speed = max(max_speed, float(np.max(np.abs(data.qvel))))
        peak_torque = max(peak_torque, float(np.max(np.abs(torque))))
        if t % 20 == 0:
            path.append({"time_s": round(float(data.time), 6),
                         "joint_q_rad": [float(x) for x in data.qpos],
                         "joint_velocity_rad_s": [float(x) for x in data.qvel],
                         "torque_n_m": [float(x) for x in torque]})
    return {"kp": kp, "kd": kd, "disturbance": disturbance, "timestep_s": STEP,
            "steps": STEPS, "trace": path, "peak_speed_rad_s": max_speed,
            "peak_applied_torque_n_m": peak_torque,
            "final_tracking_error_rad": float(np.linalg.norm(TARGET-data.qpos)),
            "source_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest()}


def run_drop() -> dict:
    xml = """<mujoco model="e04_contact_probe">
      <option timestep="0.002" gravity="0 0 -9.81"/>
      <worldbody>
        <geom name="ground" type="plane" size="1 1 0.1" friction="1 0.1 0.1"/>
        <body name="ball" pos="0 0 0.4">
          <freejoint/><geom type="sphere" size="0.05" mass="0.5" friction="1 0.1 0.1"/>
        </body>
      </worldbody>
    </mujoco>"""
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    samples, contacts, minimum_distance = [], 0, 1.
    for t in range(STEPS):
        mujoco.mj_step(model, data)
        assert np.isfinite(data.qpos).all(), "non-finite drop state"
        if data.ncon:
            contacts += 1
            minimum_distance = min(minimum_distance, min(float(c.dist) for c in data.contact))
        if t % 20 == 0:
            samples.append({"time_s": round(float(data.time), 6),
                            "z_m": float(data.qpos[2]), "contacts": int(data.ncon)})
    return {"source_mjcf_sha256": hashlib.sha256(xml.encode()).hexdigest(),
            "timestep_s": STEP, "steps": STEPS,
            "contact_frames": contacts, "penetration_m": max(0., -minimum_distance),
            "resting_height_m": float(data.qpos[2]), "samples": samples,
            "role": "passive drop/contact settling; not quadruped standing"}


def run_sweep(path: Path) -> dict:
    model = mujoco.MjModel.from_xml_path(str(path))
    data = mujoco.MjData(model)
    positions = [-1.5, -0.7, 0, 0.7, 1.5]
    minimum_mass_eigen = float("inf")
    maximum_contacts = 0
    for a in positions:
        for b in positions:
            data.qpos[:] = (a, b)
            data.qvel[:] = 0
            mujoco.mj_forward(model, data)
            dense = np.zeros((model.nv, model.nv))
            mujoco.mj_fullM(model, data, dense)
            minimum_mass_eigen = min(minimum_mass_eigen,
                                     float(np.linalg.eigvalsh(dense).min()))
            maximum_contacts = max(maximum_contacts, int(data.ncon))
    return {"poses": len(positions)**2, "joint_range_rad": [min(positions), max(positions)],
            "minimum_mass_eigen": minimum_mass_eigen, "max_contacts_observed": maximum_contacts,
            "note": "finite sampled sweep; no claim of global absence of collision"}


def run_quad_stance(folder: Path) -> dict:
    """Real floating-base synthetic quadruped on a ground box; record falls, do not hide them."""
    import xml.etree.ElementTree as ET
    root=ET.parse(ROOT/"tests/fixtures/E00/quadruped_valid.urdf").getroot()
    ground=ET.SubElement(root,"link",name="world")
    collision=ET.SubElement(ground,"collision")
    ET.SubElement(collision,"origin",xyz="0 0 -0.1")
    ET.SubElement(ET.SubElement(collision,"geometry"),"box",size="4 4 0.2")
    floating=ET.SubElement(root,"joint",name="floating_root",type="floating")
    ET.SubElement(floating,"parent",link="world")
    ET.SubElement(floating,"child",link="torso")
    source=folder/"floating_quad_ground_stance.urdf"
    source.write_bytes(ET.tostring(root,encoding="utf-8",xml_declaration=True))
    model=mujoco.MjModel.from_xml_path(str(source))
    model.opt.timestep=STEP
    assert model.nv==14 and abs(float(model.body_mass.sum())-11.2)<1e-8
    data=mujoco.MjData(model)
    data.qpos[:3]=(0.,0.,0.36)
    data.qpos[3]=1
    series=[]
    ever_contact=0
    max_tilt=0.0
    for t in range(STEPS):
        mujoco.mj_forward(model,data)
        # Free base is unactuated; eight joint PD servos, 60 Nm clipping.
        data.qfrc_applied[:6]=0
        data.qfrc_applied[6:]=np.clip(-60*data.qpos[7:]-6*data.qvel[6:]
                                        +data.qfrc_bias[6:],-60,60)
        mujoco.mj_step(model,data)
        assert np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all()
        ever_contact+=bool(data.ncon)
        qw,qx,qy,qz=data.qpos[3:7]
        tilt=math.acos(max(-1.,min(1.,1-2*(qx*qx+qy*qy))))
        max_tilt=max(max_tilt,tilt)
        if t%20==0:
            series.append({"time_s":round(float(data.time),6),
                           "root_z_m":float(data.qpos[2]),"tilt_rad":tilt,
                           "contacts":int(data.ncon)})
    final_height=float(data.qpos[2])
    tilt=series[-1]["tilt_rad"]
    outcome=("stable_in_this_probe" if final_height>0.25 and tilt<0.4
             else "unstable_in_this_probe")
    return {"origin":"synthetic_fixture","source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
            "nq":model.nq,"nv":model.nv,"mass_kg":float(model.body_mass.sum()),
            "status":outcome,"final_root_height_m":final_height,
            "maximum_tilt_rad":max_tilt,"contact_steps":ever_contact,
            "trace":series,
            "limitations":"Not a real quadruped; outcome depends on PD, foot proxies and solver, not a diagnosis of URDF alone."}


def _draw_line(pixels, width, height, start, end, index):
    x0,y0 = start; x1,y1 = end
    dx=abs(x1-x0); dy=abs(y1-y0)
    sx=1 if x0<x1 else -1; sy=1 if y0<y1 else -1
    err=dx-dy
    while True:
        for ox in (-1,0,1):
            for oy in (-1,0,1):
                x,y=x0+ox,y0+oy
                if 0<=x<width and 0<=y<height: pixels[y*width+x]=index
        if x0==x1 and y0==y1: break
        twice=2*err
        if twice>-dy:err-=dy;x0+=sx
        if twice<dx:err+=dx;y0+=sy


def _gif_lzw_literals(pixels):
    # Valid LZW stream with an explicit clear code before each literal. This is
    # intentionally uncompressed, deterministic, and has no external video dependency.
    buffer=bytearray(); bits=0; count=0
    for code in (c for pixel in pixels for c in (4,pixel)):
        bits |= code<<count;count+=3
        while count>=8:
            buffer.append(bits&255);bits>>=8;count-=8
    bits |= 5<<count;count+=3
    while count>0:
        buffer.append(bits&255);bits>>=8;count-=8
    return b"".join(bytes([len(buffer[i:i+255])])+buffer[i:i+255]
                    for i in range(0,len(buffer),255))+b"\x00"


def write_gif(path: Path, trace: list[dict], width=160, height=160):
    frames=trace[::2][:30]
    payload=bytearray(b"GIF89a"+struct.pack("<HHBBB",width,height,0xF1,0,0))
    payload.extend(bytes([250,250,250,30,30,30,20,110,220,240,80,60]))
    payload.extend(b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00")
    for row in frames:
        q1,q2=row["joint_q_rad"]
        p0=(width//2,45)
        p1=(round(p0[0]-45*math.sin(q1)),round(p0[1]+45*math.cos(q1)))
        p2=(round(p1[0]-38*math.sin(q1+q2)),round(p1[1]+38*math.cos(q1+q2)))
        pixels=bytearray([0])*(width*height)
        _draw_line(pixels,width,height,p0,p1,1)
        _draw_line(pixels,width,height,p1,p2,2)
        _draw_line(pixels,width,height,(20,145),(140,145),3)
        payload.extend(b"\x21\xf9\x04\x04"+struct.pack("<H",8)+b"\x00\x00")
        payload.extend(b"\x2c"+struct.pack("<HHHHB",0,0,width,height,0))
        payload.extend(b"\x02"+_gif_lzw_literals(pixels))
    payload.append(0x3b)
    path.write_bytes(payload)
    return {"path": str(path), "format": "animated GIF", "frames": len(frames),
            "drawn_from": "MuJoCo CPU qpos values", "representation": FONT,
            "sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload)}


def main():
    folder=ROOT/"artifacts/E04"
    folder.mkdir(parents=True,exist_ok=True)
    source=folder/"two_link_probe.urdf"
    make_robot(source)
    stable=run_servo(source,kp=35,kd=6)
    bad_controller=run_servo(source,kp=35,kd=-6)
    disturbed=run_servo(source,kp=35,kd=6,disturbance=True)
    drop=run_drop()
    sweep=run_sweep(source)
    standing=run_quad_stance(folder)
    media=write_gif(folder/"two_link_state_replay.gif",stable["trace"])
    assert stable["final_tracking_error_rad"] < 0.05, stable["final_tracking_error_rad"]
    assert bad_controller["final_tracking_error_rad"] > stable["final_tracking_error_rad"]+0.1
    assert disturbed["final_tracking_error_rad"] < 0.05
    assert drop["contact_frames"] > 0 and 0.045 < drop["resting_height_m"] < 0.065
    assert sweep["minimum_mass_eigen"] > 0
    assert standing["contact_steps"]>0 and standing["nv"]==14
    assert standing["status"] in ("unstable_in_this_probe", "stable_in_this_probe")
    report={
        "status":"passed","origin":"synthetic_fixture","engine":f"MuJoCo {mujoco.__version__}",
        "source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
        "joint_step_stable":stable,"controller_negative_damping":bad_controller,
        "joint_pulse_recovery":disturbed,"contact_drop":drop,"joint_sweep":sweep,
        "quadruped_stance":standing,
        "media":media,"interpretation":"Same URDF, different PD: controller fault, not geometry fault.",
        "limits":"No RL training, hardware truth, quadruped stand, or photoreal renderer."}
    (folder/"probe-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"status":"passed","stable_error":stable["final_tracking_error_rad"],
        "wrong_pd_error":bad_controller["final_tracking_error_rad"],
        "pulse_recovery_error":disturbed["final_tracking_error_rad"],
        "drop_contact_frames":drop["contact_frames"],"resting_z_m":drop["resting_height_m"],
        "sweep_poses":sweep["poses"],"gif_frames":media["frames"],
        "quad_stance_status":standing["status"],
        "report":"artifacts/E04/probe-report.json"}))


if __name__ == "__main__":
    main()
