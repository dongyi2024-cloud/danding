"""无 Blender 验证：用于快速检查空间逻辑是否成立。"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .generators import AbyssConfig, RoomBox, rooms_by_depth, structure_bounds_from_room
from .pathfinding import AdjacencyGraph


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    errors: list[str]
    room_count: int
    edge_count: int


def validate_rooms(rooms: list[RoomBox], graph: AdjacencyGraph, config: AbyssConfig) -> ValidationReport:
    errors: list[str] = []
    if not rooms:
        errors.append("no rooms generated")

    _validate_module_alignment(rooms, config, errors)
    _validate_bounds(rooms, config, errors)
    _validate_graph_coverage(rooms, graph, errors)
    _validate_room_character_ranges(rooms, errors)
    _validate_lineage_consistency(rooms, errors)
    _validate_depth_trend(rooms, config, errors)

    edge_count = sum(len(neighbors) for neighbors in graph.values()) // 2
    return ValidationReport(not errors, errors, len(rooms), edge_count)


def _validate_module_alignment(rooms: list[RoomBox], config: AbyssConfig, errors: list[str]) -> None:
    module = config.module_size
    for room in rooms:
        values = room.bounds()
        dimensions = (room.width, room.depth_y, room.height)
        if any(value % module != 0 for value in values + dimensions):
            errors.append(f"{room.id} is not aligned to {module}m module")


def _validate_bounds(rooms: list[RoomBox], config: AbyssConfig, errors: list[str]) -> None:
    for room in rooms:
        min_x, min_y, min_z, max_x, max_y, max_z = structure_bounds_from_room(room)
        if (
            room.min_x < min_x
            or room.min_y < min_y
            or room.min_z < min_z
            or room.max_x > max_x
            or room.max_y > max_y
            or room.max_z > max_z
        ):
            errors.append(f"{room.id} exceeds cube bounds")


def _validate_graph_coverage(rooms: list[RoomBox], graph: AdjacencyGraph, errors: list[str]) -> None:
    room_ids = {room.id for room in rooms}
    graph_ids = set(graph)
    if room_ids != graph_ids:
        errors.append("adjacency graph nodes do not match generated rooms")
    for node, neighbors in graph.items():
        missing = neighbors - room_ids
        if missing:
            errors.append(f"{node} references missing neighbors: {sorted(missing)}")


def _validate_depth_trend(rooms: list[RoomBox], config: AbyssConfig, errors: list[str]) -> None:
    groups = rooms_by_depth(rooms, config)
    if len(groups) < 2:
        return

    ordered = [groups[key] for key in sorted(groups)]
    avg_volumes = [_average(room.volume for room in group) for group in ordered]
    avg_distances = [_average(_horizontal_distance(room) for room in group) for group in ordered]
    avg_pressures = [_average(room.character.pressure for room in group) for group in ordered]
    avg_light_scarcity = [_average(room.character.light_scarcity for room in group) for group in ordered]

    if avg_volumes[-1] > avg_volumes[0]:
        errors.append("lower depth bands are not more compressed by volume")
    if avg_distances[-1] > avg_distances[0]:
        errors.append("lower depth bands are not more center biased")
    if avg_pressures[-1] < avg_pressures[0]:
        errors.append("lower depth bands are not more pressurized by room character")
    if avg_light_scarcity[-1] < avg_light_scarcity[0]:
        errors.append("lower depth bands are not darker by room character")


def _validate_room_character_ranges(rooms: list[RoomBox], errors: list[str]) -> None:
    for room in rooms:
        character_fields = {
            "pressure": room.character.pressure,
            "light_scarcity": room.character.light_scarcity,
            "ceiling_bias": room.character.ceiling_bias,
            "erosion_bias": room.character.erosion_bias,
            "ritual_bias": room.character.ritual_bias,
            "circulation_bias": room.character.circulation_bias,
            "aperture_budget": room.character.aperture_budget,
        }
        for field_name, value in character_fields.items():
            if not 0.0 <= value <= 1.0:
                errors.append(f"{room.id} has out-of-range character {field_name}: {value}")


def _validate_lineage_consistency(rooms: list[RoomBox], errors: list[str]) -> None:
    for room in rooms:
        if len(room.lineage.split_axes) != room.depth:
            errors.append(f"{room.id} lineage axis count does not match recursion depth")
        if len(room.lineage.split_biases) != room.depth:
            errors.append(f"{room.id} lineage bias count does not match recursion depth")
        wall_exposures = {
            "wall_exposure_x_min": room.lineage.wall_exposure_x_min,
            "wall_exposure_x_max": room.lineage.wall_exposure_x_max,
            "wall_exposure_y_min": room.lineage.wall_exposure_y_min,
            "wall_exposure_y_max": room.lineage.wall_exposure_y_max,
        }
        for field_name, value in wall_exposures.items():
            if not 0.0 <= value <= 1.0:
                errors.append(f"{room.id} has out-of-range lineage {field_name}: {value}")


def _horizontal_distance(room: RoomBox) -> float:
    x, y, _ = room.center
    return math.sqrt(x * x + y * y)


def _average(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0
