"""Independent MuJoCo compile check for E00 positive and injected fault URDFs."""
import json
from pathlib import Path
import mujoco

ROOT=Path(__file__).resolve().parents[1]/'tests/fixtures/E00'
expected={
  'quadruped_valid':('compiled',8),
  'humanoid_valid':('compiled',4),
  'humanoid_fixed_sensor_frame':('compiled',4),
  'hollow_frame_valid':('compiled',0),
  'quadruped_axis_context_mismatch':('compiled',8),
  'quadruped_misunit_visual':('compiled',8),
  'quadruped_zero_axis':('rejected',None),
  'humanoid_triangle_violation':('rejected',None),
  'humanoid_negative_inertia':('rejected',None),
}
observed={}
for name,(status,dof) in expected.items():
    try:
        model=mujoco.MjModel.from_xml_path(str(ROOT/(name+'.urdf')))
        observed[name]={'status':'compiled','joints':model.njnt,'dof':model.nv}
    except ValueError as exc:
        observed[name]={'status':'rejected','reason':str(exc).splitlines()[0]}
    assert observed[name]['status']==status,(name,observed[name])
    if dof is not None:assert observed[name]['dof']==dof
assert observed['quadruped_axis_context_mismatch']['status']=='compiled'
assert observed['quadruped_misunit_visual']['status']=='compiled'
print(json.dumps({'status':'passed','engine':'MuJoCo','cases':observed},ensure_ascii=False))
