"""Turn one immutable M00 revision into a named STEP assembly for C02/C03."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_Reader, STEPControl_AsIs
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.gp import gp_Trsf, gp_Vec

from urdftools.cad.step_reader import inspect_step


class AssemblyError(ValueError):
    pass


def _location(values):
    if not isinstance(values,list) or len(values)!=3:
        raise AssemblyError('placement_mm must contain three values')
    numbers=[float(item) for item in values]
    if not all(math.isfinite(item) and abs(item)<1e6 for item in numbers):
        raise AssemblyError('placement_mm must be finite and within 1000 m')
    transform=gp_Trsf();transform.SetTranslation(gp_Vec(*numbers))
    return TopLoc_Location(transform)


def export_revision_assembly(revision: str | Path, output: str | Path) -> dict:
    revision=Path(revision);output=Path(output)
    if output.exists() or output.suffix.lower() not in ('.step','.stp'):
        raise AssemblyError('Choose a new STEP/STP output')
    recipe=json.loads((revision/'recipe.json').read_text())
    report=json.loads((revision/'report.json').read_text())
    document=TDocStd_Document(TCollection_ExtendedString('XmlOcaf'))
    shape_tool=XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    assembly=shape_tool.NewShape()
    TDataStd_Name.Set_s(assembly,TCollection_ExtendedString('URDFToolsModel'))
    names=[]
    for item in recipe['parts']:
        name=item['name']
        expected=next((row for row in report['parts'] if row['name']==name),None)
        if expected is None: raise AssemblyError(f'{name}: revision report missing')
        source=revision/f'{name}.step'
        if hashlib.sha256(source.read_bytes()).hexdigest()!=expected['step_sha256']:
            raise AssemblyError(f'{name}: STEP asset changed after revision')
        reader=STEPControl_Reader()
        if reader.ReadFile(str(source))!=IFSelect_RetDone or reader.TransferRoots()<1:
            raise AssemblyError(f'{name}: STEP asset cannot be reimported')
        shape=reader.OneShape()
        if shape.IsNull(): raise AssemblyError(f'{name}: STEP asset is empty')
        label=shape_tool.AddShape(shape,False)
        TDataStd_Name.Set_s(label,TCollection_ExtendedString(name))
        shape_tool.AddComponent(assembly,label,_location(item.get('placement_mm',[0,0,0])))
        names.append(name)
    shape_tool.UpdateAssemblies()
    writer=STEPCAFControl_Writer()
    writer.SetNameMode(True)
    if not writer.Transfer(document,STEPControl_AsIs):
        raise AssemblyError('STEP assembly transfer failed')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='.m01-assembly-',suffix='.step',dir=output.parent,delete=False) as file:
        temporary=Path(file.name)
    try:
        if writer.Write(str(temporary))!=IFSelect_RetDone:
            raise AssemblyError('STEP assembly write failed')
        inspected=inspect_step(temporary)
        returned=sorted(part['name'] for part in inspected['parts'])
        if returned!=sorted(names) or inspected['adapter']['status']!='matched':
            raise AssemblyError(f'STEP assembly reimport mismatch: {returned} != {sorted(names)}')
        try:
            os.link(temporary, output)
        except FileExistsError as exc:
            raise AssemblyError('STEP output appeared during export') from exc
    finally:
        temporary.unlink(missing_ok=True)
    return {'status':'ready','path':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'parts':names,'part_count':len(names),'unit':'mm',
            'source_revision_recipe_sha256':report['recipe_sha256']}
