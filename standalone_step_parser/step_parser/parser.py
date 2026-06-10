from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Iterable

from .models import BoundingBox, HoleCandidate, MeasuredValue, RiskItem, SCHEMA_VERSION, SourceRef


MM_UNIT = "mm"
MM2_UNIT = "mm2"
MM3_UNIT = "mm3"
KG_UNIT = "kg"


@dataclass(frozen=True)
class ShapeMetrics:
    backend: str
    bounding_box: BoundingBox
    volume: float | None
    surface_area: float | None
    face_count: int | None
    edge_count: int | None
    face_type_counts: dict[str, int]
    edge_type_counts: dict[str, int]
    cylindrical_area_ratio: float
    circular_edge_ratio: float
    cylindrical_faces: list[dict[str, float | None]]
    circular_edges: list[dict[str, float | None]]
    edge_records: list[dict[str, float | str | None]]
    profile_wires: list[dict[str, float | int | str | None]]
    counterbore_candidates: list[dict[str, float | int | None]]
    countersink_candidates: list[dict[str, float | int | None]]
    solid_count: int | None = None
    shell_count: int | None = None
    compound_count: int | None = None


def parse_step_file(
    step_path: str | Path,
    *,
    task_id: str | None = None,
    file_id: str | None = None,
    density: float | None = None,
    density_unit: str = "kg/mm3",
    backend: str = "auto",
) -> dict[str, Any]:
    """Parse one STEP file into geometry features for later pricing analysis."""
    path = Path(step_path)
    resolved_file_id = file_id or path.stem
    source = SourceRef(file_id=resolved_file_id)
    risks: list[RiskItem] = []

    if not path.exists():
        return empty_result(
            path,
            task_id=task_id,
            file_id=resolved_file_id,
            risks=[
                RiskItem("MISSING_STEP", "blocking", "STEP file does not exist.", "step_parser", True, [source])
            ],
        )

    try:
        metrics = load_shape_metrics(path, backend=backend)
    except Exception as exc:
        return empty_result(
            path,
            task_id=task_id,
            file_id=resolved_file_id,
            risks=[
                RiskItem(
                    "STEP_PARSE_FAILED",
                    "blocking",
                    f"STEP parsing failed: {exc}",
                    "step_parser",
                    True,
                    [source],
                )
            ],
        )

    net_weight = calculate_net_weight(metrics.volume, density, density_unit)
    hole_instances = detect_hole_instances(metrics.profile_wires)
    holes = build_hole_candidates(
        hole_instances=hole_instances,
        counterbore_candidates=metrics.counterbore_candidates,
        countersink_candidates=metrics.countersink_candidates,
        bbox=metrics.bounding_box,
        cylindrical_faces=metrics.cylindrical_faces,
        source=source,
    )
    if not holes:
        holes = detect_holes_from_cylinders(metrics.cylindrical_faces, metrics.bounding_box, source)
    hole_groups = detect_hole_groups(hole_instances, source)
    counterbore_candidates = format_counterbore_candidates(metrics.counterbore_candidates, source)
    countersink_candidates = format_countersink_candidates(metrics.countersink_candidates, source)
    slot_candidates = detect_slot_candidates(metrics.profile_wires, source)
    slot_count = sum(slot["count"] for slot in slot_candidates)
    complexity = calculate_complexity(metrics, holes, slot_count=slot_count)
    part_type_candidates = classify_part_type(metrics, complexity)
    profile_summary = calculate_profile_summary(metrics)
    risks.extend(
        geometry_risks(
            metrics,
            part_type_candidates,
            complexity,
            holes,
            slot_candidates,
            source,
        )
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "file_id": resolved_file_id,
        "source_file": str(path),
        "backend": metrics.backend,
        "bounding_box": metrics.bounding_box.to_dict(),
        "volume": MeasuredValue(round_float(metrics.volume), MM3_UNIT, source).to_dict(),
        "surface_area": MeasuredValue(round_float(metrics.surface_area), MM2_UNIT, source).to_dict(),
        "net_weight": {
            "value": net_weight,
            "unit": KG_UNIT if net_weight is not None else None,
            "density": density,
            "density_unit": density_unit if density is not None else None,
            "source": source.to_dict(),
        },
        "part_type_candidates": part_type_candidates,
        "holes": [hole.to_dict() for hole in holes],
        "hole_summary": summarize_holes(holes),
        "hole_groups": hole_groups,
        "counterbore_candidates": counterbore_candidates,
        "countersink_candidates": countersink_candidates,
        "slot_candidates": slot_candidates,
        "profile_summary": profile_summary,
        "complexity": complexity,
        "geometry_risks": [risk.to_dict() for risk in risks],
    }


def load_shape_metrics(path: Path, *, backend: str) -> ShapeMetrics:
    if backend not in {"auto", "pythonocc", "cadquery"}:
        raise ValueError("backend must be one of: auto, pythonocc, cadquery")

    errors: list[str] = []
    if backend in {"auto", "pythonocc"}:
        try:
            return load_with_pythonocc(path)
        except Exception as exc:
            if backend == "pythonocc":
                raise
            errors.append(f"pythonocc: {exc}")

    if backend in {"auto", "cadquery"}:
        try:
            return load_with_cadquery(path)
        except Exception as exc:
            if backend == "cadquery":
                raise
            errors.append(f"cadquery: {exc}")

    raise RuntimeError("; ".join(errors) or "No STEP backend is available.")


