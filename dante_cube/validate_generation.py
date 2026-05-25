"""命令行烟测：不依赖 Blender，验证 Dante Cube 数据层。"""

from __future__ import annotations

from collections import Counter

from .generators import AbyssConfig, generate_abyss_rooms, rooms_by_structure
from .openings import generate_openings
from .pathfinding import build_adjacency_graph, connected_components
from .pathfinding import find_dante_path, measure_dante_path
from .room_semantics import classify_rooms
from .semantic_validation import validate_openings, validate_room_semantics, validate_stairs
from .stairs import STAIR_KIND_LADDER, STAIR_KIND_STAIR, generate_stairs
from .validation import validate_rooms


def run_smoke_check(config: AbyssConfig | None = None) -> int:
    cfg = config or AbyssConfig()
    rooms = generate_abyss_rooms(cfg)
    graph = build_adjacency_graph(rooms, cfg.module_size)
    report = validate_rooms(rooms, graph, cfg)
    components = connected_components(graph)
    structure_groups = rooms_by_structure(rooms)

    dante_paths: dict[str, list[str]] = {}
    path_metrics_by_structure = {}
    semantics = {}
    openings = []
    stairs = []
    semantic_errors: list[str] = []
    opening_errors: list[str] = []
    stair_errors: list[str] = []

    for structure_id, structure_rooms in sorted(structure_groups.items()):
        room_ids = {room.id for room in structure_rooms}
        structure_graph = {room_id: graph.get(room_id, set()) & room_ids for room_id in room_ids}
        structure_path = find_dante_path(structure_rooms, structure_graph, cfg)
        dante_paths[structure_id] = structure_path
        path_metrics_by_structure[structure_id] = measure_dante_path(structure_rooms, structure_path)
        structure_semantics = classify_rooms(structure_rooms, structure_graph, structure_path, cfg)
        structure_openings = generate_openings(structure_rooms, structure_graph, structure_semantics, structure_path, cfg)
        structure_stairs = generate_stairs(structure_rooms, structure_openings, structure_semantics, structure_path, cfg)
        semantics.update(structure_semantics)
        openings.extend(structure_openings)
        stairs.extend(structure_stairs)
        semantic_errors.extend(validate_room_semantics(structure_rooms, structure_semantics, structure_path, cfg).errors)
        opening_errors.extend(validate_openings(structure_rooms, structure_graph, structure_openings, structure_path, cfg).errors)
        stair_errors.extend(validate_stairs(structure_rooms, structure_stairs, structure_path, cfg).errors)

    errors = [*report.errors, *semantic_errors, *opening_errors, *stair_errors]
    type_counts = Counter(semantic.room_type for semantic in semantics.values())
    type_summary = ",".join(f"{room_type}:{count}" for room_type, count in sorted(type_counts.items()))
    avg_pressure = sum(room.character.pressure for room in rooms) / len(rooms) if rooms else 0.0
    avg_light_scarcity = sum(room.character.light_scarcity for room in rooms) / len(rooms) if rooms else 0.0
    avg_aperture_budget = sum(room.character.aperture_budget for room in rooms) / len(rooms) if rooms else 0.0
    axis_counts = Counter(_dominant_split_axis(room) for room in rooms)
    axis_summary = ",".join(f"{axis}:{axis_counts.get(axis, 0)}" for axis in ("x", "y", "z", "none"))
    stair_summary = ",".join(
        f"{kind}:{sum(1 for stair in stairs if stair.stair_kind == kind)}" for kind in (STAIR_KIND_STAIR, STAIR_KIND_LADDER)
    )
    total_path_room_count = sum(metrics.room_count for metrics in path_metrics_by_structure.values())
    total_path_segment_count = sum(metrics.segment_count for metrics in path_metrics_by_structure.values())
    total_path_length = sum(metrics.total_length for metrics in path_metrics_by_structure.values())
    total_path_descent = sum(metrics.total_descent for metrics in path_metrics_by_structure.values())
    avg_path_radius = (
        sum(metrics.average_radial_distance * metrics.room_count for metrics in path_metrics_by_structure.values())
        / max(1, total_path_room_count)
    )
    structure_summary = ",".join(
        f"{structure_id}:{len(structure_groups[structure_id])}rooms/{len(dante_paths.get(structure_id, []))}path"
        for structure_id in sorted(structure_groups)
    )

    print(f"rooms={report.room_count}")
    print(f"edges={report.edge_count}")
    print(f"components={len(components)}")
    print(f"structures={structure_summary}")
    print(f"path_rooms={total_path_room_count}")
    print(f"path_segments={total_path_segment_count}")
    print(f"path_length={total_path_length:.2f}m")
    print(f"path_descent={total_path_descent:.2f}m")
    print(f"path_avg_radius={avg_path_radius:.2f}m")
    print(f"avg_pressure={avg_pressure:.2f}")
    print(f"avg_light_scarcity={avg_light_scarcity:.2f}")
    print(f"avg_aperture_budget={avg_aperture_budget:.2f}")
    print(f"dominant_split_axes={axis_summary}")
    print(f"room_types={type_summary}")
    print(f"openings={len(openings)}")
    print(f"path_openings={sum(1 for opening in openings if opening.is_on_dante_path)}")
    print(f"stairs={len(stairs)}")
    print(f"stair_kinds={stair_summary}")
    print(f"errors={len(errors)}")
    print(f"module_size={cfg.module_size}m")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
    return 0 if not errors else 1


def _dominant_split_axis(room) -> str:
    axes = room.lineage.split_axes
    if not axes:
        return "none"

    total_weight = sum(range(1, len(axes) + 1))
    weights = {"x": 0.0, "y": 0.0, "z": 0.0}
    for index, axis in enumerate(axes, start=1):
        weights[axis] += index / total_weight
    return max(("x", "y", "z"), key=lambda axis: (weights[axis], axis))


if __name__ == "__main__":
    raise SystemExit(run_smoke_check())
