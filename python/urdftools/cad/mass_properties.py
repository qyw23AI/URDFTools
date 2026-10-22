"""CAD B-rep mass properties with explicit density, frame transforms and parallel-axis aggregation."""
from __future__ import annotations

import hashlib
import importlib.metadata
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer

try:
    from OCP.collections import Sequence_TCollection_AsciiString
except ImportError:
    from OCP.TCollection import TCollection_AsciiString as Sequence_TCollection_AsciiString

from .step2urdf_adapter import load_step
from .step_reader import STEP2URDF_ADAPTER_COMMIT, STEP2URDF_ADAPTER_VERSION


class MassPropertiesError(ValueError):
    """A CAD solid or material assignment is invalid."""


def _density(value: float | None) -> float | None:
    if value is None:
        return None
    density = float(value)
    if not math.isfinite(density) or density <= 0:
        raise MassPropertiesError("Material density must be a finite positive value in kg/m^3; use None for unknown.")
    return density


def _solid_shapes(shape) -> list:
    if shape is None or shape.IsNull():
        return []
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    solids = []
    while explorer.More():
        solids.append(explorer.Current())
        explorer.Next()
    return solids


def _matrix_of_inertia(props: GProp_GProps) -> np.ndarray:
    matrix = props.MatrixOfInertia()
    values = np.array([[float(matrix.Value(row, col)) for col in range(1, 4)] for row in range(1, 4)], dtype=float)
    return (values + values.T) * 0.5


def calculate_solid_mass_properties(
    shape,
    density_kg_m3: float | None,
    *,
    name: str = "solid",
    approximate: bool = False,
) -> dict[str, Any]:
    """Calculate properties from closed STEP B-rep solids only.

    Open shells, approximate adapter fallback geometry and meshes are never assigned
    fabricated mass or inertia. Lengths in the OCP kernel are mm.
    """
    density = _density(density_kg_m3)
    base = {
        "name": name,
        "density_kg_m3": density,
        "volume_mm3": None,
        "volume_m3": None,
        "center_of_mass_m": None,
        "mass_kg": None,
        "inertia_com_kg_m2": None,
        "status": "unknown",
        "warnings": [],
    }
    if approximate:
        base["status"] = "unsupported_approximate_geometry"
        base["warnings"].append("approximate_geometry_not_used_for_mass")
        if density is None:
            base["warnings"].append("material_density_missing")
        return base

    solids = _solid_shapes(shape)
    if not solids or any(not BRepCheck_Analyzer(solid).IsValid() for solid in solids):
        base["status"] = "unsupported_geometry"
        base["warnings"].append("closed_valid_brep_solid_required")
        if density is None:
            base["warnings"].append("material_density_missing")
        return base

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    volume_mm3 = float(props.Mass())
    if not math.isfinite(volume_mm3) or volume_mm3 <= 0:
        base["status"] = "unsupported_geometry"
        base["warnings"].append("non_positive_or_invalid_solid_volume")
        if density is None:
            base["warnings"].append("material_density_missing")
        return base

    center = props.CentreOfMass()
    center_m = [float(center.X()) / 1000.0, float(center.Y()) / 1000.0, float(center.Z()) / 1000.0]
    base["volume_mm3"] = volume_mm3
    base["volume_m3"] = volume_mm3 * 1e-9
    base["center_of_mass_m"] = center_m

    if density is None:
        base["status"] = "missing_density"
        base["warnings"].append("material_density_missing")
        return base

    inertia_geom_mm5 = _matrix_of_inertia(props)
    # GProp_GProps uses unit density and millimetre geometry: mm^5 * kg/m^3 * 1e-15 = kg m^2.
    inertia_kg_m2 = inertia_geom_mm5 * density * 1e-15
    base["mass_kg"] = base["volume_m3"] * density
    base["inertia_com_kg_m2"] = inertia_kg_m2.tolist()
    base["status"] = "known"
    return base


def _rotation_matrix(value: Sequence[Sequence[float]]) -> np.ndarray:
    rotation = np.asarray(value, dtype=float)
    if rotation.shape != (3, 3) or not np.isfinite(rotation).all():
        raise MassPropertiesError("Rotation must be a finite 3x3 matrix.")
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6, rtol=0):
        raise MassPropertiesError("Rotation matrix must be orthonormal.")
    if not math.isclose(float(np.linalg.det(rotation)), 1.0, abs_tol=1e-6):
        raise MassPropertiesError("Rotation matrix must be right-handed with determinant +1.")
    return rotation


def rotate_inertia_tensor(inertia_kg_m2: Sequence[Sequence[float]], rotation: Sequence[Sequence[float]]) -> list[list[float]]:
    """Rotate a COM inertia tensor from local axes into world axes: I_world = R I_local R^T."""
    inertia = np.asarray(inertia_kg_m2, dtype=float)
    if inertia.shape != (3, 3) or not np.isfinite(inertia).all():
        raise MassPropertiesError("Inertia tensor must be a finite 3x3 matrix.")
    inertia = (inertia + inertia.T) * 0.5
    r = _rotation_matrix(rotation)
    return (r @ inertia @ r.T).tolist()


