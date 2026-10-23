"""Regenerate original CC0 synthetic gold URDFs; no reference performance data."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent

def box_inertia(mass, size):
    x,y,z=size
    return (mass*(y*y+z*z)/12,mass*(x*x+z*z)/12,mass*(x*x+y*y)/12)

def link(robot,name,mass,size):
    item=ET.SubElement(robot,'link',name=name)
    if mass is not None:
        inertial=ET.SubElement(item,'inertial')
        ET.SubElement(inertial,'origin',xyz='0 0 0',rpy='0 0 0')
        ET.SubElement(inertial,'mass',value=str(mass))
        xx,yy,zz=box_inertia(mass,size)
        ET.SubElement(inertial,'inertia',ixx=str(xx),ixy='0',ixz='0',iyy=str(yy),iyz='0',izz=str(zz))
    for visual in ('visual','collision'):
        block=ET.SubElement(item,visual)
        ET.SubElement(ET.SubElement(block,'geometry'),'box',size=' '.join(map(str,size)))
    return item

def joint(robot,name,parent,child,origin,kind='revolute'):
    item=ET.SubElement(robot,'joint',name=name,type=kind)
    ET.SubElement(item,'parent',link=parent);ET.SubElement(item,'child',link=child)
    ET.SubElement(item,'origin',xyz=' '.join(map(str,origin)),rpy='0 0 0')
    if kind!='fixed':
        ET.SubElement(item,'axis',xyz='0 1 0')
        ET.SubElement(item,'limit',lower='-1',upper='1',effort='10',velocity='2')
    return item

def quadruped():
    robot=ET.Element('robot',name='synthetic_quadruped')
    link(robot,'torso',8,(0.4,0.2,0.1))
    for side,x,y in (('LF',0.15,0.1),('RF',0.15,-0.1),('LH',-0.15,0.1),('RH',-0.15,-0.1)):
        link(robot,side+'_upper',0.5,(0.04,0.04,0.2))
        link(robot,side+'_lower',0.3,(0.035,0.035,0.2))
        joint(robot,side+'_hip','torso',side+'_upper',(x,y,-0.04))
        joint(robot,side+'_knee',side+'_upper',side+'_lower',(0,0,-0.2))
    return robot

def humanoid():
    robot=ET.Element('robot',name='synthetic_humanoid')
    link(robot,'torso',12,(0.25,0.18,0.5))
    for side,y in (('L',0.09),('R',-0.09)):
        link(robot,side+'_thigh',2,(0.08,0.08,0.35))
        link(robot,side+'_shin',1.5,(0.07,0.07,0.35))
        joint(robot,side+'_hip','torso',side+'_thigh',(0,y,-0.2))
        joint(robot,side+'_knee',side+'_thigh',side+'_shin',(0,0,-0.35))
    return robot

def hollow_frame():
    robot=ET.Element('robot',name='synthetic_hollow_frame')
    frame=ET.SubElement(robot,'link',name='frame')
    walls=[((0,0.09,0),(0.3,0.02,0.03)),((0,-0.09,0),(0.3,0.02,0.03)),
           ((0.14,0,0),(0.02,0.16,0.03)),((-0.14,0,0),(0.02,0.16,0.03))]
    inertia=[0.,0.,0.]
    for center,size in walls:
        x,y,z=center;ix,iy,iz=box_inertia(0.5,size)
        inertia[0]+=ix+0.5*(y*y+z*z)
        inertia[1]+=iy+0.5*(x*x+z*z)
        inertia[2]+=iz+0.5*(x*x+y*y)
        for kind in ('visual','collision'):
            block=ET.SubElement(frame,kind)
            ET.SubElement(block,'origin',xyz=' '.join(map(str,center)),rpy='0 0 0')
            ET.SubElement(ET.SubElement(block,'geometry'),'box',size=' '.join(map(str,size)))
    body=ET.SubElement(frame,'inertial')
    ET.SubElement(body,'origin',xyz='0 0 0',rpy='0 0 0')
    ET.SubElement(body,'mass',value='2')
    ET.SubElement(body,'inertia',ixx=str(inertia[0]),ixy='0',ixz='0',iyy=str(inertia[1]),iyz='0',izz=str(inertia[2]))
    return robot

def save(name,root):
    ET.indent(root)
    (ROOT/(name+'.urdf')).write_bytes(ET.tostring(root,encoding='utf-8',xml_declaration=True))

def main():
    q=quadruped();save('quadruped_valid',q)
    h=humanoid();save('humanoid_valid',h)
    scaled=copy.deepcopy(q)
    scaled.find("./link[@name='torso']/visual/geometry/box").set('size','400 200 100')
    save('quadruped_misunit_visual',scaled)
    zero=copy.deepcopy(q);zero.find("./joint[@name='LF_knee']/axis").set('xyz','0 0 0')
    save('quadruped_zero_axis',zero)
    wrong=copy.deepcopy(q);wrong.find("./joint[@name='LF_knee']/axis").set('xyz','0 0 1')
    save('quadruped_axis_context_mismatch',wrong)
    triangle=copy.deepcopy(h)
    triangle.find("./link[@name='torso']/inertial/inertia").attrib.update(ixx='0.001',iyy='0.001',izz='0.01')
    save('humanoid_triangle_violation',triangle)
    negative=copy.deepcopy(h)
    negative.find("./link[@name='L_thigh']/inertial/inertia").set('ixx','-0.01')
    save('humanoid_negative_inertia',negative)
    sensor=copy.deepcopy(h);ET.SubElement(sensor,'link',name='imu_frame')
    joint(sensor,'imu_mount','torso','imu_frame',(0,0,0.22),kind='fixed')
    save('humanoid_fixed_sensor_frame',sensor)
    save('hollow_frame_valid',hollow_frame())
    manifest={'schema_version':1,'origin':'synthetic_fixture','license':'CC0-1.0','not_reference_performance':True,
      'design_context':{'quadruped_torso_size_m':[0.4,0.2,0.1],'LF_knee_expected_axis':[0,1,0]},
      'cases':[
        {'file':'quadruped_valid.urdf','category':'quadruped','expected':[]},
        {'file':'humanoid_valid.urdf','category':'humanoid','expected':[]},
        {'file':'quadruped_misunit_visual.urdf','category':'quadruped','expected':[{'rule':'context_scale_mismatch','location':'torso/visual/box','certainty':'context_dependent'}]},
        {'file':'quadruped_zero_axis.urdf','category':'quadruped','expected':[{'rule':'invalid_joint_axis','location':'LF_knee','certainty':'definite'}]},
        {'file':'quadruped_axis_context_mismatch.urdf','category':'quadruped','expected':[{'rule':'context_axis_mismatch','location':'LF_knee','certainty':'context_dependent'}]},
        {'file':'humanoid_triangle_violation.urdf','category':'humanoid','expected':[{'rule':'inertia_triangle_violation','location':'torso','certainty':'definite'}]},
        {'file':'humanoid_negative_inertia.urdf','category':'humanoid','expected':[{'rule':'negative_inertia','location':'L_thigh','certainty':'definite'}]},
        {'file':'humanoid_fixed_sensor_frame.urdf','category':'humanoid','expected':[],'positive_boundary':'massless fixed sensor frame'},
        {'file':'hollow_frame_valid.urdf','category':'other','expected':[],'positive_boundary':'COM in empty cavity with analytic positive inertia'}]}
    (ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n')

if __name__=='__main__':main()
