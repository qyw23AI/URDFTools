"""Runs only inside FreeCADCmd; receives one bounded local JSON request via environment."""
import hashlib
import json
import os
from pathlib import Path
import sys

import FreeCAD as App
import Part
import Import


def fail(message):
    result = {'status': 'failed', 'reason': str(message)}
    Path(os.environ['URDFTOOLS_FREECAD_RESULT']).write_text(json.dumps(result))
    return 2


def main():
    request = json.loads(Path(os.environ['URDFTOOLS_FREECAD_REQUEST']).read_text())
    output = Path(request['output'])
    if request['action'] == 'fixture':
        variant=request.get('fixture_variant','base')
        if variant not in ('base','resized','topology','renamed','model_same','model_topology'):
            raise ValueError('Unsupported fixture variant')
        document = App.newDocument('URDFToolsFixture')
        model_fixture=variant.startswith('model_')
        base = document.addObject('Part::Feature', 'Base' if model_fixture else 'BaseBracket')
        base.Shape = Part.makeBox(20, 10, 5, App.Vector(-10,-5,0)) if model_fixture else Part.makeBox(20, 10, 5).cut(Part.makeCylinder(2, 5, App.Vector(10, 5, 0)))
        arm = document.addObject('Part::Feature', 'Arm' if model_fixture else 'ArmRenamed' if variant=='renamed' else 'ArmLink')
        arm_length=40 if variant=='resized' else 30
        arm_shape=Part.makeBox(20,10,5,App.Vector(40,-5,0)) if model_fixture else Part.makeBox(arm_length, 4, 4, App.Vector(25, 3, 0))
        if variant in ('topology','model_topology'):
            arm_shape=arm_shape.cut(Part.makeCylinder(1,5 if model_fixture else 4,App.Vector(50,0,0) if model_fixture else App.Vector(35,5,0)))
        arm.Shape = arm_shape
        document.recompute()
        document.saveAs(str(output))
        result = {'status':'created','version':App.Version(), 'objects': [base.Name, arm.Name]}
    elif request['action'] == 'export':
        source = Path(request['source'])
        document = App.openDocument(str(source))
        objects = []
        for item in document.Objects:
            if not hasattr(item, 'Shape') or item.Shape.isNull() or not item.Shape.Solids:
                continue
            if not item.Shape.isValid() or item.Shape.Volume <= 0:
                raise ValueError(f'{item.Name}: invalid or non-solid geometry')
            objects.append(item)
        if not objects:
            raise ValueError('FCStd has no valid closed solid objects')
        Import.export(objects, str(output))
        result = {'status':'exported_geometry_only','version':App.Version(),
                  'objects':[{'name':item.Name,'label':item.Label,'volume_mm3':item.Shape.Volume,
                              'solid_count':len(item.Shape.Solids)} for item in objects],
                  'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                  'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
                  'losses':['STEP drops FreeCAD feature history, sketches and constraints',
                            'Robot joints, motor limits and material densities require explicit mapping']}
    else:
        raise ValueError('Unknown FreeCAD worker action')
    Path(os.environ['URDFTOOLS_FREECAD_RESULT']).write_text(json.dumps(result))
    App.closeDocument(document.Name)
    return 0


try:
    raise SystemExit(main())
except Exception as exc:
    raise SystemExit(fail(exc))
