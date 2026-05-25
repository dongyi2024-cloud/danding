"""路径构件：依据 Dante Path 的入口/出口 opening 生成楼梯或梯子。"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .generators import AbyssConfig, RoomBox
from .openings import (
    OPENING_DROP_SHAFT,
    OPENING_LADDER,
    OPENING_STAIR_HINT,
    Opening,
    canonical_edge,
    opening_floor_aligned_bottom,
    opening_uses_floor_aligned_bottom,
    opening_vertical_size,
)
from .room_semantics import RoomSemantic


STAIR_KIND_STAIR = "stair"
STAIR_KIND_LADDER = "ladder"

LEGAL_STAIR_KINDS = frozenset({STAIR_KIND_STAIR, STAIR_KIND_LADDER})

_VERTICAL_OPENING_TYPES = frozenset({OPENING_LADDER, OPENING_DROP_SHAFT, OPENING_STAIR_HINT})


@dataclass(frozen=True)
class StairFlight:
    """房间内部的主路径通行构件。

    一个 StairFlight 不直接切洞，只表达“人如何在当前房间里从入口走到出口”。
    这样楼梯层既能服务 Blender 可视化，也能给后续真实几何细化提供参数。
    """

    id: str
    structure_id: str
    room_id: str
    entry_room_id: str
    exit_room_id: str
    stair_kind: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    path_points: tuple[tuple[float, float, float], ...]
    width: float
    step_count: int
    tread_depth: float
    riser_height: float
    required_run: float
    actual_run: float
    vertical_rise: float
    difficulty: float
    is_on_dante_path: bool


def generate_stairs(
    rooms: list[RoomBox],
    openings: list[Opening],
    semantics: dict[str, RoomSemantic],
    dante_path: list[str],
    config: AbyssConfig,
) -> list[StairFlight]:
    """为 Dante Path 中的房间生成内部通行构件。"""

    by_id = {room.id: room for room in rooms}
    openings_by_edge = {canonical_edge(opening.from_room_id, opening.to_room_id): opening for opening in openings}
    flights: list[StairFlight] = []

    for index in range(1, len(dante_path) - 1):
        previous_room_id = dante_path[index - 1]
        room_id = dante_path[index]
        next_room_id = dante_path[index + 1]
        room = by_id.get(room_id)
        incoming = openings_by_edge.get(canonical_edge(previous_room_id, room_id))
        outgoing = openings_by_edge.get(canonical_edge(room_id, next_room_id))
        semantic = semantics.get(room_id)
        if room is None or incoming is None or outgoing is None or semantic is None:
            continue

        start = _opening_point_inside_room(room, incoming, config)
        end = _opening_point_inside_room(room, outgoing, config)
        if not _needs_stair_flight(start, end, incoming, outgoing, config):
            continue

        stair_kind = _stair_kind(start, end, incoming, outgoing, config)
        width = _flight_width(room, semantic, config, stair_kind)
        if stair_kind == STAIR_KIND_LADDER:
            path_points = (start, end)
            actual_run = math.hypot(end[0] - start[0], end[1] - start[1])
            required_run = actual_run
        else:
            path_points, required_run, actual_run = _wall_hugging_stair_path(room, start, end, width, config)
        vertical_rise = abs(end[2] - start[2])
        step_count, tread_depth, riser_height = _stair_dimensions(
            width=width,
            vertical_rise=vertical_rise,
            required_run=required_run,
            actual_run=actual_run,
            config=config,
            stair_kind=stair_kind,
        )
        flights.append(
            StairFlight(
                id=f"stair_{room_id}_{previous_room_id}_{next_room_id}",
                structure_id=room.structure_id,
                room_id=room_id,
                entry_room_id=previous_room_id,
                exit_room_id=next_room_id,
                stair_kind=stair_kind,
                start=start,
                end=end,
                path_points=path_points,
                width=width,
                step_count=step_count,
                tread_depth=tread_depth,
                riser_height=riser_height,
                required_run=required_run,
                actual_run=actual_run,
                vertical_rise=vertical_rise,
                difficulty=_flight_difficulty(incoming, outgoing, semantic, stair_kind),
                is_on_dante_path=True,
            )
        )

    flights.extend(_generate_opening_access_stairs(rooms, openings, semantics, dante_path, config))
    return flights


def _generate_opening_access_stairs(
    rooms: list[RoomBox],
    openings: list[Opening],
    semantics: dict[str, RoomSemantic],
    dante_path: list[str],
    config: AbyssConfig,
) -> list[StairFlight]:
    by_id = {room.id: room for room in rooms}
    selected_edges: dict[tuple[str, str], tuple[float, float, Opening, RoomBox, RoomBox, RoomSemantic]] = {}
    path_room_ids = set(dante_path)
    path_neighbor_ids = _path_neighbor_room_ids(openings, path_room_ids)

    for opening in openings:
        if opening.opening_type != OPENING_STAIR_HINT:
            continue
        if not opening_uses_floor_aligned_bottom(opening):
            continue

        left = by_id.get(opening.from_room_id)
        right = by_id.get(opening.to_room_id)
        if left is None or right is None:
            continue
        if (
            left.id not in path_room_ids
            and right.id not in path_room_ids
            and left.id not in path_neighbor_ids
            and right.id not in path_neighbor_ids
        ):
            continue

        higher_room = left if left.min_z >= right.min_z else right
        lower_room = right if higher_room is left else left
        floor_delta = higher_room.min_z - lower_room.min_z
        if floor_delta < config.module_size * 0.12:
            continue

        semantic = semantics.get(lower_room.id)
        if semantic is None:
            continue

        host_face = _opening_face_for_room(lower_room.id, opening)
        if host_face is None:
            continue
        key = (lower_room.id, host_face)
        score = (1.0 if opening.is_on_dante_path else 0.0, floor_delta + opening.difficulty)
        current = selected_edges.get(key)
        if current is not None and current[0] >= score[0] and current[1] >= score[1]:
            continue
        selected_edges[key] = (score[0], score[1], opening, lower_room, higher_room, semantic)

    flights: list[StairFlight] = []
    for _, (_, _, opening, lower_room, higher_room, semantic) in sorted(selected_edges.items()):
        floor_delta = higher_room.min_z - lower_room.min_z

        end = _aligned_side_opening_point_inside_room(lower_room, higher_room, opening, config)
        if end is None:
            continue

        stair_kind = STAIR_KIND_STAIR
        width = _flight_width(lower_room, semantic, config, stair_kind)
        start = _opening_access_stair_start(lower_room, end, opening, width, config)
        path_points, required_run, actual_run = _wall_hugging_stair_path(lower_room, start, end, width, config)
        vertical_rise = abs(end[2] - start[2])
        if vertical_rise < config.module_size * 0.08:
            continue

        step_count, tread_depth, riser_height = _stair_dimensions(
            width=width,
            vertical_rise=vertical_rise,
            required_run=required_run,
            actual_run=actual_run,
            config=config,
            stair_kind=stair_kind,
        )
        flights.append(
            StairFlight(
                id=f"stair_access_{lower_room.id}_{higher_room.id}",
                structure_id=lower_room.structure_id,
                room_id=lower_room.id,
                entry_room_id=lower_room.id,
                exit_room_id=higher_room.id,
                stair_kind=stair_kind,
                start=start,
                end=end,
                path_points=path_points,
                width=width,
                step_count=step_count,
                tread_depth=tread_depth,
                riser_height=riser_height,
                required_run=required_run,
                actual_run=actual_run,
                vertical_rise=vertical_rise,
                difficulty=_clamp(
                    opening.difficulty * 0.55 + semantic.pressure * 0.18 + semantic.compression * 0.12,
                    0.0,
                    1.0,
                ),
                is_on_dante_path=False,
            )
        )
    return flights


def _needs_stair_flight(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    incoming: Opening,
    outgoing: Opening,
    config: AbyssConfig,
) -> bool:
    vertical_delta = abs(end[2] - start[2])
    return (
        vertical_delta >= config.module_size * 0.15
        or incoming.opening_type in _VERTICAL_OPENING_TYPES
        or outgoing.opening_type in _VERTICAL_OPENING_TYPES
    )


def _stair_kind(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    incoming: Opening,
    outgoing: Opening,
    config: AbyssConfig,
) -> str:
    horizontal_span = math.hypot(end[0] - start[0], end[1] - start[1])
    vertical_span = abs(end[2] - start[2])
    if (
        outgoing.opening_type == OPENING_LADDER
        and horizontal_span <= config.module_size * 0.6
        and vertical_span >= config.module_size * 0.65
    ):
        return STAIR_KIND_LADDER
    if (
        incoming.opening_type == OPENING_LADDER
        and horizontal_span <= config.module_size * 0.55
        and vertical_span >= config.module_size * 0.5
    ):
        return STAIR_KIND_LADDER
    return STAIR_KIND_STAIR


def _flight_width(room: RoomBox, semantic: RoomSemantic, config: AbyssConfig, stair_kind: str) -> float:
    base = config.module_size * (0.46 + semantic.circulation_bias * 0.34)
    if stair_kind == STAIR_KIND_LADDER:
        return _clamp(base * 0.55, 0.42, 0.9)
    return _clamp(base, 0.9, config.module_size * 1.25)


def _stair_dimensions(
    width: float,
    vertical_rise: float,
    required_run: float,
    actual_run: float,
    config: AbyssConfig,
    stair_kind: str,
) -> tuple[int, float, float]:
    if stair_kind == STAIR_KIND_LADDER:
        step_count = max(4, min(18, round(vertical_rise / 0.32)))
        return (step_count, width * 0.18, max(0.18, vertical_rise / step_count))

    guide_run = max(actual_run, required_run, config.module_size * 0.8)
    step_count = max(4, min(48, round(max(guide_run / 0.30, vertical_rise / 0.165))))
    tread_depth = guide_run / step_count
    riser_height = max(0.08, vertical_rise / step_count)
    return (step_count, tread_depth, riser_height)


def _flight_difficulty(
    incoming: Opening,
    outgoing: Opening,
    semantic: RoomSemantic,
    stair_kind: str,
) -> float:
    base = 0.28 if stair_kind == STAIR_KIND_STAIR else 0.46
    return _clamp(
        base
        + incoming.difficulty * 0.18
        + outgoing.difficulty * 0.28
        + semantic.pressure * 0.14
        + semantic.compression * 0.12,
        0.0,
        1.0,
    )


def _opening_point_inside_room(room: RoomBox, opening: Opening, config: AbyssConfig) -> tuple[float, float, float]:
    """把 wall/floor opening 中心点轻微推入房间内部，作为楼梯的落脚点。"""

    inset = max(config.wall_thickness * 2.0, config.module_size * 0.24)
    x, y, z = opening.center
    distances = {
        "min_x": abs(x - room.min_x),
        "max_x": abs(x - room.max_x),
        "min_y": abs(y - room.min_y),
        "max_y": abs(y - room.max_y),
        "min_z": abs(z - room.min_z),
        "max_z": abs(z - room.max_z),
    }
    nearest = min(distances, key=distances.get)

    if nearest == "min_x":
        x = room.min_x + inset
    elif nearest == "max_x":
        x = room.max_x - inset
    elif nearest == "min_y":
        y = room.min_y + inset
    elif nearest == "max_y":
        y = room.max_y - inset
    elif nearest == "min_z":
        z = room.min_z + inset
    else:
        z = room.max_z - inset

    return (
        _clamp(x, room.min_x + inset, room.max_x - inset),
        _clamp(y, room.min_y + inset, room.max_y - inset),
        _clamp(z, room.min_z + inset, room.max_z - inset),
    )


def _aligned_side_opening_point_inside_room(
    room: RoomBox,
    counterpart_room: RoomBox,
    opening: Opening,
    config: AbyssConfig,
) -> tuple[float, float, float] | None:
    point = _opening_point_inside_room(room, opening, config)
    bottom = opening_floor_aligned_bottom(room, counterpart_room, opening, config)
    if bottom is None:
        return None
    opening_height = opening_vertical_size(opening)
    wall_margin = 0.12
    target_z = bottom + opening_height * 0.5
    min_z = room.min_z + max(config.wall_thickness * 2.0, 0.16)
    max_z = room.max_z - max(wall_margin + opening_height * 0.5, 0.24)
    if max_z <= min_z:
        return None
    return (point[0], point[1], _clamp(target_z, min_z, max_z))


def _opening_access_stair_start(
    room: RoomBox,
    end: tuple[float, float, float],
    opening: Opening,
    width: float,
    config: AbyssConfig,
) -> tuple[float, float, float]:
    floor_z = room.min_z + max(config.wall_thickness * 2.0, 0.12)
    run_offset = max(config.module_size * 0.55, width * 1.45)
    center_x, center_y, _ = room.center
    dx = center_x - end[0]
    dy = center_y - end[1]
    horizontal = math.hypot(dx, dy)
    if horizontal <= 1e-6:
        if opening.orientation in {"x_pos", "x_neg"}:
            dx, dy = 0.0, 1.0
        else:
            dx, dy = 1.0, 0.0
        horizontal = 1.0
    ux = dx / horizontal
    uy = dy / horizontal
    inset = max(config.wall_thickness * 2.0, config.module_size * 0.24)
    return (
        _clamp(end[0] + ux * run_offset, room.min_x + inset, room.max_x - inset),
        _clamp(end[1] + uy * run_offset, room.min_y + inset, room.max_y - inset),
        floor_z,
    )


def _opening_face_for_room(room_id: str, opening: Opening) -> str | None:
    is_from = room_id == opening.from_room_id
    if room_id not in {opening.from_room_id, opening.to_room_id}:
        return None
    if opening.orientation == "x_pos":
        return "x_max" if is_from else "x_min"
    if opening.orientation == "x_neg":
        return "x_min" if is_from else "x_max"
    if opening.orientation == "y_pos":
        return "y_max" if is_from else "y_min"
    if opening.orientation == "y_neg":
        return "y_min" if is_from else "y_max"
    return None


def _path_neighbor_room_ids(openings: list[Opening], path_room_ids: set[str]) -> set[str]:
    neighbors: set[str] = set()
    for opening in openings:
        if opening.from_room_id in path_room_ids:
            neighbors.add(opening.to_room_id)
        if opening.to_room_id in path_room_ids:
            neighbors.add(opening.from_room_id)
    return neighbors


def _wall_hugging_stair_path(
    room: RoomBox,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    width: float,
    config: AbyssConfig,
) -> tuple[tuple[tuple[float, float, float], ...], float, float]:
    """生成贴着房间内壁盘旋的楼梯中心线。"""

    vertical_rise = abs(end[2] - start[2])
    if vertical_rise <= 1e-6:
        return ((start, end), 0.0, math.hypot(end[0] - start[0], end[1] - start[1]))

    pitch_radians = math.radians(config.stair_pitch_degrees)
    required_run = vertical_rise / max(1e-6, math.tan(pitch_radians)) + config.stair_landing_length
    wall_offset = max(config.stair_wall_clearance, width * 0.55)

    x_min = room.min_x + wall_offset
    x_max = room.max_x - wall_offset
    y_min = room.min_y + wall_offset
    y_max = room.max_y - wall_offset
    if x_max <= x_min or y_max <= y_min:
        fallback_run = math.hypot(end[0] - start[0], end[1] - start[1])
        return ((start, end), required_run, fallback_run)

    perimeter = 2.0 * ((x_max - x_min) + (y_max - y_min))
    if perimeter <= 1e-6:
        fallback_run = math.hypot(end[0] - start[0], end[1] - start[1])
        return ((start, end), required_run, fallback_run)

    start_2d = _project_to_inset_perimeter((start[0], start[1]), room, x_min, x_max, y_min, y_max)
    end_2d = _project_to_inset_perimeter((end[0], end[1]), room, x_min, x_max, y_min, y_max)
    start_s = _perimeter_scalar(start_2d, x_min, x_max, y_min, y_max)
    end_s = _perimeter_scalar(end_2d, x_min, x_max, y_min, y_max)
    base_run = (end_s - start_s) % perimeter
    if base_run < config.stair_landing_length:
        base_run += perimeter

    actual_run = base_run
    while actual_run < required_run:
        actual_run += perimeter

    scalar_points = _perimeter_breakpoints(start_s, actual_run, perimeter, x_min, x_max, y_min, y_max)
    points: list[tuple[float, float, float]] = []
    for scalar in scalar_points:
        x, y = _point_at_perimeter_scalar(scalar, perimeter, x_min, x_max, y_min, y_max)
        ratio = 0.0 if actual_run <= 1e-6 else (scalar - start_s) / actual_run
        z = start[2] + (end[2] - start[2]) * ratio
        point = (x, y, z)
        if not points or _distance_3d(points[-1], point) > 1e-6:
            points.append(point)

    if points:
        points[0] = start
        points[-1] = end
    else:
        points = [start, end]
    return (tuple(points), required_run, actual_run)


def _project_to_inset_perimeter(
    point: tuple[float, float],
    room: RoomBox,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
) -> tuple[float, float]:
    x, y = point
    distances = {
        "min_x": abs(x - room.min_x),
        "max_x": abs(x - room.max_x),
        "min_y": abs(y - room.min_y),
        "max_y": abs(y - room.max_y),
    }
    nearest = min(distances, key=distances.get)
    if nearest == "min_x":
        return (x_min, _clamp(y, y_min, y_max))
    if nearest == "max_x":
        return (x_max, _clamp(y, y_min, y_max))
    if nearest == "min_y":
        return (_clamp(x, x_min, x_max), y_min)
    return (_clamp(x, x_min, x_max), y_max)


def _perimeter_scalar(point: tuple[float, float], x_min: float, x_max: float, y_min: float, y_max: float) -> float:
    x, y = point
    width = x_max - x_min
    height = y_max - y_min
    if abs(y - y_min) <= 1e-6:
        return x - x_min
    if abs(x - x_max) <= 1e-6:
        return width + (y - y_min)
    if abs(y - y_max) <= 1e-6:
        return width + height + (x_max - x)
    return width + height + width + (y_max - y)


def _point_at_perimeter_scalar(
    scalar: float,
    perimeter: float,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
) -> tuple[float, float]:
    width = x_max - x_min
    height = y_max - y_min
    s = scalar % perimeter
    if s <= width:
        return (x_min + s, y_min)
    if s <= width + height:
        return (x_max, y_min + (s - width))
    if s <= width + height + width:
        return (x_max - (s - width - height), y_max)
    return (x_min, y_max - (s - width - height - width))


def _perimeter_breakpoints(
    start_s: float,
    actual_run: float,
    perimeter: float,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
) -> list[float]:
    width = x_max - x_min
    height = y_max - y_min
    corner_offsets = (0.0, width, width + height, width + height + width)
    end_s = start_s + actual_run
    points = [start_s]
    start_loop = math.floor(start_s / perimeter) - 1
    end_loop = math.ceil(end_s / perimeter) + 1
    for loop_index in range(start_loop, end_loop + 1):
        loop_base = loop_index * perimeter
        for offset in corner_offsets:
            scalar = loop_base + offset
            if start_s < scalar < end_s:
                points.append(scalar)
    points.append(end_s)
    points.sort()
    return points


def _distance_3d(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return math.dist(left, right)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))
