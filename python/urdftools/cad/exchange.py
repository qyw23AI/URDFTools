"""Conservative local IGES/BREP to STEP bridge with explicit loss reporting.

This bridge carries exact solid geometry only. It never invents assemblies,
materials, joints, density or provenance from unitless BREP data.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import tempfile

from OCP.BRep import BRep_Builder
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepTools import BRepTools
from OCP.GProp import GProp_GProps
from OCP.IGESControl import IGESControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs, STEPControl_Reader
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Pnt, gp_Trsf
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform


class ExchangeError(ValueError):
    pass


def _metrics(shape):
    solids = TopExp_Explorer(shape, TopAbs_SOLID)
    count = 0
    while solids.More():
        if not BRepCheck_Analyzer(solids.Current()).IsValid():
            raise ExchangeError('Invalid B-rep solid')
        count += 1
        solids.Next()
    if count == 0:
        raise ExchangeError('No closed solid; surface-only CAD cannot enter physical export')
    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, properties)
    volume = float(properties.Mass())
    if not math.isfinite(volume) or volume <= 0:
        raise ExchangeError('Invalid solid volume')
    return {'solid_count': count, 'volume_mm3': volume,
            'center_of_mass_mm': [float(getattr(properties.CentreOfMass(), axis)()) for axis in ('X','Y','Z')]}


def _read(path: Path, brep_unit: str | None):
    extension = path.suffix.lower()
    if extension in ('.igs', '.iges'):
        if brep_unit is not None:
            raise ExchangeError('--brep-unit applies only to unitless BREP')
        reader = IGESControl_Reader()
        if reader.ReadFile(str(path)) != IFSelect_RetDone or reader.TransferRoots() < 1:
            raise ExchangeError('IGES read or transfer failed')
        return reader.OneShape(), 'IGES source units interpreted by OpenCascade; normalized kernel mm'
    if extension in ('.brep', '.brp'):
        if brep_unit not in ('mm','m'):
            raise ExchangeError('Unitless BREP requires explicit --brep-unit mm or m')
        shape = TopoDS_Shape()
        if not BRepTools.Read_s(shape, str(path), BRep_Builder()) or shape.IsNull():
            raise ExchangeError('BREP read failed')
        if brep_unit == 'm':
            transform = gp_Trsf()
            transform.SetScale(gp_Pnt(0, 0, 0), 1000)
            shape = BRepBuilderAPI_Transform(shape, transform, True).Shape()
        return shape, f'BREP operator-declared {brep_unit}; normalized kernel mm'
    if extension in ('.sldasm', '.sldprt'):
        raise ExchangeError('Native SolidWorks files require Windows + SolidWorks extraction; export STEP/IGES or sw2robot graph on that machine')
    if extension == '.fcstd':
        raise ExchangeError('FCStd requires optional local FreeCAD bridge; export STEP from FreeCAD first')
    raise ExchangeError(f'Unsupported CAD extension: {extension}')


def convert_to_step(source: str | Path, output: str | Path, *, brep_unit: str | None = None) -> dict:
    source, output = Path(source), Path(output)
    if not source.is_file() or source.stat().st_size == 0:
        raise ExchangeError('Source CAD file missing or empty')
    if source.stat().st_size > 512*1024*1024:
        raise ExchangeError('Source CAD file exceeds 512 MiB local limit')
    if output.suffix.lower() not in ('.step','.stp') or os.path.lexists(output):
        raise ExchangeError('Choose a new .step or .stp output path')
    if output.resolve() == source.resolve():
        raise ExchangeError('Output cannot overwrite source')
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    shape, units = _read(source, brep_unit)
    before = _metrics(shape)
    writer = STEPControl_Writer()
    if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone:
        raise ExchangeError('OpenCascade failed to transfer B-rep to STEP')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='.urdftools-c04-',suffix='.step',dir=output.parent,delete=False) as stream:
        temporary = Path(stream.name)
    try:
        if writer.Write(str(temporary)) != IFSelect_RetDone:
            raise ExchangeError('OpenCascade failed to write STEP')
        reread = STEPControl_Reader()
        if reread.ReadFile(str(temporary)) != IFSelect_RetDone or reread.TransferRoots() < 1:
            raise ExchangeError('Written STEP did not reimport')
        after = _metrics(reread.OneShape())
        if before['solid_count'] != after['solid_count'] or not math.isclose(before['volume_mm3'],after['volume_mm3'], rel_tol=1e-6,abs_tol=1e-6):
            raise ExchangeError('STEP roundtrip changed solid count or volume')
        if any(not math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-5) for a,b in zip(before['center_of_mass_mm'],after['center_of_mass_mm'])):
            raise ExchangeError('STEP roundtrip changed geometric center')
        if hashlib.sha256(source.read_bytes()).hexdigest() != original_hash:
            raise ExchangeError('Source CAD changed during conversion')
        try:
            os.link(temporary, output)  # O_EXCL semantics: never replace a user file
        except FileExistsError as exc:
            raise ExchangeError('STEP output appeared during conversion; no overwrite') from exc
    finally:
        temporary.unlink(missing_ok=True)
    return {'status':'converted_geometry_only','source':str(source),'source_sha256':original_hash,
            'step':str(output),'step_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'unit_handling':units, 'before':before,'after':after,
            'losses':['assembly hierarchy and part names are not preserved by this geometry-only bridge',
                      'colors and materials are not preserved','joints, limits, density and actuator data are unavailable',
                      'human remapping and physical verification are required before URDF export']}
