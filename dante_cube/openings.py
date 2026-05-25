"""Opening 逻辑：把邻接图边解释为门洞、裂缝、竖井和封闭关系。"""

from __future__ import annotations

from dataclasses import dataclass
import random

from .generators import AbyssConfig, RoomBox
from .pathfinding import AdjacencyGraph
from .room_semantics import RoomSemantic


OPENING_DOOR = "door"
OPENING_CRACK = "crack"
OPENING_LADDER = "ladder"
OPENING_DROP_SHAFT = "drop_shaft"
OPENING_STAIR_HINT = "stair_hint"
OPENING_RITUAL_GATE = "ritual_gate"
OPENING_BLOCKED = "blocked"

LEGAL_OPENING_TYPES = frozenset(
    {
        OPENING_DOOR,
        OPENING_CRACK,
        OPENING_LADDER,
        OPENING_DROP_SHAFT,
        OPENING_STAIR_HINT,
        OPENING_RITUAL_GATE,
        OPENING_BLOCKED,
    }
)

FLOOR_ALIGNED_OPENING_TYPES = frozenset({OPENING_DOOR, OPENING_RITUAL_GATE, OPENING_STAIR_HINT})

ORIENTATION_X_POS = "x_pos"
ORIENTATION_X_NEG = "x_neg"
ORIENTATION_Y_POS = "y_pos"
ORIENTATION_Y_NEG = "y_neg"
ORIENTATION_Z_UP = "z_up"
ORIENTATION_Z_DOWN = "z_down"

LEGAL_ORIENTATIONS = frozenset(
    {
        ORIENTATION_X_POS,
        ORIENTATION_X_NEG,
        ORIENTATION_Y_POS,
        ORIENTATION_Y_NEG,
        ORIENTATION_Z_UP,
        ORIENTATION_Z_DOWN,
    }
)


@dataclass(frozen=True)
class Opening:
    """两个相邻房间之间的一条建筑通行或封闭关系。"""

    id: str
    from_room_id: str
    to_room_id: str
    opening_type: str
    orientation: str
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    is_on_dante_path: bool
    difficulty: float


def generate_openings(
    rooms: list[RoomBox],
    graph: AdjacencyGraph,
    semantics: dict[str, RoomSemantic],
    dante_path: list[str],
    config: AbyssConfig,
) -> list[Opening]:
    """为 graph 中每条无向边生成一个 canonical Opening。"""

    by_id = {room.id: room for room in rooms}
    path_edges = _path_edge_set(dante_path)
    path_room_ids = set(dante_path)
    path_neighbor_ids = _path_neighbor_room_ids(graph, path_room_ids)
    openings: list[Opening] = []

    for left_id, right_id in sorted(canonical_edge(left, right) for left, neighbors in graph.items() for right in neighbors if left < right):
        left = by_id.get(left_id)
        right = by_id.get(right_id)
        if left is None or right is None:
            continue

        orientation = opening_orientation(left, right)
        is_path = canonical_edge(left_id, right_id) in path_edges
        opening_type = _opening_type(
            left,
            right,
            orientation,
            is_path,
            semantics,
            path_room_ids,
            path_neighbor_ids,
            config,
        )
        center = _opening_center(left, right, orientation)
        size = _opening_size(opening_type, orientation, config)
        difficulty = _difficulty(opening_type, left, right, semantics)
        openings.append(
            Opening(
                id=f"opening_{left_id}_{right_id}",
                from_room_id=left_id,
                to_room_id=right_id,
                opening_type=opening_type,
                orientation=orientation,
                center=center,
                size=size,
                is_on_dante_path=is_path,
                difficulty=difficulty,
            )
        )
    return openings


def canonical_edge(left_id: str, right_id: str) -> tuple[str, str]:
    return (left_id, right_id) if left_id <= right_id else (right_id, left_id)


def opening_orientation(left: RoomBox, right: RoomBox) -> str:
    """从 left 指向 right 的主方向；canonical edge 保证结果稳定。"""

    lx, ly, lz = left.center
    rx, ry, rz = right.center
    dx = rx - lx
    dy = ry - ly
    dz = rz - lz
    axis = max((("x", abs(dx)), ("y", abs(dy)), ("z", abs(dz))), key=lambda item: (item[1], item[0]))[0]

    if axis == "z":
        return ORIENTATION_Z_UP if dz > 0 else ORIENTATION_Z_DOWN
    if axis == "y":
        return ORIENTATION_Y_POS if dy > 0 else ORIENTATION_Y_NEG
    return ORIENTATION_X_POS if dx > 0 else ORIENTATION_X_NEG