def transform_mass_properties(local: Mapping[str, Any], transform_4x4_m: Sequence[Sequence[float]]) -> dict[str, Any]:
    """Transform local COM and inertia into world coordinates using a metre-based 4x4 transform."""
    transform = np.asarray(transform_4x4_m, dtype=float)
    if transform.shape != (4, 4) or not np.isfinite(transform).all():
        raise MassPropertiesError("Transform must be a finite 4x4 matrix.")
    if not np.allclose(transform[3], [0, 0, 0, 1], atol=1e-8, rtol=0):
        raise MassPropertiesError("Transform bottom row must be [0, 0, 0, 1].")
    rotation = _rotation_matrix(transform[:3, :3])
    translation = transform[:3, 3]
    result = dict(local)
    center = local.get("center_of_mass_m")
    inertia = local.get("inertia_com_kg_m2")
    result["center_of_mass_local_m"] = list(center) if center is not None else None
    result["inertia_com_local_kg_m2"] = [list(row) for row in inertia] if inertia is not None else None
    result["center_of_mass_m"] = (rotation @ np.asarray(center, dtype=float) + translation).tolist() if center is not None else None
    result["inertia_com_kg_m2"] = rotate_inertia_tensor(inertia, rotation) if inertia is not None else None
    result["transform_4x4_m"] = transform.tolist()
    return result


def _source_units(path: Path) -> dict[str, Any]:
    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise MassPropertiesError(f"OpenCascade could not read STEP units from {path.name}")
    lengths = Sequence_TCollection_AsciiString()
    angles = Sequence_TCollection_AsciiString()
    solid_angles = Sequence_TCollection_AsciiString()
    reader.FileUnits(lengths, angles, solid_angles)
    names = sorted({lengths.Value(index).ToCString().strip().lower() for index in range(1, lengths.Length() + 1)})
    map_unit = {"millimetre": ("mm", 0.001), "millimeter": ("mm", 0.001), "metre": ("m", 1.0), "meter": ("m", 1.0)}
    normalized = {map_unit[name][0] for name in names if name in map_unit}
    scales = {map_unit[name][1] for name in names if name in map_unit}
    if len(names) == 1 and len(normalized) == 1 and len(scales) == 1:
        unit, scale = next(iter(normalized)), next(iter(scales))
        status = "recognized"
    else:
        unit, scale, status = ("mixed" if len(names) > 1 else "unknown"), None, "ambiguous_or_unsupported"
    return {
        "source_length_units": names,
        "source_length_unit": unit,
        "source_unit_scale_to_m": scale,
        "kernel_length_unit": "mm",
        "output_length_unit": "m",
        "unit_status": status,
    }


def _transform_of_shape(shape) -> tuple[list[list[float]], list[list[float]]]:
    transform = shape.Location().Transformation()
    matrix_mm = [[float(transform.Value(row, col)) for col in range(1, 5)] for row in range(1, 4)]
    matrix_m = [row[:3] + [row[3] / 1000.0] for row in matrix_mm]
    matrix_mm.append([0.0, 0.0, 0.0, 1.0])
    matrix_m.append([0.0, 0.0, 0.0, 1.0])
    return matrix_mm, matrix_m