def load_with_pythonocc(path: Path) -> ShapeMetrics:
    from OCC.Core.Bnd import Bnd_Box
    from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
    from OCC.Core.BRepBndLib import brepbndlib_Add
    from OCC.Core.BRepGProp import brepgprop_SurfaceProperties, brepgprop_VolumeProperties
    from OCC.Core.GProp import GProp_GProps
    from OCC.Core.GeomAbs import GeomAbs_Cylinder
    from OCC.Core.IFSelect import IFSelect_RetDone
    from OCC.Core.STEPControl import STEPControl_Reader
    from OCC.Core.TopAbs import TopAbs_COMPOUND, TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
    from OCC.Core.TopExp import TopExp_Explorer

    reader = STEPControl_Reader()
    status = reader.ReadFile(str(path))
    if status != IFSelect_RetDone:
        raise RuntimeError("STEP reader did not return IFSelect_RetDone.")
    reader.TransferRoots()
    shape = reader.OneShape()

    box = Bnd_Box()
    brepbndlib_Add(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    bounding_box = BoundingBox(
        length=round_float(abs(xmax - xmin)),
        width=round_float(abs(ymax - ymin)),
        height=round_float(abs(zmax - zmin)),
    )

    volume_props = GProp_GProps()
    brepgprop_VolumeProperties(shape, volume_props)
    volume = volume_props.Mass()

    surface_props = GProp_GProps()
    brepgprop_SurfaceProperties(shape, surface_props)
    surface_area = surface_props.Mass()

    face_count = count_topology(shape, TopAbs_FACE, TopExp_Explorer)
    edge_count = count_topology(shape, TopAbs_EDGE, TopExp_Explorer)
    solid_count = count_topology(shape, TopAbs_SOLID, TopExp_Explorer)
    shell_count = count_topology(shape, TopAbs_SHELL, TopExp_Explorer)
    compound_count = count_topology(shape, TopAbs_COMPOUND, TopExp_Explorer)
    cylindrical_faces = collect_pythonocc_cylinders(shape, TopAbs_FACE, TopExp_Explorer, BRepAdaptor_Surface, GeomAbs_Cylinder)

    return ShapeMetrics(
        backend="pythonocc",
        bounding_box=bounding_box,
        volume=volume,
        surface_area=surface_area,
        face_count=face_count,
        edge_count=edge_count,
        face_type_counts={},
        edge_type_counts={},
        cylindrical_area_ratio=0.0,
        circular_edge_ratio=0.0,
        cylindrical_faces=cylindrical_faces,
        circular_edges=[],
        edge_records=[],
        profile_wires=[],
        counterbore_candidates=[],
        countersink_candidates=[],
        solid_count=solid_count,
        shell_count=shell_count,
        compound_count=compound_count,
    )


def count_topology(shape: Any, topology_kind: Any, explorer_cls: Any) -> int:
    explorer = explorer_cls(shape, topology_kind)
    count = 0
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def collect_pythonocc_cylinders(
    shape: Any,
    face_kind: Any,
    explorer_cls: Any,
    surface_adapter_cls: Any,
    cylinder_kind: Any,
) -> list[dict[str, float | None]]:
    cylinders: list[dict[str, float | None]] = []
    explorer = explorer_cls(shape, face_kind)
    while explorer.More():
        face = explorer.Current()
        try:
            surface = surface_adapter_cls(face)
            if surface.GetType() == cylinder_kind:
                radius = float(surface.Cylinder().Radius())
                area = face_area(face)
                depth = area / (2 * math.pi * radius) if radius > 0 and area else None
                cylinders.append({"radius": radius, "diameter": radius * 2, "depth": depth, "area": area})
        except Exception:
            pass
        explorer.Next()
    return cylinders


def face_area(face: Any) -> float | None:
    from OCC.Core.BRepGProp import brepgprop_SurfaceProperties
    from OCC.Core.GProp import GProp_GProps

    props = GProp_GProps()
    brepgprop_SurfaceProperties(face, props)
    return float(props.Mass())


def load_with_cadquery(path: Path) -> ShapeMetrics:
    ensure_numpy_legacy_aliases_for_cadquery()
    import cadquery as cq

    imported = cq.importers.importStep(str(path))
    shape = imported.val() if hasattr(imported, "val") else imported
    box = shape.BoundingBox()
    bounding_box = BoundingBox(
        length=round_float(getattr(box, "xlen", None)),
        width=round_float(getattr(box, "ylen", None)),
        height=round_float(getattr(box, "zlen", None)),
    )
    faces = list(shape.Faces())
    edges = list(shape.Edges())
    cylinders = collect_cadquery_cylinders(faces)
    circular_edges = collect_cadquery_circular_edges(edges)
    edge_records = collect_cadquery_edge_records(edges)
    profile_wires = collect_cadquery_top_face_profiles(faces)
    counterbore_candidates = collect_counterbore_candidates(circular_edges, bounding_box)
    countersink_candidates = collect_countersink_candidates(faces, bounding_box)
    face_type_counts = Counter(str(face.geomType()).upper() for face in faces)
    edge_type_counts = Counter(str(edge.geomType()).upper() for edge in edges)
    cylindrical_area = sum(float(face.get("area") or 0) for face in cylinders)
    surface_area = safe_call(shape, "Area")
    return ShapeMetrics(
        backend="cadquery",
        bounding_box=bounding_box,
        volume=safe_call(shape, "Volume"),
        surface_area=surface_area,
        face_count=len(faces),
        edge_count=len(edges),
        face_type_counts=dict(face_type_counts),
        edge_type_counts=dict(edge_type_counts),
        cylindrical_area_ratio=round_float(cylindrical_area / surface_area, 4) if surface_area else 0.0,
        circular_edge_ratio=round_float(len(circular_edges) / len(edges), 4) if edges else 0.0,
        cylindrical_faces=cylinders,
        circular_edges=circular_edges,
        edge_records=edge_records,
        profile_wires=profile_wires,
        counterbore_candidates=counterbore_candidates,
        countersink_candidates=countersink_candidates,
        solid_count=count_cadquery_items(shape, "Solids"),
        shell_count=count_cadquery_items(shape, "Shells"),
        compound_count=count_cadquery_items(shape, "Compounds"),
    )


def ensure_numpy_legacy_aliases_for_cadquery() -> None:
    import numpy as np

    aliases = {
        "bool8": "bool_",
        "int0": "intp",
        "uint0": "uintp",
        "object0": "object_",
        "str0": "str_",
        "bytes0": "bytes_",
        "void0": "void",
        "float_": "float64",
        "complex_": "complex128",
        "longfloat": "longdouble",
        "longcomplex": "clongdouble",
        "singlecomplex": "complex64",
        "cfloat": "complex128",
        "clongfloat": "clongdouble",
        "string_": "bytes_",
        "unicode_": "str_",
    }
    for alias, target in aliases.items():
        if not hasattr(np, alias) and hasattr(np, target):
            setattr(np, alias, getattr(np, target))


def count_cadquery_items(shape: Any, method_name: str) -> int | None:
    try:
        method = getattr(shape, method_name)
        return len(list(method()))
    except Exception:
        return None


def collect_cadquery_cylinders(faces: Iterable[Any]) -> list[dict[str, float | None]]:
    cylinders: list[dict[str, float | None]] = []
    for face in faces:
        try:
            geom_type = face.geomType()
            if str(geom_type).upper() != "CYLINDER":
                continue
            normal = face.normalAt()
            radius = vector_length(
                getattr(normal, "x", None),
                getattr(normal, "y", None),
                getattr(normal, "z", None),
            )
            area = safe_call(face, "Area")
            depth = area / (2 * math.pi * radius) if radius and area else None
            center = face.Center()
            cylinders.append(
                {
                    "radius": round_float(radius),
                    "diameter": round_float(radius * 2) if radius else None,
                    "depth": round_float(depth),
                    "area": round_float(area),
                    "center_x": round_float(getattr(center, "x", None)),
                    "center_y": round_float(getattr(center, "y", None)),
                    "center_z": round_float(getattr(center, "z", None)),
                }
            )
        except Exception:
            continue
    return cylinders


def vector_length(x: Any, y: Any, z: Any) -> float | None:
    if x is None or y is None or z is None:
        return None
    return math.sqrt(float(x) ** 2 + float(y) ** 2 + float(z) ** 2)


def collect_cadquery_circular_edges(edges: Iterable[Any]) -> list[dict[str, float | None]]:
    circles: list[dict[str, float | None]] = []
    for edge in edges:
        try:
            if str(edge.geomType()).upper() != "CIRCLE":
                continue
            radius = float(edge.radius())
            center = edge.arcCenter()
            length = float(edge.Length())
            arc_fraction = length / (2 * math.pi * radius) if radius > 0 else None
            circles.append(
                {
                    "radius": radius,
                    "diameter": radius * 2,
                    "length": length,
                    "arc_fraction": arc_fraction,
                    "center_x": float(center.x),
                    "center_y": float(center.y),
                    "center_z": float(center.z),
                }
            )
        except Exception:
            continue
    return circles


def collect_cadquery_edge_records(edges: Iterable[Any]) -> list[dict[str, float | str | None]]:
    records: list[dict[str, float | str | None]] = []
    for edge in edges:
        try:
            geom_type = str(edge.geomType()).upper()
            center = edge.arcCenter() if geom_type == "CIRCLE" else edge.Center()
            records.append(
                {
                    "geom_type": geom_type,
                    "length": float(edge.Length()),
                    "center_x": float(center.x),
                    "center_y": float(center.y),
                    "center_z": float(center.z),
                    "radius": float(edge.radius()) if geom_type == "CIRCLE" else None,
                }
            )
        except Exception:
            continue
    return records


def collect_cadquery_top_face_profiles(faces: Iterable[Any]) -> list[dict[str, float | int | str | None]]:
    planar_faces = []
    for face in faces:
        try:
            if str(face.geomType()).upper() != "PLANE":
                continue
            normal = face.normalAt()
            if float(normal.z) > 0.9:
                planar_faces.append(face)
        except Exception:
            continue
    if not planar_faces:
        return []

    top_face = max(planar_faces, key=lambda face: safe_call(face, "Area") or 0)
    profiles: list[dict[str, float | int | str | None]] = []
    profiles.append(profile_wire_record(top_face.outerWire(), "outer"))
    for wire in top_face.innerWires():
        profiles.append(profile_wire_record(wire, "inner"))
    return profiles


def profile_wire_record(wire: Any, kind: str) -> dict[str, float | int | str | None]:
    edges = list(wire.Edges())
    geom_counts = Counter(str(edge.geomType()).upper() for edge in edges)
    center = wire.Center()
    bbox = wire.BoundingBox()
    line_length = 0.0
    arc_length = 0.0
    for edge in edges:
        try:
            edge_type = str(edge.geomType()).upper()
            edge_length = float(edge.Length())
            if edge_type == "LINE":
                line_length += edge_length
            elif edge_type == "CIRCLE":
                arc_length += edge_length
        except Exception:
            continue
    return {
        "kind": kind,
        "length": round_float(wire.Length()),
        "line_length": round_float(line_length),
        "arc_length": round_float(arc_length),
        "edge_count": len(edges),
        "line_count": geom_counts.get("LINE", 0),
        "circle_count": geom_counts.get("CIRCLE", 0),
        "center_x": round_float(center.x),
        "center_y": round_float(center.y),
        "center_z": round_float(center.z),
        "bbox_length": round_float(max(getattr(bbox, "xlen", 0), getattr(bbox, "ylen", 0))),
        "bbox_width": round_float(min(getattr(bbox, "xlen", 0), getattr(bbox, "ylen", 0))),
    }


def detect_holes(metrics: ShapeMetrics, source: SourceRef) -> list[HoleCandidate]:
    hole_instances = detect_hole_instances(metrics.profile_wires)
    holes = summarize_hole_instances_as_candidates(hole_instances, source)
    if holes:
        return holes
    return detect_holes_from_cylinders(metrics.cylindrical_faces, metrics.bounding_box, source)


def detect_hole_instances(profile_wires: list[dict[str, float | int | str | None]]) -> list[dict[str, float]]:
    holes: list[dict[str, float]] = []
    for profile in profile_wires:
        if profile.get("kind") != "inner":
            continue
        if int(profile.get("line_count") or 0) != 0 or int(profile.get("circle_count") or 0) <= 0:
            continue
        length = float(profile.get("length") or 0)
        if length <= 0:
            continue
        diameter = length / math.pi
        holes.append(
            {
                "diameter": round_float(diameter, 1) or 0.0,
                "center_x": float(profile.get("center_x") or 0),
                "center_y": float(profile.get("center_y") or 0),
                "profile_length": length,
            }
        )
    return holes


def build_hole_candidates(
    *,
    hole_instances: list[dict[str, float]],
    counterbore_candidates: list[dict[str, float | int | None]],
    countersink_candidates: list[dict[str, float | int | None]],
    bbox: BoundingBox,
    cylindrical_faces: list[dict[str, float | None]] | None = None,
    source: SourceRef,
) -> list[HoleCandidate]:
    through_depth = through_hole_depth_from_bbox(bbox)
    special_centers = {
        center_key(candidate)
        for candidate in [*counterbore_candidates, *countersink_candidates]
        if center_key(candidate) is not None
    }
    simple_holes = [
        hole
        for hole in hole_instances
        if center_key(hole) not in special_centers
    ]
    return [
        *summarize_counterbore_candidates_as_holes(
            counterbore_candidates,
            through_depth,
            source,
            cylindrical_faces=cylindrical_faces or [],
            bbox=bbox,
        ),
        *summarize_countersink_candidates_as_holes(
            countersink_candidates,
            through_depth,
            source,
            cylindrical_faces=cylindrical_faces or [],
            bbox=bbox,
        ),
        *summarize_hole_instances_as_candidates(
            simple_holes,
            source,
            depth=through_depth,
            bbox=bbox,
            cylindrical_faces=cylindrical_faces or [],
        ),
    ]


def through_hole_depth_from_bbox(bbox: BoundingBox) -> float | None:
    dims = [
        value
        for value in (bbox.length, bbox.width, bbox.height)
        if value is not None and value > 0
    ]
    return round_float(min(dims), 1) if dims else None


def center_key(item: dict[str, Any]) -> tuple[float, float] | None:
    center_x = item.get("center_x")
    center_y = item.get("center_y")
    if center_x is None or center_y is None:
        return None
    return (round(float(center_x), 2), round(float(center_y), 2))


def summarize_hole_instances_as_candidates(
    hole_instances: list[dict[str, float]],
    source: SourceRef,
    *,
    depth: float | None = None,
    bbox: BoundingBox | None = None,
    cylindrical_faces: list[dict[str, float | None]] | None = None,
) -> list[HoleCandidate]:
    grouped: dict[tuple[str, float, float | None], list[dict[str, float]]] = defaultdict(list)
    for hole in hole_instances:
        matched_cylinder = matching_cylinder_for_hole(hole, cylindrical_faces or [])
        inferred_depth = (
            round_float(matched_cylinder.get("depth"), 1)
            if matched_cylinder and matched_cylinder.get("depth") is not None
            else depth
        )
        hole_type = classify_cylinder_hole_type(inferred_depth, bbox)
        grouped[(hole_type, hole["diameter"], inferred_depth)].append(hole)
    holes: list[HoleCandidate] = []
    for (hole_type, diameter, inferred_depth), instances in sorted(grouped.items()):
        holes.append(
            HoleCandidate(
                hole_type=hole_type,
                diameter=diameter,
                depth=inferred_depth,
                count=len(instances),
                confidence=0.88,
                evidence=[source],
            )
        )
    return holes


def summarize_counterbore_candidates_as_holes(
    candidates: list[dict[str, float | int | None]],
    depth: float | None,
    source: SourceRef,
    *,
    cylindrical_faces: list[dict[str, float | None]] | None = None,
    bbox: BoundingBox | None = None,
) -> list[HoleCandidate]:
    grouped: dict[tuple[float | None, float | None, float | None, float | None], int] = defaultdict(int)
    for candidate in candidates:
        base_depth = matched_cylinder_depth(candidate, cylindrical_faces or []) or depth
        grouped[
            (
                candidate.get("base_diameter"),
                candidate.get("counterbore_diameter"),
                candidate.get("counterbore_depth"),
                base_depth,
            )
        ] += 1

    holes: list[HoleCandidate] = []
    for (base_diameter, counterbore_diameter, counterbore_depth, base_depth), count in sorted(
        grouped.items(),
        key=lambda item: (item[0][0] or 0, item[0][1] or 0),
    ):
        holes.append(
            HoleCandidate(
                hole_type="counterbore",
                diameter=float(base_diameter) if base_diameter is not None else None,
                depth=base_depth,
                count=count,
                confidence=0.72,
                evidence=[source],
                counterbore_diameter=(
                    float(counterbore_diameter)
                    if counterbore_diameter is not None
                    else None
                ),
                counterbore_depth=(
                    float(counterbore_depth)
                    if counterbore_depth is not None
                    else None
                ),
            )
        )
    return holes


def summarize_countersink_candidates_as_holes(
    candidates: list[dict[str, float | int | None]],
    depth: float | None,
    source: SourceRef,
    *,
    cylindrical_faces: list[dict[str, float | None]] | None = None,
    bbox: BoundingBox | None = None,
) -> list[HoleCandidate]:
    grouped: dict[tuple[float | None, float | None, float | None, float | None, float | None], int] = defaultdict(int)
    for candidate in candidates:
        base_depth = matched_cylinder_depth(candidate, cylindrical_faces or []) or depth
        grouped[
            (
                candidate.get("base_diameter"),
                candidate.get("countersink_diameter"),
                candidate.get("countersink_depth"),
                candidate.get("countersink_angle"),
                base_depth,
            )
        ] += 1

    holes: list[HoleCandidate] = []
    for (
        base_diameter,
        countersink_diameter,
        countersink_depth,
        countersink_angle,
        base_depth,
    ), count in sorted(grouped.items(), key=lambda item: (item[0][0] or 0, item[0][1] or 0)):
        holes.append(
            HoleCandidate(
                hole_type="countersink",
                diameter=float(base_diameter) if base_diameter is not None else None,
                depth=base_depth,
                count=count,
                confidence=0.7,
                evidence=[source],
                countersink_diameter=(
                    float(countersink_diameter)
                    if countersink_diameter is not None
                    else None
                ),
                countersink_depth=(
                    float(countersink_depth)
                    if countersink_depth is not None
                    else None
                ),
                countersink_angle=(
                    float(countersink_angle)
                    if countersink_angle is not None
                    else None
                ),
            )
        )
    return holes


def matching_cylinder_for_hole(
    hole: dict[str, float],
    cylindrical_faces: list[dict[str, float | None]],
) -> dict[str, float | None] | None:
    diameter = hole.get("diameter")
    if diameter is None:
        return None
    center_x = hole.get("center_x")
    center_y = hole.get("center_y")
    candidates: list[tuple[float, dict[str, float | None]]] = []
    for cylinder in cylindrical_faces:
        cylinder_diameter = cylinder.get("diameter")
        if cylinder_diameter is None or abs(float(cylinder_diameter) - float(diameter)) > 0.35:
            continue
        distance = 0.0
        if center_x is not None and center_y is not None and cylinder.get("center_x") is not None and cylinder.get("center_y") is not None:
            distance = math.hypot(
                float(center_x) - float(cylinder["center_x"]),
                float(center_y) - float(cylinder["center_y"]),
            )
            if distance > 1.5:
                continue
        candidates.append((distance, cylinder))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[0][1]


def matched_cylinder_depth(
    candidate: dict[str, float | int | None],
    cylindrical_faces: list[dict[str, float | None]],
) -> float | None:
    base_diameter = candidate.get("base_diameter") or candidate.get("diameter")
    if base_diameter is None:
        return None
    matched = matching_cylinder_for_hole(
        {
            "diameter": float(base_diameter),
            "center_x": float(candidate.get("center_x") or 0),
            "center_y": float(candidate.get("center_y") or 0),
        },
        cylindrical_faces,
    )
    if not matched or matched.get("depth") is None:
        return None
    return round_float(matched.get("depth"), 1)


def classify_cylinder_hole_type(
    depth: float | None,
    bbox: BoundingBox | None,
    *,
    default: str = "through",
) -> str:
    if depth is None or bbox is None:
        return default
    dims = [
        value
        for value in (bbox.length, bbox.width, bbox.height)
        if value is not None and value > 0
    ]
    if not dims:
        return default
    min_dim = min(dims)
    return "through" if depth >= min_dim * 0.85 else "blind"


def detect_hole_groups(hole_instances: list[dict[str, float]], source: SourceRef) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    by_diameter: dict[float, list[dict[str, float]]] = defaultdict(list)
    for hole in hole_instances:
        by_diameter[hole["diameter"]].append(hole)

    group_index = 1
    for diameter, holes in sorted(by_diameter.items()):
        for cluster in cluster_points(holes):
            xs = sorted({round_float(hole["center_x"], 2) or 0.0 for hole in cluster})
            ys = sorted({round_float(hole["center_y"], 2) or 0.0 for hole in cluster})
            x_spacings = spacing_values(xs)
            y_spacings = spacing_values(ys)
            array_type = classify_hole_group(len(cluster), len(xs), len(ys), x_spacings, y_spacings)
            result.append(
                {
                    "group_id": f"hole_group_{group_index}",
                    "diameter": diameter,
                    "count": len(cluster),
                    "array_type": array_type,
                    "x_count": len(xs),
                    "y_count": len(ys),
                    "x_spacing_candidates": x_spacings[:5],
                    "y_spacing_candidates": y_spacings[:5],
                    "bbox": point_bbox(cluster),
                    "confidence": hole_group_confidence(array_type),
                    "evidence": [source.to_dict()],
                }
            )
            group_index += 1
    return result


def cluster_points(points: list[dict[str, float]]) -> list[list[dict[str, float]]]:
    if not points:
        return []
    if len(points) <= 3:
        return [points]
    threshold = cluster_threshold(points)
    remaining = list(points)
    clusters: list[list[dict[str, float]]] = []
    while remaining:
        seed = remaining.pop(0)
        cluster = [seed]
        changed = True
        while changed:
            changed = False
            next_remaining = []
            for point in remaining:
                if any(point_distance(point, member) <= threshold for member in cluster):
                    cluster.append(point)
                    changed = True
                else:
                    next_remaining.append(point)
            remaining = next_remaining
        clusters.append(cluster)
    return sorted(clusters, key=lambda item: (-len(item), point_bbox(item)["min_x"], point_bbox(item)["min_y"]))


def cluster_threshold(points: list[dict[str, float]]) -> float:
    if len(points) <= 1:
        return 0.0
    nearest: list[float] = []
    for point in points:
        distances = sorted(point_distance(point, other) for other in points if other is not point)
        if distances:
            nearest.append(distances[0])
    if not nearest:
        return 0.0
    nearest_sorted = sorted(nearest)
    median = nearest_sorted[len(nearest_sorted) // 2]
    return max(80.0, min(260.0, median * 1.8))


def point_distance(a: dict[str, float], b: dict[str, float]) -> float:
    return math.hypot(a["center_x"] - b["center_x"], a["center_y"] - b["center_y"])


def spacing_values(values: list[float]) -> list[float]:
    if len(values) <= 1:
        return []
    counts = Counter(round_float(values[index + 1] - values[index], 1) for index in range(len(values) - 1))
    return [float(value) for value, _count in counts.most_common() if value and value > 0]


def classify_hole_group(count: int, x_count: int, y_count: int, x_spacings: list[float], y_spacings: list[float]) -> str:
    if count == 1:
        return "single"
    if count == 2:
        return "pair"
    if x_count >= 2 and y_count >= 2 and count >= min(x_count * y_count, 4):
        return "grid_array"
    if x_count == 1 or y_count == 1:
        return "linear_array"
    if x_spacings or y_spacings:
        return "pattern_group"
    return "irregular_group"


def hole_group_confidence(array_type: str) -> float:
    if array_type in {"grid_array", "linear_array"}:
        return 0.74
    if array_type in {"pattern_group", "pair"}:
        return 0.66
    if array_type == "single":
        return 0.5
    return 0.58


def point_bbox(points: list[dict[str, float]]) -> dict[str, float | None]:
    if not points:
        return {"min_x": None, "max_x": None, "min_y": None, "max_y": None}
    xs = [point["center_x"] for point in points]
    ys = [point["center_y"] for point in points]
    return {
        "min_x": round_float(min(xs), 2),
        "max_x": round_float(max(xs), 2),
        "min_y": round_float(min(ys), 2),
        "max_y": round_float(max(ys), 2),
    }


def collect_counterbore_candidates(circular_edges: list[dict[str, float | None]], bbox: BoundingBox) -> list[dict[str, float | int | None]]:
    max_dim = max(value for value in [bbox.length, bbox.width, bbox.height] if value is not None) if any([bbox.length, bbox.width, bbox.height]) else 0
    grouped_edges: dict[tuple[float, float, float], list[dict[str, float | None]]] = defaultdict(list)

    for edge in circular_edges:
        diameter = edge.get("diameter")
        radius = edge.get("radius")
        center_x = edge.get("center_x")
        center_y = edge.get("center_y")
        if None in (diameter, radius, center_x, center_y):
            continue
        if max_dim and diameter > max_dim * 0.35:
            continue
        if diameter < 1.0:
            continue
        key = (round(float(center_x), 2), round(float(center_y), 2), round(float(radius), 2))
        grouped_edges[key].append(edge)

    center_groups: dict[tuple[float, float], list[tuple[float, float | None, float, float]]] = defaultdict(list)
    for (_center_x, _center_y, radius), edges in grouped_edges.items():
        arc_sum = sum(float(edge.get("arc_fraction") or 0) for edge in edges)
        if arc_sum < 0.45:
            continue
        z_values = [float(edge["center_z"]) for edge in edges if edge.get("center_z") is not None]
        depth = max(z_values) - min(z_values) if len(z_values) >= 2 else None
        center_groups[(_center_x, _center_y)].append((radius * 2, depth, arc_sum, radius))

    candidates: list[dict[str, float | int | None]] = []
    for (center_x, center_y), circles in center_groups.items():
        circles = sorted(circles, key=lambda item: item[0])
        if len(circles) >= 2:
            smallest = circles[0]
            largest = circles[-1]
            if largest[0] >= smallest[0] * 1.25:
                candidates.append(
                    {
                        "center_x": center_x,
                        "center_y": center_y,
                        "base_diameter": round_float(smallest[0], 1),
                        "counterbore_diameter": round_float(largest[0], 1),
                        "counterbore_depth": round_float(largest[1], 1) if largest[1] is not None else None,
                    }
                )
    return candidates


def collect_countersink_candidates(faces: Iterable[Any], bbox: BoundingBox) -> list[dict[str, float | int | None]]:
    max_dim = max(value for value in [bbox.length, bbox.width, bbox.height] if value is not None) if any([bbox.length, bbox.width, bbox.height]) else 0
    candidates: list[dict[str, float | int | None]] = []
    for face in faces:
        try:
            if str(face.geomType()).upper() != "CONE":
                continue
            circular_edges = []
            for edge in face.Edges():
                try:
                    if str(edge.geomType()).upper() != "CIRCLE":
                        continue
                    radius = float(edge.radius())
                    center = edge.arcCenter()
                    circular_edges.append(
                        {
                            "radius": radius,
                            "diameter": radius * 2,
                            "center_x": float(center.x),
                            "center_y": float(center.y),
                            "center_z": float(center.z),
                        }
                    )
                except Exception:
                    continue
            if len(circular_edges) < 2:
                continue

            circular_edges = sorted(circular_edges, key=lambda item: item["diameter"])
            small = circular_edges[0]
            large = circular_edges[-1]
            if max_dim and large["diameter"] > max_dim * 0.35:
                continue
            if small["diameter"] < 1.0 or large["diameter"] < small["diameter"] * 1.15:
                continue

            depth = distance_3d(small, large)
            angle = countersink_included_angle(
                small["diameter"],
                large["diameter"],
                depth,
            )
            if depth is None or depth <= 0:
                continue
            candidates.append(
                {
                    "center_x": round_float((small["center_x"] + large["center_x"]) / 2, 2),
                    "center_y": round_float((small["center_y"] + large["center_y"]) / 2, 2),
                    "base_diameter": round_float(small["diameter"], 1),
                    "countersink_diameter": round_float(large["diameter"], 1),
                    "countersink_depth": round_float(depth, 1),
                    "countersink_angle": round_float(angle, 1),
                }
            )
        except Exception:
            continue
    return candidates


def distance_3d(a: dict[str, float], b: dict[str, float]) -> float | None:
    return vector_length(
        a.get("center_x", 0) - b.get("center_x", 0),
        a.get("center_y", 0) - b.get("center_y", 0),
        a.get("center_z", 0) - b.get("center_z", 0),
    )


def countersink_included_angle(
    small_diameter: float,
    large_diameter: float,
    depth: float | None,
) -> float | None:
    if depth is None or depth <= 0:
        return None
    radius_delta = abs(large_diameter - small_diameter) / 2
    return math.degrees(2 * math.atan(radius_delta / depth))


def format_counterbore_candidates(candidates: list[dict[str, float | int | None]], source: SourceRef) -> list[dict[str, Any]]:
    grouped: dict[tuple[float | None, float | None, float | None], int] = defaultdict(int)
    for candidate in candidates:
        grouped[(candidate.get("base_diameter"), candidate.get("counterbore_diameter"), candidate.get("counterbore_depth"))] += 1

    result: list[dict[str, Any]] = []
    for (base_diameter, counterbore_diameter, counterbore_depth), count in sorted(grouped.items(), key=lambda item: (item[0][0] or 0, item[0][1] or 0)):
        result.append(
            {
                "base_diameter": base_diameter,
                "counterbore_diameter": counterbore_diameter,
                "counterbore_depth": counterbore_depth,
                "count": count,
                "confidence": 0.72,
                "evidence": [source.to_dict()],
            }
        )
    return result


def format_countersink_candidates(candidates: list[dict[str, float | int | None]], source: SourceRef) -> list[dict[str, Any]]:
    grouped: dict[tuple[float | None, float | None, float | None, float | None], int] = defaultdict(int)
    for candidate in candidates:
        grouped[
            (
                candidate.get("base_diameter"),
                candidate.get("countersink_diameter"),
                candidate.get("countersink_depth"),
                candidate.get("countersink_angle"),
            )
        ] += 1

    result: list[dict[str, Any]] = []
    for (
        base_diameter,
        countersink_diameter,
        countersink_depth,
        countersink_angle,
    ), count in sorted(grouped.items(), key=lambda item: (item[0][0] or 0, item[0][1] or 0)):
        result.append(
            {
                "base_diameter": base_diameter,
                "countersink_diameter": countersink_diameter,
                "countersink_depth": countersink_depth,
                "countersink_angle": countersink_angle,
                "count": count,
                "confidence": 0.7,
                "evidence": [source.to_dict()],
            }
        )
    return result


def detect_holes_from_cylinders(cylindrical_faces: list[dict[str, float | None]], bbox: BoundingBox, source: SourceRef) -> list[HoleCandidate]:
    max_dim = max(value for value in [bbox.length, bbox.width, bbox.height] if value is not None) if any([bbox.length, bbox.width, bbox.height]) else 0
    hole_groups: dict[tuple[float | None, float | None], int] = defaultdict(int)

    for item in cylindrical_faces:
        diameter = item.get("diameter")
        depth = item.get("depth")
        if diameter is None or diameter <= 0:
            continue
        if max_dim and diameter > max_dim * 0.35:
            continue
        if diameter < 1.0:
            continue
        key = (round_float(diameter, 1), round_float(depth, 1) if depth is not None else None)
        hole_groups[key] += 1

    holes: list[HoleCandidate] = []
    for (diameter, depth), count in sorted(hole_groups.items(), key=lambda pair: (pair[0][0] or 0, pair[0][1] or 0)):
        hole_type = classify_cylinder_hole_type(depth, bbox, default="blind")
        holes.append(
            HoleCandidate(
                hole_type=hole_type,
                diameter=diameter,
                depth=depth,
                count=count,
                confidence=0.62,
                evidence=[source],
            )
        )
    return holes


def calculate_profile_summary(metrics: ShapeMetrics) -> dict[str, Any]:
    if metrics.profile_wires:
        outer_profiles = [profile for profile in metrics.profile_wires if profile.get("kind") == "outer"]
        inner_profiles = [profile for profile in metrics.profile_wires if profile.get("kind") == "inner"]
        outer_profile_length = sum(float(profile.get("length") or 0) for profile in outer_profiles)
        outer_line_length = sum(float(profile.get("line_length") or 0) for profile in outer_profiles)
        outer_arc_length = sum(float(profile.get("arc_length") or 0) for profile in outer_profiles)
        outer_line_count = sum(int(profile.get("line_count") or 0) for profile in outer_profiles)
        outer_arc_count = sum(int(profile.get("circle_count") or 0) for profile in outer_profiles)
        inner_profile_length = sum(float(profile.get("length") or 0) for profile in inner_profiles)
        inner_line_length = sum(float(profile.get("line_length") or 0) for profile in inner_profiles)
        inner_arc_length = sum(float(profile.get("arc_length") or 0) for profile in inner_profiles)
        inner_line_count = sum(int(profile.get("line_count") or 0) for profile in inner_profiles)
        inner_arc_count = sum(int(profile.get("circle_count") or 0) for profile in inner_profiles)
        circular_inner_count = sum(1 for profile in inner_profiles if profile.get("circle_count", 0) > 0 and profile.get("line_count", 0) == 0)
        slot_candidate_count = sum(1 for profile in inner_profiles if is_slot_profile(profile))
        return {
            "outer_profile_length": round_float(outer_profile_length),
            "outer_line_length": round_float(outer_line_length),
            "outer_arc_length": round_float(outer_arc_length),
            "outer_line_count": outer_line_count,
            "outer_arc_count": outer_arc_count,
            "inner_profile_length": round_float(inner_profile_length),
            "inner_line_length": round_float(inner_line_length),
            "inner_arc_length": round_float(inner_arc_length),
            "inner_line_count": inner_line_count,
            "inner_arc_count": inner_arc_count,
            "top_profile_length": round_float(outer_profile_length + inner_profile_length),
            "inner_profile_count": len(inner_profiles),
            "circular_inner_profile_count": circular_inner_count,
            "slot_candidate_count": slot_candidate_count,
            "total_edge_length": round_float(sum(float(record.get("length") or 0) for record in metrics.edge_records)) if metrics.edge_records else None,
            "line_edge_length": round_float(sum(float(record.get("length") or 0) for record in metrics.edge_records if record.get("geom_type") == "LINE")) if metrics.edge_records else None,
            "circular_edge_length": round_float(sum(float(record.get("length") or 0) for record in metrics.edge_records if record.get("geom_type") == "CIRCLE")) if metrics.edge_records else None,
            "circular_edge_count": len(metrics.circular_edges),
        }

    records = metrics.edge_records
    if not records:
        return {
            "outer_profile_length": None,
            "outer_line_length": None,
            "outer_arc_length": None,
            "outer_line_count": None,
            "outer_arc_count": None,
            "inner_profile_length": None,
            "inner_line_length": None,
            "inner_arc_length": None,
            "inner_line_count": None,
            "inner_arc_count": None,
            "total_edge_length": None,
            "top_profile_length": None,
            "inner_profile_count": None,
            "circular_inner_profile_count": None,
            "slot_candidate_count": None,
            "line_edge_length": None,
            "circular_edge_length": None,
            "circular_edge_count": len(metrics.circular_edges),
        }

    total_edge_length = sum(float(record.get("length") or 0) for record in records)
    line_edge_length = sum(float(record.get("length") or 0) for record in records if record.get("geom_type") == "LINE")
    circular_edge_length = sum(float(record.get("length") or 0) for record in records if record.get("geom_type") == "CIRCLE")
    top_profile_length = estimate_top_profile_length(records)
    return {
        "outer_profile_length": None,
        "outer_line_length": None,
        "outer_arc_length": None,
        "outer_line_count": None,
        "outer_arc_count": None,
        "inner_profile_length": None,
        "inner_line_length": None,
        "inner_arc_length": None,
        "inner_line_count": None,
        "inner_arc_count": None,
        "total_edge_length": round_float(total_edge_length),
        "top_profile_length": round_float(top_profile_length),
        "inner_profile_count": None,
        "circular_inner_profile_count": None,
        "slot_candidate_count": None,
        "line_edge_length": round_float(line_edge_length),
        "circular_edge_length": round_float(circular_edge_length),
        "circular_edge_count": len(metrics.circular_edges),
    }


def detect_slot_candidates(profile_wires: list[dict[str, float | int | str | None]], source: SourceRef) -> list[dict[str, Any]]:
    candidates = [profile for profile in profile_wires if profile.get("kind") == "inner" and is_slot_profile(profile)]
    if not candidates:
        return []

    grouped: dict[str, list[dict[str, float | int | str | None]]] = defaultdict(list)
    for profile in candidates:
        slot_type = "elongated_slot" if profile_aspect_ratio(profile) >= 2.0 else "irregular_inner_profile"
        grouped[slot_type].append(profile)

    result: list[dict[str, Any]] = []
    for slot_type, profiles in sorted(grouped.items()):
        result.append(
            {
                "slot_type": slot_type,
                "count": len(profiles),
                "confidence": 0.68 if slot_type == "elongated_slot" else 0.55,
                "avg_profile_length": round_float(sum(float(profile.get("length") or 0) for profile in profiles) / len(profiles)),
                "max_profile_length": round_float(max(float(profile.get("length") or 0) for profile in profiles)),
                "avg_length": round_float(sum(float(profile.get("bbox_length") or 0) for profile in profiles) / len(profiles)),
                "avg_width": round_float(sum(float(profile.get("bbox_width") or 0) for profile in profiles) / len(profiles)),
                "avg_line_length": round_float(sum(float(profile.get("line_length") or 0) for profile in profiles) / len(profiles)),
                "avg_arc_length": round_float(sum(float(profile.get("arc_length") or 0) for profile in profiles) / len(profiles)),
                "evidence": [source.to_dict()],
            }
        )
    return result


def is_slot_profile(profile: dict[str, float | int | str | None]) -> bool:
    line_count = int(profile.get("line_count") or 0)
    circle_count = int(profile.get("circle_count") or 0)
    if line_count >= 2 and circle_count >= 2:
        return True
    return profile_aspect_ratio(profile) >= 3.0 and line_count >= 2


def profile_aspect_ratio(profile: dict[str, float | int | str | None]) -> float:
    length = float(profile.get("bbox_length") or 0)
    width = float(profile.get("bbox_width") or 0)
    if width <= 0:
        return 0.0
    return length / width


def summarize_holes(holes: list[HoleCandidate]) -> dict[str, Any]:
    by_type: dict[str, int] = defaultdict(int)
    by_diameter: dict[str, int] = defaultdict(int)
    for hole in holes:
        by_type[hole.hole_type] += hole.count
        diameter_key = f"{hole.diameter:.1f}" if hole.diameter is not None else "unknown"
        by_diameter[diameter_key] += hole.count
    return {
        "total_count": sum(hole.count for hole in holes),
        "by_type": dict(sorted(by_type.items())),
        "by_diameter": dict(sorted(by_diameter.items(), key=lambda item: float(item[0]) if item[0] != "unknown" else -1)),
    }


def estimate_top_profile_length(records: list[dict[str, float | str | None]]) -> float | None:
    z_values = [float(record["center_z"]) for record in records if record.get("center_z") is not None]
    if not z_values:
        return None
    top_z = max(z_values)
    tolerance = max(0.2, (max(z_values) - min(z_values)) * 0.01)
    return sum(float(record.get("length") or 0) for record in records if record.get("center_z") is not None and abs(float(record["center_z"]) - top_z) <= tolerance)


def calculate_complexity(
    metrics: ShapeMetrics,
    holes: list[HoleCandidate],
    *,
    slot_count: int = 0,
) -> dict[str, Any]:
    face_count = metrics.face_count or 0
    edge_count = metrics.edge_count or 0
    small_radius_count = count_small_radius_features(metrics)
    hole_count = sum(hole.count for hole in holes)
    bspline_face_ratio = (metrics.face_type_counts.get("BSPLINE", 0) / face_count) if face_count else 0.0
    bspline_edge_ratio = (metrics.edge_type_counts.get("BSPLINE", 0) / edge_count) if edge_count else 0.0
    multi_body_count = max(metrics.solid_count or 0, metrics.shell_count or 0, metrics.compound_count or 0)
    bbox = metrics.bounding_box
    dims = [value for value in [bbox.length, bbox.width, bbox.height] if value is not None and value > 0]
    thin_wall_candidate = bool(dims and min(dims) <= max(dims) * 0.06)
    score = min(
        100,
        round(
            face_count * 0.5
            + edge_count * 0.12
            + min(hole_count, 16) * 2
            + small_radius_count * 2
            + min(slot_count, 8) * 3
            + bspline_face_ratio * 25
            + bspline_edge_ratio * 10
            + max(multi_body_count - 1, 0) * 15
            + (8 if thin_wall_candidate else 0)
        ),
    )
    return {
        "face_count": face_count,
        "edge_count": edge_count,
        "small_radius_count": small_radius_count,
        "slot_count": slot_count,
        "thin_wall_candidate": thin_wall_candidate,
        "complexity_score": score,
    }


def count_small_radius_features(metrics: ShapeMetrics) -> int:
    keys: set[tuple[str, float, float | None, float | None, float | None]] = set()
    for item in metrics.cylindrical_faces:
        radius = item.get("radius")
        if radius is None or radius > 2.0:
            continue
        keys.add(
            (
                "face",
                round(float(radius), 2),
                round_float(item.get("center_x"), 2),
                round_float(item.get("center_y"), 2),
                round_float(item.get("center_z"), 2),
            )
        )
    for item in metrics.circular_edges:
        radius = item.get("radius")
        if radius is None or radius > 2.0:
            continue
        keys.add(
            (
                "edge",
                round(float(radius), 2),
                round_float(item.get("center_x"), 2),
                round_float(item.get("center_y"), 2),
                round_float(item.get("center_z"), 2),
            )
        )
    return len(keys)


def classify_part_type(metrics: ShapeMetrics, complexity: dict[str, Any]) -> list[dict[str, Any]]:
    bbox = metrics.bounding_box
    dims = sorted([value for value in [bbox.length, bbox.width, bbox.height] if value is not None and value > 0], reverse=True)
    if len(dims) != 3:
        return [{"part_type": "complex", "confidence": 0.45, "reason": "Bounding box is incomplete."}]

    long_dim, mid_dim, short_dim = dims
    candidates: list[dict[str, Any]] = []
    round_section = mid_dim > 0 and short_dim > 0 and mid_dim / short_dim <= 1.18
    relaxed_round_section = mid_dim > 0 and short_dim > 0 and mid_dim / short_dim <= 1.75
    round_disk_section = long_dim > 0 and mid_dim > 0 and long_dim / mid_dim <= 1.18
    elongated = mid_dim > 0 and long_dim / mid_dim >= 2.4
    cylindrical_face_ratio = (metrics.face_type_counts.get("CYLINDER", 0) / metrics.face_count) if metrics.face_count else 0.0
    bspline_face_ratio = (metrics.face_type_counts.get("BSPLINE", 0) / metrics.face_count) if metrics.face_count else 0.0
    bspline_edge_ratio = (metrics.edge_type_counts.get("BSPLINE", 0) / metrics.edge_count) if metrics.edge_count else 0.0
    cylindrical_signal = metrics.cylindrical_area_ratio >= 0.4 or metrics.circular_edge_ratio >= 0.35 or cylindrical_face_ratio >= 0.45
    strong_cylindrical_signal = metrics.cylindrical_area_ratio >= 0.65 or metrics.circular_edge_ratio >= 0.5
    short_turned_signal = relaxed_round_section and metrics.cylindrical_area_ratio >= 0.55 and metrics.circular_edge_ratio >= 0.3
    freeform_turned_signal = round_disk_section and metrics.cylindrical_area_ratio >= 0.4 and (bspline_face_ratio >= 0.25 or bspline_edge_ratio >= 0.25)

    if is_multi_body_candidate(metrics):
        candidates.append(
            {
                "part_type": "complex",
                "confidence": 0.78,
                "reason": "Multiple solids/shells/compounds suggest an assembly or multi-body STEP.",
            }
        )
    elif bspline_face_ratio >= 0.35 or bspline_edge_ratio >= 0.35:
        candidates.append(
            {
                "part_type": "complex",
                "confidence": 0.7,
                "reason": "Freeform BSPLINE geometry ratio is high.",
            }
        )

    if round_section and cylindrical_signal:
        confidence = 0.86 if elongated and strong_cylindrical_signal else 0.72
        reason = "Two shorter bounding-box dimensions are close and cylindrical geometry dominates."
        if elongated:
            reason = "Long axis with near-round cross section and strong cylindrical geometry."
        candidates.append({"part_type": "shaft", "confidence": confidence, "reason": reason})
    elif (
        (round_disk_section and cylindrical_signal and (has_round_outer_profile(metrics) or (strong_cylindrical_signal and not has_rectangular_plate_profile(metrics))))
        or (short_turned_signal and not has_rectangular_plate_profile(metrics))
        or (freeform_turned_signal and not has_rectangular_plate_profile(metrics))
    ):
        candidates.append(
            {
                "part_type": "shaft",
                "confidence": 0.68,
                "reason": "Short round or flange-like turned part with strong cylindrical geometry.",
            }
        )

    if short_dim <= long_dim * 0.12 and short_dim <= mid_dim * 0.2:
        candidates.append({"part_type": "thin_plate", "confidence": 0.82, "reason": "One dimension is much smaller than length and width."})
    elif short_dim <= long_dim * 0.35:
        candidates.append({"part_type": "plate", "confidence": 0.76, "reason": "Bounding box has plate-like proportions."})
    elif long_dim <= short_dim * 2.2:
        candidates.append({"part_type": "block", "confidence": 0.74, "reason": "Bounding box dimensions are relatively close."})
    elif long_dim >= mid_dim * 3.0 and mid_dim <= short_dim * 1.3:
        candidates.append({"part_type": "shaft", "confidence": 0.56, "reason": "Long and narrow shape may be a shaft."})

    if (complexity.get("complexity_score") or 0) >= 70 and not any(candidate["part_type"] == "complex" for candidate in candidates):
        complex_candidate = {"part_type": "complex", "confidence": 0.72, "reason": "Complexity score is high."}
        if candidates and candidates[0]["part_type"] == "shaft":
            candidates.append(complex_candidate)
        else:
            candidates.insert(0, complex_candidate)
    if not candidates:
        candidates.append({"part_type": "small_irregular", "confidence": 0.52, "reason": "No simple bounding-box category matched."})
    return candidates


def is_multi_body_candidate(metrics: ShapeMetrics) -> bool:
    counts = [
        count
        for count in (metrics.solid_count, metrics.shell_count, metrics.compound_count)
        if count is not None
    ]
    return bool(counts and max(counts) > 1)


def freeform_geometry_ratio(metrics: ShapeMetrics) -> float:
    face_ratio = (
        metrics.face_type_counts.get("BSPLINE", 0) / metrics.face_count
        if metrics.face_count
        else 0.0
    )
    edge_ratio = (
        metrics.edge_type_counts.get("BSPLINE", 0) / metrics.edge_count
        if metrics.edge_count
        else 0.0
    )
    return max(face_ratio, edge_ratio)


def has_round_outer_profile(metrics: ShapeMetrics) -> bool:
    outer_profiles = [profile for profile in metrics.profile_wires if profile.get("kind") == "outer"]
    if not outer_profiles:
        return metrics.circular_edge_ratio >= 0.5 and metrics.cylindrical_area_ratio >= 0.45
    outer = outer_profiles[0]
    line_count = int(outer.get("line_count") or 0)
    circle_count = int(outer.get("circle_count") or 0)
    arc_length = float(outer.get("arc_length") or 0)
    length = float(outer.get("length") or 0)
    return circle_count >= 2 and line_count <= 2 and length > 0 and arc_length / length >= 0.75


def has_rectangular_plate_profile(metrics: ShapeMetrics) -> bool:
    outer_profiles = [profile for profile in metrics.profile_wires if profile.get("kind") == "outer"]
    inner_profiles = [profile for profile in metrics.profile_wires if profile.get("kind") == "inner"]
    if not outer_profiles:
        return False
    outer = outer_profiles[0]
    line_count = int(outer.get("line_count") or 0)
    arc_length = float(outer.get("arc_length") or 0)
    length = float(outer.get("length") or 0)
    arc_ratio = arc_length / length if length else 0.0
    return line_count >= 4 and arc_ratio <= 0.25 and len(inner_profiles) >= 3


def geometry_risks(
    metrics: ShapeMetrics,
    candidates: list[dict[str, Any]],
    complexity: dict[str, Any],
    holes: list[HoleCandidate],
    slot_candidates: list[dict[str, Any]],
    source: SourceRef,
) -> list[RiskItem]:
    risks: list[RiskItem] = []
    primary_type = candidates[0]["part_type"] if candidates else None
    if primary_type in {"shaft", "complex"}:
        risks.append(
            RiskItem(
                "HIGH_RISK_GEOMETRY",
                "blocking",
                f"Part type candidate {primary_type} should be reviewed before automatic pricing.",
                "step_parser",
                True,
                [source],
            )
        )
    if is_multi_body_candidate(metrics):
        risks.append(
            RiskItem(
                "HIGH_RISK_GEOMETRY",
                "blocking",
                "Multiple solids/shells/compounds detected; assembly or multi-body STEP should be reviewed.",
                "step_parser",
                True,
                [source],
            )
        )
    if freeform_geometry_ratio(metrics) >= 0.35:
        risks.append(
            RiskItem(
                "HIGH_RISK_GEOMETRY",
                "warning",
                "High freeform BSPLINE geometry ratio should be reviewed.",
                "step_parser",
                True,
                [source],
            )
        )
    if (complexity.get("complexity_score") or 0) >= 70:
        risks.append(
            RiskItem(
                "HIGH_RISK_GEOMETRY",
                "warning",
                "High geometry complexity should be reviewed.",
                "step_parser",
                True,
                [source],
            )
        )
    if complexity.get("thin_wall_candidate"):
        risks.append(
            RiskItem(
                "HIGH_RISK_GEOMETRY",
                "warning",
                "Thin-wall candidate detected from bounding box proportions.",
                "step_parser",
                True,
                [source],
            )
        )
    if (complexity.get("small_radius_count") or 0) > 0:
        risks.append(
            RiskItem(
                "HIGH_RISK_GEOMETRY",
                "warning",
                f"Small radius features detected: {complexity.get('small_radius_count')}.",
                "step_parser",
                True,
                [source],
            )
        )
    narrow_slots = [slot for slot in slot_candidates if is_narrow_slot(slot)]
    if narrow_slots:
        risks.append(
            RiskItem(
                "HIGH_RISK_GEOMETRY",
                "warning",
                f"Narrow slot candidates detected: {sum(int(slot.get('count') or 0) for slot in narrow_slots)}.",
                "step_parser",
                True,
                [source],
            )
        )
    deep_holes = [hole for hole in holes if is_deep_hole(hole)]
    if deep_holes:
        risks.append(
            RiskItem(
                "HIGH_RISK_GEOMETRY",
                "warning",
                f"Deep hole candidates detected: {sum(hole.count for hole in deep_holes)}.",
                "step_parser",
                True,
                [source],
            )
        )
    if is_long_cantilever_candidate(metrics):
        risks.append(
            RiskItem(
                "HIGH_RISK_GEOMETRY",
                "warning",
                "Long thin geometry may require support/cantilever review.",
                "step_parser",
                True,
                [source],
            )
        )
    return risks


def is_narrow_slot(slot: dict[str, Any]) -> bool:
    avg_width = slot.get("avg_width")
    avg_length = slot.get("avg_length")
    if avg_width is None or avg_length is None:
        return False
    width = float(avg_width)
    length = float(avg_length)
    if width <= 0:
        return False
    aspect_ratio = length / width
    return width <= 3.0 or (width <= 5.0 and aspect_ratio >= 8.0)


def is_deep_hole(hole: HoleCandidate) -> bool:
    if hole.depth is None or hole.diameter is None or hole.diameter <= 0:
        return False
    return hole.depth / hole.diameter >= 5.0


def is_long_cantilever_candidate(metrics: ShapeMetrics) -> bool:
    dims = sorted(
        [
            value
            for value in (
                metrics.bounding_box.length,
                metrics.bounding_box.width,
                metrics.bounding_box.height,
            )
            if value is not None and value > 0
        ],
        reverse=True,
    )
    if len(dims) != 3:
        return False
    long_dim, mid_dim, short_dim = dims
    return long_dim / mid_dim >= 6.0 and short_dim / mid_dim <= 0.25


def calculate_net_weight(volume_mm3: float | None, density: float | None, density_unit: str) -> float | None:
    if volume_mm3 is None or density is None:
        return None
    if density_unit == "kg/mm3":
        return volume_mm3 * density
    if density_unit == "g/cm3":
        return volume_mm3 * density / 1_000_000
    raise ValueError("density_unit must be kg/mm3 or g/cm3")


def build_part_feature_stub(
    step_result: dict[str, Any],
    *,
    part_name: str | None = None,
    drawing_no: str | None = None,
    revision: str | None = None,
    quantity: float = 1,
    material_code: str | None = None,
    material_name: str | None = None,
    density: float | None = None,
    density_unit: str | None = None,
) -> dict[str, Any]:
    """Convert STEP-only output into a part_feature-like payload for A-side trials."""
    source = {"source_type": "step", "file_id": step_result.get("file_id")}
    primary_type = first_part_type(step_result)
    risk_items = []
    for risk in step_result.get("geometry_risks", []):
        risk_items.append(
            {
                "code": risk["code"],
                "level": risk["level"],
                "message": risk["message"],
                "source": risk["source"],
                "requires_review": risk["requires_review"],
                "evidence": risk.get("evidence") or [source],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": step_result.get("task_id") or f"task_{step_result.get('file_id', 'step')}",
        "part": {"part_name": part_name, "drawing_no": drawing_no, "revision": revision, "quantity": quantity},
        "material": {
            "raw_text": material_code,
            "standard_code": material_code,
            "standard_name": material_name or material_code,
            "density": density,
            "density_unit": density_unit,
            "confidence": 0.0 if material_code is None else 0.7,
            "source": {"source_type": "manual"},
        },
        "geometry": {
            "bounding_box": step_result["bounding_box"],
            "volume": step_result["volume"],
            "surface_area": step_result["surface_area"],
            "pdf_weight": {"value": None, "unit": None, "source": {"source_type": "manual"}},
            "step_net_weight": {"value": step_result["net_weight"]["value"], "unit": step_result["net_weight"]["unit"], "source": source},
            "part_type": primary_type["part_type"] if primary_type else None,
            "part_type_confidence": primary_type["confidence"] if primary_type else 0.0,
        },
        "features": {
            "holes": step_result.get("holes", []),
            "slots": part_feature_slots(step_result.get("slot_candidates", [])),
            "precision_requirements": [],
            "complexity": step_result["complexity"],
        },
        "manufacturing_requirements": {
            "heat_treatment": empty_requirement(),
            "surface_treatment": empty_requirement(),
            "deburring": empty_requirement(),
            "inspection": default_requirement("STANDARD_INSPECTION"),
            "packaging": default_requirement("STANDARD_PACKAGING"),
        },
        "risks": risk_items,
        "evidence": [source],
    }


def first_part_type(step_result: dict[str, Any]) -> dict[str, Any] | None:
    candidates = step_result.get("part_type_candidates") or []
    return candidates[0] if candidates else None


def empty_requirement() -> dict[str, Any]:
    return {"required": False, "raw_text": None, "standard_code": None, "confidence": 1.0, "source": {"source_type": "manual"}}


def default_requirement(code: str) -> dict[str, Any]:
    return {"required": True, "raw_text": code.lower(), "standard_code": code, "confidence": 0.8, "source": {"source_type": "manual"}}


def part_feature_slots(slot_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "slot_type": slot["slot_type"],
            "count": slot["count"],
            "confidence": slot["confidence"],
        }
        for slot in slot_candidates
    ]


def empty_result(path: Path, *, task_id: str | None, file_id: str, risks: list[RiskItem]) -> dict[str, Any]:
    source = SourceRef(file_id=file_id)
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "file_id": file_id,
        "source_file": str(path),
        "backend": None,
        "bounding_box": BoundingBox(None, None, None).to_dict(),
        "volume": MeasuredValue(None, MM3_UNIT, source).to_dict(),
        "surface_area": MeasuredValue(None, MM2_UNIT, source).to_dict(),
        "net_weight": {"value": None, "unit": None, "density": None, "density_unit": None, "source": source.to_dict()},
        "part_type_candidates": [],
        "holes": [],
        "hole_summary": {"total_count": 0, "by_type": {}, "by_diameter": {}},
        "hole_groups": [],
        "counterbore_candidates": [],
        "countersink_candidates": [],
        "slot_candidates": [],
        "profile_summary": {
            "outer_profile_length": None,
            "outer_line_length": None,
            "outer_arc_length": None,
            "outer_line_count": None,
            "outer_arc_count": None,
            "inner_profile_length": None,
            "inner_line_length": None,
            "inner_arc_length": None,
            "inner_line_count": None,
            "inner_arc_count": None,
            "total_edge_length": None,
            "top_profile_length": None,
            "inner_profile_count": None,
            "circular_inner_profile_count": None,
            "slot_candidate_count": None,
            "line_edge_length": None,
            "circular_edge_length": None,
            "circular_edge_count": 0,
        },
        "complexity": {
            "face_count": None,
            "edge_count": None,
            "small_radius_count": None,
            "slot_count": None,
            "thin_wall_candidate": False,
            "complexity_score": None,
        },
        "geometry_risks": [risk.to_dict() for risk in risks],
    }


def safe_call(obj: Any, method_name: str) -> float | None:
    try:
        method = getattr(obj, method_name)
        return float(method())
    except Exception:
        return None


def round_float(value: Any, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)