def _path_edge_set(dante_path: list[str]) -> set[tuple[str, str]]:
    return {canonical_edge(left_id, right_id) for left_id, right_id in zip(dante_path, dante_path[1:])}


def _opening_type(
    left: RoomBox,
    right: RoomBox,
    orientation: str,
    is_path: bool,
    semantics: dict[str, RoomSemantic],
    path_room_ids: set[str],
    path_neighbor_ids: set[str],
    config: AbyssConfig,
) -> str:
    average_down = (_semantic_value(left.id, semantics, "normalized_down") + _semantic_value(right.id, semantics, "normalized_down")) / 2
    average_chaos = (_semantic_value(left.id, semantics, "chaos") + _semantic_value(right.id, semantics, "chaos")) / 2

    if is_path:
        if orientation in {ORIENTATION_X_POS, ORIENTATION_X_NEG, ORIENTATION_Y_POS, ORIENTATION_Y_NEG}:
            return OPENING_RITUAL_GATE
        if orientation == ORIENTATION_Z_UP:
            return OPENING_LADDER
        return OPENING_DROP_SHAFT if average_down > 0.58 else OPENING_STAIR_HINT

    if orientation in {ORIENTATION_X_POS, ORIENTATION_X_NEG, ORIENTATION_Y_POS, ORIENTATION_Y_NEG}:
        if _should_promote_to_stair_hint(left, right, path_room_ids, path_neighbor_ids, config):
            return OPENING_STAIR_HINT
        if average_down > 0.72 and average_chaos > 0.64:
            return OPENING_RITUAL_GATE
        return OPENING_DOOR

    if average_down > 0.76 and average_chaos > 0.7:
        return OPENING_LADDER
    return OPENING_LADDER if orientation == ORIENTATION_Z_UP else OPENING_STAIR_HINT


def _opening_center(left: RoomBox, right: RoomBox, orientation: str) -> tuple[float, float, float]:
    if orientation in {ORIENTATION_X_POS, ORIENTATION_X_NEG}:
        x = (left.max_x + right.min_x) / 2 if left.center[0] <= right.center[0] else (right.max_x + left.min_x) / 2
        y = _overlap_mid(left.min_y, left.max_y, right.min_y, right.max_y)
        z = _overlap_mid(left.min_z, left.max_z, right.min_z, right.max_z)
        return (x, y, z)
    if orientation in {ORIENTATION_Y_POS, ORIENTATION_Y_NEG}:
        x = _overlap_mid(left.min_x, left.max_x, right.min_x, right.max_x)
        y = (left.max_y + right.min_y) / 2 if left.center[1] <= right.center[1] else (right.max_y + left.min_y) / 2
        z = _overlap_mid(left.min_z, left.max_z, right.min_z, right.max_z)
        return (x, y, z)

    x = _overlap_mid(left.min_x, left.max_x, right.min_x, right.max_x)
    y = _overlap_mid(left.min_y, left.max_y, right.min_y, right.max_y)
    z = (left.max_z + right.min_z) / 2 if left.center[2] <= right.center[2] else (right.max_z + left.min_z) / 2
    return (x, y, z)


def _opening_size(opening_type: str, orientation: str, config: AbyssConfig) -> tuple[float, float, float]:
    thickness = 0.08
    if opening_type == OPENING_RITUAL_GATE:
        width, height, thickness = 1.8, 2.8, 0.08
    elif opening_type == OPENING_DOOR:
        width, height, thickness = 1.2, 2.2, 0.08
    elif opening_type == OPENING_CRACK:
        width, height, thickness = 0.3, 2.8, 0.04
    elif opening_type == OPENING_BLOCKED:
        width, height, thickness = 1.4, 2.4, 0.06
    else:
        width, height, thickness = config.module_size * 0.55, config.module_size * 0.55, 0.08

    if orientation in {ORIENTATION_X_POS, ORIENTATION_X_NEG}:
        return (thickness, width, height)
    if orientation in {ORIENTATION_Y_POS, ORIENTATION_Y_NEG}:
        return (width, thickness, height)
    return (width, height, thickness)