def aggregate_mass_properties(parts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate part COM inertias into an assembly COM frame using the parallel-axis theorem."""
    if not parts:
        raise MassPropertiesError("At least one CAD part is required for assembly aggregation.")
    known_volumes = [float(part["volume_m3"]) for part in parts if part.get("volume_m3") is not None]
    volume_complete = len(known_volumes) == len(parts)
    known = [part for part in parts if part.get("mass_kg") is not None and part.get("center_of_mass_m") is not None and part.get("inertia_com_kg_m2") is not None]
    known_ids = {id(part) for part in known}
    unknown = [str(part.get("name", "part")) for part in parts if id(part) not in known_ids]
    known_masses = [float(part["mass_kg"]) for part in known]
    known_mass_subtotal = float(sum(known_masses)) if known else None
    warnings = sorted({warning for part in parts for warning in part.get("warnings", [])})

    if len(known) != len(parts) or known_mass_subtotal is None or known_mass_subtotal <= 0:
        warnings.append("assembly_mass_incomplete")
        return {
            "mass_complete": False,
            "volume_complete": volume_complete,
            "total_volume_m3": float(sum(known_volumes)) if volume_complete else None,
            "known_volume_subtotal_m3": float(sum(known_volumes)) if known_volumes else None,
            "known_mass_subtotal_kg": known_mass_subtotal,
            "known_mass_part_count": len(known),
            "total_mass_kg": None,
            "center_of_mass_m": None,
            "inertia_about_total_com_kg_m2": None,
            "unknown_parts": unknown,
            "warnings": sorted(set(warnings)),
        }

    total_mass = known_mass_subtotal
    center = sum((float(part["mass_kg"]) * np.asarray(part["center_of_mass_m"], dtype=float) for part in known), np.zeros(3)) / total_mass
    total_inertia = np.zeros((3, 3), dtype=float)
    for part in known:
        mass = float(part["mass_kg"])
        displacement = np.asarray(part["center_of_mass_m"], dtype=float) - center
        inertia_com = np.asarray(part["inertia_com_kg_m2"], dtype=float)
        parallel_axis = mass * ((float(displacement @ displacement) * np.eye(3)) - np.outer(displacement, displacement))
        total_inertia += inertia_com + parallel_axis
    return {
        "mass_complete": True,
        "volume_complete": volume_complete,
        "total_volume_m3": float(sum(known_volumes)) if volume_complete else None,
        "known_volume_subtotal_m3": float(sum(known_volumes)) if known_volumes else None,
        "known_mass_subtotal_kg": total_mass,
        "known_mass_part_count": len(known),
        "total_mass_kg": total_mass,
        "center_of_mass_m": center.tolist(),
        "inertia_about_total_com_kg_m2": ((total_inertia + total_inertia.T) * 0.5).tolist(),
        "unknown_parts": [],
        "warnings": sorted(set(warnings)),
    }


def compute_step_mass_properties(
    path: str | Path,
    densities_by_part: Mapping[str, float | None] | None = None,
    *,
    default_density_kg_m3: float | None = None,
) -> dict[str, Any]:
    """Compute mass/COM/inertia from STEP B-rep solids, never from URDF visual/collision meshes."""
    source = Path(path).expanduser()
    if source.suffix.lower() not in {".step", ".stp"}:
        raise MassPropertiesError("Mass properties require a STEP B-rep file (.step or .stp); visual/collision meshes are not physical mass sources.")
    if not source.is_file() or source.stat().st_size == 0:
        raise MassPropertiesError(f"STEP file does not exist or is empty: {source}")
    default_density = _density(default_density_kg_m3)
    assignments = dict(densities_by_part or {})
    for name, density in assignments.items():
        if not isinstance(name, str) or not name.strip():
            raise MassPropertiesError("Material assignment keys must be non-empty exact part names.")
        _density(density)
    units = _source_units(source)
    adapter_parts = load_step(str(source))
    if not adapter_parts:
        raise MassPropertiesError("STEP adapter returned no CAD parts.")
    part_names = {part.name for part in adapter_parts}
    unmatched_density_assignments = sorted(set(assignments) - part_names)

    reports = []
    for part in adapter_parts:
        if part.name in assignments:
            density = _density(assignments[part.name])
            density_source = "per_part" if density is not None else "missing"
        elif default_density is not None:
            density = default_density
            density_source = "explicit_default"
        else:
            density = None
            density_source = "missing"
        props = calculate_solid_mass_properties(part.shape, density, name=part.name, approximate=bool(part.approximate))
        matrix_mm, matrix_m = _transform_of_shape(part.shape)
        bbox_dimensions_m = [float(part.bbox_max[i] - part.bbox_min[i]) / 1000.0 for i in range(3)] if part.bbox_min is not None and part.bbox_max is not None else None
        props.update({
            "density_source": density_source,
            "color_rgb": list(part.color) if part.color is not None else None,
            "bbox_dimensions_m": bbox_dimensions_m,
            "world_transform_4x4_mm": matrix_mm,
            "world_transform_4x4_m": matrix_m,
        })
        if units["unit_status"] != "recognized":
            props["warnings"].append("source_length_unit_ambiguous_or_unsupported")
        reports.append(props)

    assembly = aggregate_mass_properties(reports)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    warnings = sorted({warning for part in reports for warning in part["warnings"]} | set(assembly["warnings"]))
    if unmatched_density_assignments:
        warnings = sorted(set(warnings) | {"unmatched_density_assignments"})
    return {
        "schema_version": 1,
        "status": "ready",
        "source": {"path": str(source), "filename": source.name, "size_bytes": source.stat().st_size, "sha256": digest},
        "units": units,
        "parts": reports,
        "assembly": assembly,
        "unmatched_density_assignments": unmatched_density_assignments,
        "kernel": {
            "name": "OpenCascade via OCP",
            "distribution": "cadquery-ocp-novtk",
            "version": importlib.metadata.version("cadquery-ocp-novtk"),
            "internal_length_unit": "mm",
            "output_length_unit": "m",
        },
        "adapter": {
            "name": "step2urdf",
            "version": STEP2URDF_ADAPTER_VERSION,
            "commit": STEP2URDF_ADAPTER_COMMIT,
            "module": "urdftools.cad.step2urdf_adapter.load_step",
            "part_count": len(reports),
        },
        "warnings": warnings,
    }
