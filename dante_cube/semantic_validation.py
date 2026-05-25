"""房间语义与 Opening 的无 Blender 验证。"""

from __future__ import annotations

from dataclasses import dataclass

from .generators import AbyssConfig, RoomBox
from .openings import LEGAL_OPENING_TYPES, LEGAL_ORIENTATIONS, Opening, canonical_edge
from .pathfinding import AdjacencyGraph
from .room_semantics import LEGAL_ROOM_TYPES, ROOM_TYPE_ABYSS_EDGE, ROOM_TYPE_ENTRANCE, RoomSemantic
from .stairs import LEGAL_STAIR_KINDS, StairFlight


@dataclass(frozen=True)
class SemanticValidationReport:
    ok: bool
    errors: list[str]


def validate_room_semantics(
    rooms: list[RoomBox],
    semantics: dict[str, RoomSemantic],
    dante_path: list[str],
    config: AbyssConfig,
) -> SemanticValidationReport:
    """检查每个房间的语义记录是否完整、合法、可解释。"""

    errors: list[str] = []
    room_ids = {room.id for room in rooms}
    semantic_ids = set(semantics)

    for missing_id in sorted(room_ids - semantic_ids):
        errors.append(f"{missing_id} has no RoomSemantic")
    for extra_id in sorted(semantic_ids - room_ids):
        errors.append(f"semantic references unknown room: {extra_id}")

    for room_id, semantic in sorted(semantics.items()):
        if semantic.room_id != room_id:
            errors.append(f"{room_id} semantic room_id mismatch: {semantic.room_id}")
        if semantic.room_type not in LEGAL_ROOM_TYPES:
            errors.append(f"{room_id} has illegal room_type: {semantic.room_type}")
        _validate_unit_interval(room_id, "normalized_down", semantic.normalized_down, errors)
        _validate_unit_interval(room_id, "compression", semantic.compression, errors)
        _validate_unit_interval(room_id, "darkness", semantic.darkness, errors)
        _validate_unit_interval(room_id, "chaos", semantic.chaos, errors)
        _validate_unit_interval(room_id, "rituality", semantic.rituality, errors)
        _validate_unit_interval(room_id, "pressure", semantic.pressure, errors)
        _validate_unit_interval(room_id, "light_scarcity", semantic.light_scarcity, errors)
        _validate_unit_interval(room_id, "ceiling_bias", semantic.ceiling_bias, errors)
        _validate_unit_interval(room_id, "erosion_bias", semantic.erosion_bias, errors)
        _validate_unit_interval(room_id, "ritual_bias", semantic.ritual_bias, errors)
        _validate_unit_interval(room_id, "circulation_bias", semantic.circulation_bias, errors)

    if len(dante_path) >= 2:
        first = semantics.get(dante_path[0])
        last = semantics.get(dante_path[-1])
        if first is None or first.room_type != ROOM_TYPE_ENTRANCE:
            errors.append("Dante Path first room is not entrance")
        if last is None or last.room_type != ROOM_TYPE_ABYSS_EDGE:
            errors.append("Dante Path last room is not abyss_edge")

    type_count = len({semantic.room_type for semantic in semantics.values()})
    if semantics and type_count < 3:
        errors.append("room semantics contain fewer than 3 room types")

    # config is accepted for API symmetry and future threshold validation.
    _ = config
    return SemanticValidationReport(not errors, errors)