def opening_uses_floor_aligned_bottom(opening: Opening) -> bool:
    return (
        opening.opening_type in FLOOR_ALIGNED_OPENING_TYPES
        and opening.orientation in {ORIENTATION_X_POS, ORIENTATION_X_NEG, ORIENTATION_Y_POS, ORIENTATION_Y_NEG}
    )


def opening_vertical_jitter(opening: Opening, config: AbyssConfig) -> float:
    if config.opening_vertical_jitter <= 0:
        return 0.0
    stable_seed = config.seed * 1009 + sum((index + 1) * ord(ch) for index, ch in enumerate(opening.id))
    rng = random.Random(stable_seed)
    return rng.uniform(-config.opening_vertical_jitter, config.opening_vertical_jitter)


def opening_floor_aligned_bottom(
    left: RoomBox,
    right: RoomBox,
    opening: Opening,
    config: AbyssConfig,
) -> float | None:
    if not opening_uses_floor_aligned_bottom(opening):
        return None
    reference_floor = max(left.min_z, right.min_z)
    return reference_floor + config.opening_sill_offset + opening_vertical_jitter(opening, config)


def opening_vertical_size(opening: Opening) -> float:
    if opening.orientation in {ORIENTATION_X_POS, ORIENTATION_X_NEG, ORIENTATION_Y_POS, ORIENTATION_Y_NEG}:
        return opening.size[2]
    if opening.orientation in {ORIENTATION_Z_UP, ORIENTATION_Z_DOWN}:
        return opening.size[1]
    return max(opening.size)


def _difficulty(
    opening_type: str,
    left: RoomBox,
    right: RoomBox,
    semantics: dict[str, RoomSemantic],
) -> float:
    base = {
        OPENING_RITUAL_GATE: 0.18,
        OPENING_DOOR: 0.25,
        OPENING_STAIR_HINT: 0.42,
        OPENING_LADDER: 0.58,
        OPENING_DROP_SHAFT: 0.72,
        OPENING_CRACK: 0.78,
        OPENING_BLOCKED: 1.0,
    }[opening_type]
    compression = (_semantic_value(left.id, semantics, "compression") + _semantic_value(right.id, semantics, "compression")) / 2
    chaos = (_semantic_value(left.id, semantics, "chaos") + _semantic_value(right.id, semantics, "chaos")) / 2
    return _clamp(base * 0.68 + compression * 0.18 + chaos * 0.14, 0.0, 1.0)


def _semantic_value(room_id: str, semantics: dict[str, RoomSemantic], name: str) -> float:
    semantic = semantics.get(room_id)
    return float(getattr(semantic, name, 0.0)) if semantic is not None else 0.0


def _path_neighbor_room_ids(
    graph: AdjacencyGraph,
    path_room_ids: set[str],
) -> set[str]:
    neighbors: set[str] = set()
    for room_id in path_room_ids:
        neighbors.update(graph.get(room_id, set()))
    return neighbors - path_room_ids


def _should_promote_to_stair_hint(
    left: RoomBox,
    right: RoomBox,
    path_room_ids: set[str],
    path_neighbor_ids: set[str],
    config: AbyssConfig,
) -> bool:
    near_path = (
        left.id in path_room_ids
        or right.id in path_room_ids
        or left.id in path_neighbor_ids
        or right.id in path_neighbor_ids
    )
    if not near_path:
        return False

    floor_delta = abs(left.min_z - right.min_z)
    if floor_delta < config.module_size:
        return False

    edge_key = canonical_edge(left.id, right.id)
    touch_path = left.id in path_room_ids or right.id in path_room_ids
    threshold = 0.20
    if floor_delta >= config.module_size * 2:
        threshold += 0.08
    if floor_delta >= config.module_size * 3:
        threshold += 0.06
    if touch_path:
        threshold += 0.10

    return _stable_edge_noise(edge_key, config.seed) < threshold


def _stable_edge_noise(edge_key: tuple[str, str], seed: int) -> float:
    token = f"{edge_key[0]}|{edge_key[1]}|{seed}"
    value = 0
    for index, char in enumerate(token, start=1):
        value += index * ord(char)
    return (value % 1000) / 1000.0


def _overlap_mid(a_min: float, a_max: float, b_min: float, b_max: float) -> float:
    overlap_min = max(a_min, b_min)
    overlap_max = min(a_max, b_max)
    if overlap_min < overlap_max:
        return (overlap_min + overlap_max) / 2
    return (a_min + a_max + b_min + b_max) / 4


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))
