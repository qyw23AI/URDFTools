"""Generate B-rep STEP fixtures for independent C01 mass/inertia tests."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
from pathlib import Path

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeSphere
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests/fixtures/C01"


def set_name(label, name: str) -> None:
    TDataStd_Name.Set_s(label, TCollection_ExtendedString(name))


def translation(x: float, y: float, z: float) -> TopLoc_Location:
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(x, y, z))
    return TopLoc_Location(transform)


def rotated_box_location() -> TopLoc_Location:
    transform = gp_Trsf()
    transform.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 0.7853981633974483)
    transform.SetTranslationPart(gp_Vec(100, -20, 30))
    return TopLoc_Location(transform)


def write_step(document, path: Path) -> None:
    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    writer.SetColorMode(True)
    if not writer.Transfer(document, STEPControl_AsIs):
        raise RuntimeError(f"Could not transfer XCAF document to STEP: {path}")
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f"Could not write STEP fixture: {path}")
    # Normalize OCCT's wall-clock timestamp; entity ordering may still vary between builds.
    text = path.read_text(encoding="latin-1")
    text, count = re.subn(r"(FILE_NAME\('[^']*',')[^']+(')", r"\g<1>2026-01-01T00:00:00\2", text, count=1)
    if count != 1:
        raise RuntimeError(f"Could not normalize STEP FILE_NAME timestamp: {path}")
    path.write_text(text, encoding="latin-1")


def new_document():
    document = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    return document, XCAFDoc_DocumentTool.ShapeTool_s(document.Main())


def named_shape(shape_tool, shape, name: str):
    label = shape_tool.AddShape(shape, False)
    set_name(label, name)
    return label


def write_box() -> Path:
    document, shape_tool = new_document()
    named_shape(shape_tool, BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 20, 10, 5).Shape(), "Box20x10x5")
    path = OUT / "box_mm.step"
    write_step(document, path)
    return path


def write_offset_double_sphere() -> Path:
    document, shape_tool = new_document()
    sphere = named_shape(shape_tool, BRepPrimAPI_MakeSphere(gp_Pnt(0, 0, 0), 10).Shape(), "SpherePart")
    assembly = shape_tool.NewShape()
    set_name(assembly, "OffsetDoubleSphere")
    first = shape_tool.AddComponent(assembly, sphere, translation(0, 0, 0))
    set_name(first, "SphereA")
    second = shape_tool.AddComponent(assembly, sphere, translation(50, 0, 0))
    set_name(second, "SphereB")
    shape_tool.UpdateAssemblies()
    path = OUT / "offset_double_sphere_mm.step"
    write_step(document, path)
    return path


def write_rotated_box() -> Path:
    document, shape_tool = new_document()
    box = named_shape(shape_tool, BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 20, 10, 5).Shape(), "RotatedBox")
    assembly = shape_tool.NewShape()
    set_name(assembly, "RotatedBoxAssembly")
    instance = shape_tool.AddComponent(assembly, box, rotated_box_location())
    set_name(instance, "RotatedBoxInstance")
    shape_tool.UpdateAssemblies()
    path = OUT / "rotated_box_mm.step"
    write_step(document, path)
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    paths = [write_box(), write_offset_double_sphere(), write_rotated_box()]
    files = {}
    for path in paths:
        raw = path.read_bytes()
        files[path.name] = {"size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    manifest = {
        "schema_version": 1,
        "fixture_origin": "self-authored analytic B-rep shapes; not vendor or user robot assets",
        "generator": "scripts/generate_c01_fixtures.py",
        "kernel_distribution": "cadquery-ocp-novtk",
        "kernel_version": importlib.metadata.version("cadquery-ocp-novtk"),
        "units": "millimetre",
        "models": {
            "box_mm.step": {"name": "Box20x10x5", "dimensions_mm": [20, 10, 5]},
            "offset_double_sphere_mm.step": {
                "name": "OffsetDoubleSphere", "part_count": 2, "sphere_radius_mm": 10,
                "sphere_centers_mm": [[0, 0, 0], [50, 0, 0]], "density_test_kg_m3": 1000
            },
            "rotated_box_mm.step": {
                "name": "RotatedBox", "dimensions_mm": [20, 10, 5], "rotation_z_rad": 0.7853981633974483,
                "translation_mm": [100, -20, 30], "density_test_kg_m3": 1000
            }
        },
        "files": files
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "generated", "kernel_version": manifest["kernel_version"], "files": files}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