def validate_openings(
    rooms: list[RoomBox],
    graph: AdjacencyGraph,
    openings: list[Opening],
    dante_path: list[str],
    config: AbyssConfig,
) -> SemanticValidationReport:
    """检查 Opening 与拓扑图、路径边和合法枚举的一致性。"""

    errors: list[str] = []
    room_ids = {room.id for room in rooms}
    graph_edges = {canonical_edge(left, right) for left, neighbors in graph.items() for right in neighbors}
    seen_edges: set[tuple[str, str]] = set()
    path_edges = {canonical_edge(left, right) for left, right in zip(dante_path, dante_path[1:])}

    for opening in openings:
        edge = canonical_edge(opening.from_room_id, opening.to_room_id)
        if edge in seen_edges:
            errors.append(f"duplicate opening for edge: {edge[0]}-{edge[1]}")
        seen_edges.add(edge)

        if opening.from_room_id not in room_ids or opening.to_room_id not in room_ids:
            errors.append(f"{opening.id} references missing room")
        if edge not in graph_edges:
            errors.append(f"{opening.id} references non-adjacent rooms: {edge[0]}-{edge[1]}")
        if opening.opening_type not in LEGAL_OPENING_TYPES:
            errors.append(f"{opening.id} has illegal opening_type: {opening.opening_type}")
        if opening.orientation not in LEGAL_ORIENTATIONS:
            errors.append(f"{opening.id} has illegal orientation: {opening.orientation}")
        if len(opening.center) != 3 or not all(isinstance(value, int | float) for value in opening.center):
            errors.append(f"{opening.id} has invalid center")
        if len(opening.size) != 3 or any(value <= 0 for value in opening.size):
            errors.append(f"{opening.id} has invalid size")
        _validate_unit_interval(opening.id, "difficulty", opening.difficulty, errors)

    for edge in sorted(path_edges & graph_edges):
        if edge not in seen_edges:
            errors.append(f"missing opening for Dante Path edge: {edge[0]}-{edge[1]}")
            continue
        opening = next((item for item in openings if canonical_edge(item.from_room_id, item.to_room_id) == edge), None)
        if opening is not None and not opening.is_on_dante_path:
            errors.append(f"Dante Path opening not marked as path opening: {edge[0]}-{edge[1]}")

    # config is accepted for API symmetry and future metric validation.
    _ = config
    return SemanticValidationReport(not errors, errors)


def validate_stairs(
    rooms: list[RoomBox],
    stairs: list[StairFlight],
    dante_path: list[str],
    config: AbyssConfig,
) -> SemanticValidationReport:
    """检查主路径楼梯与高差补楼梯是否引用合法房间，并保持可解释的尺度。"""

    errors: list[str] = []
    room_ids = {room.id for room in rooms}
    path_room_ids = set(dante_path)

    for stair in stairs:
        if stair.room_id not in room_ids:
            errors.append(f"{stair.id} references unknown room: {stair.room_id}")
        if stair.entry_room_id not in room_ids:
            errors.append(f"{stair.id} references unknown entry room: {stair.entry_room_id}")
        if stair.exit_room_id not in room_ids:
            errors.append(f"{stair.id} references unknown exit room: {stair.exit_room_id}")
        if stair.stair_kind not in LEGAL_STAIR_KINDS:
            errors.append(f"{stair.id} has illegal stair_kind: {stair.stair_kind}")
        if stair.is_on_dante_path and stair.room_id not in path_room_ids:
            errors.append(f"{stair.id} is not hosted by a Dante Path room")
        if len(stair.start) != 3 or len(stair.end) != 3:
            errors.append(f"{stair.id} has invalid endpoints")
        if len(stair.path_points) < 2:
            errors.append(f"{stair.id} has too few path points")
        if stair.width <= 0:
            errors.append(f"{stair.id} has non-positive width")
        if stair.step_count <= 0:
            errors.append(f"{stair.id} has non-positive step_count")
        if stair.tread_depth <= 0:
            errors.append(f"{stair.id} has non-positive tread_depth")
        if stair.riser_height <= 0:
            errors.append(f"{stair.id} has non-positive riser_height")
        if stair.required_run < 0:
            errors.append(f"{stair.id} has negative required_run")
        if stair.actual_run < 0:
            errors.append(f"{stair.id} has negative actual_run")
        if stair.actual_run + 1e-6 < stair.required_run and stair.stair_kind != "ladder":
            errors.append(f"{stair.id} actual_run is shorter than required_run")
        _validate_unit_interval(stair.id, "difficulty", stair.difficulty, errors)

    path_stairs = [stair for stair in stairs if stair.is_on_dante_path]
    if len(dante_path) >= 3 and not path_stairs:
        errors.append("no stair flights generated for multi-room Dante Path")

    _ = config
    return SemanticValidationReport(not errors, errors)


def _validate_unit_interval(room_id: str, field_name: str, value: float, errors: list[str]) -> None:
    if not 0.0 <= value <= 1.0:
        errors.append(f"{room_id} has out-of-range {field_name}: {value}")
