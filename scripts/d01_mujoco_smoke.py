#!/usr/bin/env python3
"""Compile both CAD-derived URDFs with real MuJoCo; no training is run."""
import json
from pathlib import Path
import mujoco

root = Path(__file__).resolve().parents[1]
plan = json.loads((root/"artifacts/D01/parametric-leg-report.json").read_text())["plan"]
records = {}
for label in ("baseline", "variant"):
    part = plan[label]
    model = mujoco.MjModel.from_xml_string(part["urdf_xml"])
    assert model.nq == model.nv == 1
    # MuJoCo's URDF importer discards the inertial base root in this fixed-root model.
    assert abs(float(sum(model.body_mass)) - part["mass_kg"]) < 1e-9
    # MuJoCo fuses fixed foot_frame; inspect actual collision geom dimensions.
    assert model.ngeom == 1
    assert abs(float(model.geom_pos[0][0]) - part["length_m"]/2) < 1e-10
    assert abs(float(model.geom_size[0][0])*2 - part["length_m"]) < 1e-10
    records[label] = {"dof": model.nv, "dynamic_mass_kg": float(sum(model.body_mass)),
                      "collision_box_length_m": float(model.geom_size[0][0])*2,
                      "fixed_foot_frame_fused": True,
                      "root_inertial_mass_dropped_by_importer": True}
(root/"artifacts/D01/mujoco-compile-report.json").write_text(json.dumps(records,indent=2)+"\n")
print(json.dumps(records))
