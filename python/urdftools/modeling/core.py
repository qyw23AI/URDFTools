"""Allowlisted build123d model recipe and transactional artifact store.

All geometry inputs are millimetres. Density is kg/m^3; report masses are SI.
The incoming recipe is data, never evaluated as Python code.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from build123d import (Axis, Box, Circle, Cylinder, Plane, Polygon, Pos, Rectangle,
                       export_step, export_stl, extrude, fillet, import_step, revolve)

from urdftools.cad.mass_properties import calculate_solid_mass_properties


class ModelingError(ValueError):
    pass


def positive(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ModelingError(f'{label} must be a positive finite number')
    try:
        result=float(value)
    except (TypeError,ValueError,OverflowError) as exc:
        raise ModelingError(f'{label} must be a positive finite number') from exc
    if not math.isfinite(result) or result <= 0:
        raise ModelingError(f'{label} must be a positive finite number')
    return result


def finite(value: Any, label: str) -> float:
    try: result=float(value)
    except (TypeError,ValueError,OverflowError) as exc:
        raise ModelingError(f'{label} must be finite') from exc
    if not math.isfinite(result): raise ModelingError(f'{label} must be finite')
    return result


def _point(values, label: str, count: int):
    if not isinstance(values,list) or len(values)!=count:
        raise ModelingError(f'{label} must contain {count} values')
    return [finite(value,label) for value in values]


def build_part(recipe: dict):
    if not isinstance(recipe,dict): raise ModelingError('Part recipe must be an object')
    profile=recipe.get('profile')
    if not isinstance(profile,dict): raise ModelingError('Part profile is missing')
    kind=profile.get('kind')
    if kind=='rectangle':
        sketch=Rectangle(positive(profile.get('width_mm'),'width_mm'),positive(profile.get('height_mm'),'height_mm'))
    elif kind=='circle':
        sketch=Circle(positive(profile.get('radius_mm'),'radius_mm'))
    elif kind=='polygon':
        points=profile.get('points_mm')
        if not isinstance(points,list) or not 3<=len(points)<=100:
            raise ModelingError('Polygon needs 3..100 vertices')
        sketch=Polygon(*[tuple(_point(point,'polygon vertex',2)) for point in points],align=None)
    else:
        raise ModelingError(f'Unsupported sketch kind: {kind}')
    holes=profile.get('holes',[])
    if kind!='rectangle' and holes: raise ModelingError('Holes are currently supported in rectangle sketches')
    if not isinstance(holes,list) or len(holes)>100: raise ModelingError('Too many holes')
    for index,hole in enumerate(holes):
        if not isinstance(hole,dict): raise ModelingError('Hole must be an object')
        x,y=_point(hole.get('center_mm'),f'hole {index} center',2)
        radius=positive(hole.get('radius_mm'),f'hole {index} radius')
        if abs(x)+radius>=float(profile['width_mm'])/2 or abs(y)+radius>=float(profile['height_mm'])/2:
            raise ModelingError('Hole crosses sketch boundary')
        sketch-=Pos(x,y)*Circle(radius)
    operation=recipe.get('operation')
    if not isinstance(operation,dict): raise ModelingError('Primary operation missing')
    if operation.get('kind')=='extrude':
        shape=extrude(sketch,positive(operation.get('distance_mm'),'extrude distance_mm'))
    elif operation.get('kind')=='revolve':
        if holes: raise ModelingError('Revolve with holes is unsupported')
        axis=operation.get('axis')
        if axis not in ('X','Y'): raise ModelingError('Revolve axis must be X or Y')
        angle=positive(operation.get('angle_deg'),'revolve angle_deg')
        if angle>360: raise ModelingError('Revolve angle exceeds 360 degrees')
        shape=revolve(sketch,Axis.X if axis=='X' else Axis.Y,revolution_arc=angle)
    else:
        raise ModelingError('Primary operation must be extrude or revolve')
    operations=recipe.get('modifiers',[])
    if not isinstance(operations,list) or len(operations)>100: raise ModelingError('Too many modifiers')
    for index,modifier in enumerate(operations):
        if not isinstance(modifier,dict): raise ModelingError('Modifier must be an object')
        kind=modifier.get('kind')
        if kind in ('subtract_box','add_box'):
            dimensions=_point(modifier.get('size_mm'),f'modifier {index} size',3)
            if any(value<=0 for value in dimensions): raise ModelingError('Box size must be positive')
            location=_point(modifier.get('center_mm',[0,0,0]),'box center',3)
            tool=Pos(*location)*Box(*dimensions)
            shape=shape-tool if kind=='subtract_box' else shape+tool
        elif kind in ('subtract_cylinder','add_cylinder'):
            radius=positive(modifier.get('radius_mm'),'cylinder radius')
            height=positive(modifier.get('height_mm'),'cylinder height')
            location=_point(modifier.get('center_mm',[0,0,0]),'cylinder center',3)
            tool=Pos(*location)*Cylinder(radius,height)
            shape=shape-tool if kind=='subtract_cylinder' else shape+tool
        elif kind=='fillet':
            radius=positive(modifier.get('radius_mm'),'fillet radius')
            direction=modifier.get('parallel_axis')
            if direction not in ('X','Y','Z'): raise ModelingError('Fillet needs X/Y/Z edge direction')
            axis={'X':Axis.X,'Y':Axis.Y,'Z':Axis.Z}[direction]
            edges=shape.edges().filter_by(axis)
            if not edges: raise ModelingError('Fillet selected no edges')
            shape=fillet(edges,radius)
        else:
            raise ModelingError(f'Unsupported modifier: {kind}')
    if not shape.is_valid or not shape.solids() or shape.volume<=0:
        raise ModelingError('Result must be a valid closed solid')
    return shape


def build_project(spec: dict, output_dir: Path) -> dict:
    if not isinstance(spec,dict) or spec.get('schema_version')!=1:
        raise ModelingError('Model recipe schema_version must be 1')
    parts=spec.get('parts')
    if not isinstance(parts,list) or not 1<=len(parts)<=100:
        raise ModelingError('Project needs 1..100 parts')
    names=set()
    output_dir.mkdir(parents=True,exist_ok=False)
    summaries=[]
    for item in parts:
        if not isinstance(item,dict): raise ModelingError('Part must be an object')
        name=item.get('name')
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}',name) or name in names:
            raise ModelingError('Part name invalid or duplicate')
        names.add(name)
        material=item.get('material')
        if not isinstance(material,str) or not material.strip() or len(material)>100:
            raise ModelingError(f'{name}: explicit material name required')
        density=positive(item.get('density_kg_m3'),f'{name} density_kg_m3')
        try:
            shape=build_part(item)
        except ModelingError: raise
        except Exception as exc:
            raise ModelingError(f'{name}: CAD operation failed: {exc}') from exc
        properties=calculate_solid_mass_properties(shape.wrapped,density,name=name)
        if properties['status']!='known': raise ModelingError(f'{name}: exact mass properties unavailable')
        step=output_dir/f'{name}.step';mesh=output_dir/f'{name}.stl'
        export_step(shape,str(step))
        export_stl(shape,str(mesh))
        reread=import_step(str(step))
        if not math.isclose(reread.volume,shape.volume,rel_tol=1e-6,abs_tol=1e-6):
            raise ModelingError(f'{name}: STEP roundtrip changed volume')
        summaries.append({'name':name,'material':material,'density_kg_m3':density,
                          'volume_mm3':shape.volume,'mass_kg':properties['mass_kg'],
                          'center_of_mass_m':properties['center_of_mass_m'],
                          'inertia_com_kg_m2':properties['inertia_com_kg_m2'],
                          'step_sha256':hashlib.sha256(step.read_bytes()).hexdigest(),
                          'mesh_sha256':hashlib.sha256(mesh.read_bytes()).hexdigest()})
    report={'schema_version':1,'status':'ready','parts':summaries,
            'total_mass_kg':sum(row['mass_kg'] for row in summaries),
            'recipe_sha256':hashlib.sha256(json.dumps(spec,sort_keys=True,allow_nan=False).encode()).hexdigest()}
    (output_dir/'recipe.json').write_text(json.dumps(spec,indent=2,sort_keys=True)+'\n')
    (output_dir/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report


def apply_project(directory: str | Path, spec: dict, *, expected_revision: int | None) -> dict:
    """Write a new immutable revision only after all CAD operations and exports pass."""
    root=Path(directory)
    root.mkdir(parents=True,exist_ok=True)
    current_path=root/'current.json'
    old=json.loads(current_path.read_text()) if current_path.is_file() else None
    old_revision=old['revision'] if old else 0
    if expected_revision!=old_revision:
        raise ModelingError(f'Stale revision; current is {old_revision}')
    next_revision=old_revision+1
    revisions=root/'revisions';revisions.mkdir(exist_ok=True)
    destination=revisions/f'{next_revision:06d}'
    if destination.exists(): raise ModelingError('Revision destination already exists')
    with tempfile.TemporaryDirectory(prefix='.model-staging-',dir=root) as staging:
        work=Path(staging)/'package'
        report=build_project(spec,work)
        work.rename(destination)
    pointer={'revision':next_revision,'report_sha256':hashlib.sha256((destination/'report.json').read_bytes()).hexdigest()}
    with tempfile.NamedTemporaryFile(prefix='.current-',dir=root,mode='w',delete=False) as stream:
        temporary=Path(stream.name);stream.write(json.dumps(pointer)+'\n')
    try:
        os.replace(temporary,current_path)
    except OSError:
        temporary.unlink(missing_ok=True)
        shutil.rmtree(destination)
        raise
    return {'revision':next_revision,'package':str(destination),'report':report}
