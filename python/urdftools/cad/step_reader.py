"""Assembly-aware STEP inspection with source-unit, transform, color and provenance reporting.

All geometry coordinates returned by OpenCascade and the pinned step2urdf adapter
are in millimetres; exported SI translations and bounds are explicitly converted to metres.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
from pathlib import Path
from typing import Any

from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
from OCP.TDF import TDF_Label
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_ColorGen, XCAFDoc_ColorSurf, XCAFDoc_ColorTool, XCAFDoc_DocumentTool, XCAFDoc_ShapeTool
from OCP.Quantity import Quantity_Color

try:
    from OCP.collections import Sequence_TDF_Label, Sequence_TCollection_AsciiString
except ImportError:  # compatibility with older OCP builds
    from OCP.TDF import TDF_LabelSequence as Sequence_TDF_Label
    from OCP.TCollection import TCollection_AsciiString as Sequence_TCollection_AsciiString

from .step2urdf_adapter import _label_color, _label_name, _static, load_step, sanitize

STEP2URDF_ADAPTER_VERSION = "0.1.0"
STEP2URDF_ADAPTER_COMMIT = "3845072d29c0cdbd12a9b3c65808440163e32130"
SUPPORTED_EXTENSIONS = {".step", ".stp"}
LENGTH_UNIT_TO_METRE = {"millimetre": ("mm", 0.001), "millimeter": ("mm", 0.001), "metre": ("m", 1.0), "meter": ("m", 1.0)}


class StepImportError(ValueError):
    """A STEP file could not be safely or completely inspected."""


def _unit_names(reader: STEPCAFControl_Reader) -> list[str]:
    length_units = Sequence_TCollection_AsciiString()
    angle_units = Sequence_TCollection_AsciiString()
    solid_angle_units = Sequence_TCollection_AsciiString()
    reader.Reader().FileUnits(length_units, angle_units, solid_angle_units)
    return sorted({length_units.Value(index).ToCString().strip().lower()
                   for index in range(1, length_units.Length() + 1)})


def _unit_summary(names: list[str]) -> dict[str, Any]:
    recognized = {LENGTH_UNIT_TO_METRE[name][0] for name in names if name in LENGTH_UNIT_TO_METRE}
    scale_values = {LENGTH_UNIT_TO_METRE[name][1] for name in names if name in LENGTH_UNIT_TO_METRE}
    if len(names) == 1 and len(recognized) == 1 and len(scale_values) == 1:
        unit = next(iter(recognized))
        scale = next(iter(scale_values))
        return {
            "source_length_units": names,
            "source_length_unit": unit,
            "source_unit_scale_to_m": scale,
            "kernel_length_unit": "mm",
            "output_length_unit": "m",
            "kernel_to_output_scale": 0.001,
            "unit_status": "recognized",
        }
    return {
        "source_length_units": names,
        "source_length_unit": "mixed" if len(names) > 1 else "unknown",
        "source_unit_scale_to_m": None,
        "kernel_length_unit": "mm",
        "output_length_unit": "m",
        "kernel_to_output_scale": 0.001,
        "unit_status": "ambiguous_or_unsupported",
    }


def _transform_matrix(location: TopLoc_Location) -> tuple[list[list[float]], list[list[float]], list[float]]:
    transform = location.Transformation()
    matrix_mm = [[float(transform.Value(row, col)) for col in range(1, 5)] for row in range(1, 4)]
    matrix_m = [row[:3] + [row[3] / 1000.0] for row in matrix_mm]
    matrix_mm.append([0.0, 0.0, 0.0, 1.0])
    matrix_m.append([0.0, 0.0, 0.0, 1.0])
    translation_m = [matrix_m[row][3] for row in range(3)]
    return matrix_mm, matrix_m, translation_m


def _bounds(shape) -> dict[str, Any] | None:
    if shape.IsNull():
        return None
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    if box.IsVoid():
        return None
    low, high = box.CornerMin(), box.CornerMax()
    minimum_mm = [float(low.X()), float(low.Y()), float(low.Z())]
    maximum_mm = [float(high.X()), float(high.Y()), float(high.Z())]
    dimensions_mm = [max(0.0, maximum_mm[i] - minimum_mm[i]) for i in range(3)]
    return {
        "min_mm": minimum_mm,
        "max_mm": maximum_mm,
        "dimensions_mm": dimensions_mm,
        "dimensions_m": [value / 1000.0 for value in dimensions_mm],
    }


def _walk_tree(shape_tool, color_tool, label, world_location: TopLoc_Location,
               parent_path: list[str], inherited_color=None, instance_label=None,
               fallback_name: str = "part") -> dict[str, Any] | None:
    definition_name = _label_name(label)
    instance_name = _label_name(instance_label) if instance_label is not None else ""
    name = instance_name or definition_name or fallback_name
    instance_color = _label_color(color_tool, instance_label) if instance_label is not None else None
    definition_color = _label_color(color_tool, label)
    if instance_color is not None:
        color, color_source = instance_color, "instance"
    elif definition_color is not None:
        color, color_source = definition_color, "definition"
    elif inherited_color is not None:
        color, color_source = inherited_color, "inherited"
    else:
        color, color_source = None, "missing"

    matrix_mm, matrix_m, translation_m = _transform_matrix(world_location)
    path_parts = parent_path + [name]
    node: dict[str, Any] = {
        "name": name,
        "kind": "assembly" if _static(XCAFDoc_ShapeTool, "IsAssembly")(label) else "part",
        "path": "/".join(path_parts),
        "color_rgb": list(color) if color is not None else None,
        "color_source": color_source,
        "transform_4x4_mm": matrix_mm,
        "transform_4x4_m": matrix_m,
        "world_translation_m": translation_m,
        "children": [],
    }

    if node["kind"] == "assembly":
        components = Sequence_TDF_Label()
        _static(XCAFDoc_ShapeTool, "GetComponents")(label, components, False)
        seen_names: dict[str, int] = {}
        for index in range(1, components.Length() + 1):
            component = components.Value(index)
            referred = TDF_Label()
            if not _static(XCAFDoc_ShapeTool, "GetReferredShape")(component, referred):
                raise StepImportError(f"STEP assembly component {index} in {node['path']} has no referred shape")
            component_name = _label_name(component) or _label_name(referred) or f"part_{index}"
            seen_names[component_name] = seen_names.get(component_name, 0) + 1
            if seen_names[component_name] > 1:
                component_name = f"{component_name}#{seen_names[component_name]}"
            component_location = _static(XCAFDoc_ShapeTool, "GetLocation")(component)
            child_world_location = world_location.Multiplied(component_location)
            child = _walk_tree(shape_tool, color_tool, referred, child_world_location,
                               path_parts, color, component, component_name)
            if child is not None:
                node["children"].append(child)
        return node

    shape = _static(XCAFDoc_ShapeTool, "GetShape")(label)
    if shape.IsNull():
        return None
    world_shape = shape.Moved(world_location)
    node["bounds"] = _bounds(world_shape)
    node["warnings"] = [] if color is not None else ["missing_color"]
    return node


def _flatten_parts(node: dict[str, Any]) -> list[dict[str, Any]]:
    if node["kind"] == "part":
        return [node]
    result: list[dict[str, Any]] = []
    for child in node["children"]:
        result.extend(_flatten_parts(child))
    return result


def inspect_step(path: str | Path) -> dict[str, Any]:
    """Read a local STEP/STP file and return JSON-serializable assembly metadata."""
    source = Path(path).expanduser()
    if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise StepImportError(f"Unsupported CAD extension {source.suffix!r}; expected .step or .stp")
    if not source.is_file():
        raise StepImportError(f"STEP file does not exist or is not a regular file: {source}")
    if source.stat().st_size == 0:
        raise StepImportError("STEP file is empty")

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetColorMode(True)
    if reader.ReadFile(str(source)) != IFSelect_RetDone:
        raise StepImportError(f"OpenCascade could not read STEP file: {source.name}")
    units = _unit_summary(_unit_names(reader))
    document = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    if not reader.Transfer(document):
        raise StepImportError(f"OpenCascade could not transfer STEP data: {source.name}")

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(document.Main())
    roots = Sequence_TDF_Label()
    shape_tool.GetFreeShapes(roots)
    if roots.Length() == 0:
        raise StepImportError("STEP file contains no free assembly or part shapes")

    hierarchy_roots: list[dict[str, Any]] = []
    for index in range(1, roots.Length() + 1):
        label = roots.Value(index)
        name = _label_name(label) or f"root_{index}"
        node = _walk_tree(shape_tool, color_tool, label, TopLoc_Location(), [], None, None, name)
        if node is not None:
            hierarchy_roots.append(node)
    parts = [part for root in hierarchy_roots for part in _flatten_parts(root)]
    if not parts:
        raise StepImportError("STEP file contains no usable part geometry")

    # Cross-check the assembly-aware reader against the pinned step2urdf part adapter.
    # The adapter intentionally returns a flat part list; it is not used as the hierarchy source.
    adapter_parts = load_step(str(source))
    # Some exporters give assembly instances generic NAUO labels while the flat
    # reader retains the product names. Compare the actual placed geometry in
    # traversal order before treating that naming difference as a mismatch.
    def same_bounds(tree_part: dict[str, Any], adapter_part: Any) -> bool:
        bounds = tree_part.get("bounds")
        if not bounds or adapter_part.bbox_min is None or adapter_part.bbox_max is None:
            return False
        return all(abs(float(actual) - float(expected)) <= 1e-4
                   for key, values in (("min_mm", adapter_part.bbox_min), ("max_mm", adapter_part.bbox_max))
                   for actual, expected in zip(bounds[key], values))

    adapter_status = "matched" if len(parts) == len(adapter_parts) and all(
        same_bounds(tree, adapter) for tree, adapter in zip(parts, adapter_parts)
    ) else "mismatch"
    adapter_summaries = []
    for part in adapter_parts:
        bounds = None
        if getattr(part, "bbox_min", None) is not None and getattr(part, "bbox_max", None) is not None:
            dimensions_mm = [float(part.bbox_max[i] - part.bbox_min[i]) for i in range(3)]
            bounds = {
                "min_mm": [float(v) for v in part.bbox_min.tolist()],
                "max_mm": [float(v) for v in part.bbox_max.tolist()],
                "dimensions_m": [v / 1000.0 for v in dimensions_mm],
            }
        adapter_summaries.append({
            "name": part.name,
            "color_rgb": list(part.color) if part.color is not None else None,
            "bounds": bounds,
            "volume_mm3": float(part.volume),
            "geometry_approximate": bool(getattr(part, "approximate", False)),
        })

    warnings: list[str] = []
    if units["unit_status"] != "recognized":
        warnings.append("source_length_unit_ambiguous_or_unsupported")
    if adapter_status != "matched":
        warnings.append("step2urdf_adapter_part_list_mismatch")
    missing_color_count = sum(part["color_rgb"] is None for part in parts)
    if missing_color_count:
        warnings.append("one_or_more_parts_have_no_explicit_or_inherited_color")

    return {
        "schema_version": 1,
        "status": "ready",
        "source": {
            "path": str(source),
            "filename": source.name,
            "size_bytes": source.stat().st_size,
            "sha256": digest,
        },
        "units": units,
        "assembly_roots": hierarchy_roots,
        "counts": {
            "root_count": len(hierarchy_roots),
            "assembly_count": sum(1 for root in hierarchy_roots for node in _walk_nodes(root) if node["kind"] == "assembly"),
            "part_instance_count": len(parts),
            "colored_part_count": len(parts) - missing_color_count,
            "missing_color_count": missing_color_count,
        },
        "parts": [{
            "name": part["name"],
            "path": part["path"],
            "color_rgb": part["color_rgb"],
            "color_source": part["color_source"],
            "transform_4x4_mm": part["transform_4x4_mm"],
            "transform_4x4_m": part["transform_4x4_m"],
            "world_translation_m": part["world_translation_m"],
            "bounds": part.get("bounds"),
            "warnings": part["warnings"],
        } for part in parts],
        "adapter": {
            "name": "step2urdf",
            "version": STEP2URDF_ADAPTER_VERSION,
            "commit": STEP2URDF_ADAPTER_COMMIT,
            "module": "urdftools.cad.step2urdf_adapter.load_step",
            "status": adapter_status,
            "part_count": len(adapter_parts),
            "parts": adapter_summaries,
        },
        "kernel": {
            "name": "OpenCascade via OCP",
            "distribution": "cadquery-ocp-novtk",
            "version": importlib.metadata.version("cadquery-ocp-novtk"),
            "internal_length_unit": "mm",
            "output_length_unit": "m",
        },
        "warnings": warnings,
    }


def _walk_nodes(node: dict[str, Any]):
    yield node
    for child in node.get("children", []):
        yield from _walk_nodes(child)
