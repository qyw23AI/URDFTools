"""Generate self-authored STEP fixtures for C00 using the pinned OCP worker."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
from pathlib import Path

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.IFSelect import IFSelect_RetDone
from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_ColorSurf, XCAFDoc_DocumentTool
from OCP.gp import gp_Pnt, gp_Trsf, gp_Vec

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests/fixtures/C00"


def set_name(label, name: str) -> None:
    TDataStd_Name.Set_s(label, TCollection_ExtendedString(name))


def translation(x: float, y: float, z: float) -> TopLoc_Location:
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(x, y, z))
    return TopLoc_Location(transform)


def add_part(shape_tool, color_tool, name: str, dimensions: tuple[float, float, float], color):
    dx, dy, dz = dimensions
    shape = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), dx, dy, dz).Shape()
    label = shape_tool.AddShape(shape, False)
    set_name(label, name)
    if color is not None:
        r, g, b = color
        color_tool.SetColor(label, Quantity_Color(r, g, b, Quantity_TOC_RGB), XCAFDoc_ColorSurf)
    return label


def write_document(document, path: Path) -> None:
    # STEPCAFControl uses the OpenCascade defaults (mm, AP214) for the base fixture.
    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    writer.SetColorMode(True)
    if not writer.Transfer(document, STEPControl_AsIs):
        raise RuntimeError(f"Could not transfer XCAF document to STEP model: {path}")
    status = writer.Write(str(path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"Could not write STEP fixture: {path} (status={status})")
    # OCCT embeds the wall-clock timestamp in FILE_NAME; normalize it for stable fixture hashes.
    text = path.read_text(encoding="latin-1")
    text, count = re.subn(r"(FILE_NAME\('[^']*',')[^']+(')", r"\g<1>2026-01-01T00:00:00\2", text, count=1)
    if count != 1:
        raise RuntimeError(f"Could not normalize STEP FILE_NAME timestamp: {path}")
    path.write_text(text, encoding="latin-1")

def generate_two_part_mm() -> Path:
    document = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(document.Main())
    base = add_part(shape_tool, color_tool, "BasePart", (20, 10, 5), (0.8, 0.2, 0.1))
    offset = add_part(shape_tool, color_tool, "OffsetPart", (10, 6, 4), (0.1, 0.4, 0.9))
    assembly = shape_tool.NewShape()
    set_name(assembly, "TwoPartAssembly")
    shape_tool.AddComponent(assembly, base, translation(0, 0, 0))
    shape_tool.AddComponent(assembly, offset, translation(50, 20, 10))
    shape_tool.UpdateAssemblies()
    path = OUT / "two_part_mm.step"
    write_document(document, path)
    return path


def generate_single_part_m() -> Path:
    document = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    # Encode metre-valued coordinates in the file's declared SI length unit.
    # The raw numeric values are 0.02 x 0.01 x 0.005 and are explicitly metres.
    add_part(shape_tool, None, "MeterPart", (0.02, 0.01, 0.005), None)
    path = OUT / "single_part_m.step"
    write_document(document, path)
    text = path.read_text(encoding="latin-1")
    marker = "SI_UNIT(.MILLI.,.METRE.)"
    if marker not in text:
        raise RuntimeError("Could not find the expected millimetre unit declaration to convert the self-authored metre fixture")
    path.write_text(text.replace(marker, "SI_UNIT($,.METRE.)"), encoding="latin-1")
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = [generate_two_part_mm(), generate_single_part_m()]
    records = {}
    for path in files:
        data = path.read_bytes()
        records[path.name] = {"size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    manifest = {
        "schema_version": 1,
        "fixture_origin": "self-authored test geometry; not a vendor robot model",
        "generator": "scripts/generate_c00_fixtures.py",
        "kernel_distribution": "cadquery-ocp-novtk",
        "kernel_version": importlib.metadata.version("cadquery-ocp-novtk"),
        "models": {
            "two_part_mm.step": {
                "source_unit": "mm",
                "root_name": "TwoPartAssembly",
                "part_count": 2,
                "parts": [
                    {"name": "BasePart", "dimensions_mm": [20, 10, 5], "translation_mm": [0, 0, 0], "color_rgb": [0.8, 0.2, 0.1]},
                    {"name": "OffsetPart", "dimensions_mm": [10, 6, 4], "translation_mm": [50, 20, 10], "color_rgb": [0.1, 0.4, 0.9]}
                ]
            },
            "single_part_m.step": {
                "source_unit": "m",
                "root_name": "MeterPart",
                "part_count": 1,
                "parts": [
                    {"name": "MeterPart", "dimensions_m": [0.02, 0.01, 0.005], "translation_m": [0, 0, 0], "color_rgb": None}
                ]
            }
        },
        "files": records
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "generated", "kernel_version": manifest["kernel_version"], "files": records}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
