"""房间语义分类：把几何 RoomBox 解释为 Dante Cube 的建筑空间单元。"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .generators import AbyssConfig, RoomBox, depth_band, room_depth_progress
from .pathfinding import AdjacencyGraph


ROOM_TYPE_ENTRANCE = "entrance"
ROOM_TYPE_MEMORIAL_HALL = "memorial_hall"
ROOM_TYPE_OVERLOOK = "overlook"
ROOM_TYPE_TRANSITION = "transition"
ROOM_TYPE_CORRIDOR = "corridor"
ROOM_TYPE_COMPRESSION = "compression"
ROOM_TYPE_DESCENT_CHAMBER = "descent_chamber"
ROOM_TYPE_PENITENCE_CELL = "penitence_cell"
ROOM_TYPE_RUIN_CHAMBER = "ruin_chamber"
ROOM_TYPE_ABYSS_EDGE = "abyss_edge"
ROOM_TYPE_SIDE_VOID = "side_void"
ROOM_TYPE_LOST_ROOM = "lost_room"

LEGAL_ROOM_TYPES = frozenset(
    {
        ROOM_TYPE_ENTRANCE,
        ROOM_TYPE_MEMORIAL_HALL,
        ROOM_TYPE_OVERLOOK,
        ROOM_TYPE_TRANSITION,
        ROOM_TYPE_CORRIDOR,
        ROOM_TYPE_COMPRESSION,
        ROOM_TYPE_DESCENT_CHAMBER,
        ROOM_TYPE_PENITENCE_CELL,
        ROOM_TYPE_RUIN_CHAMBER,
        ROOM_TYPE_ABYSS_EDGE,
        ROOM_TYPE_SIDE_VOID,
        ROOM_TYPE_LOST_ROOM,
    }
)


@dataclass(frozen=True)
class RoomSemantic:
    """房间的叙事属性。

    normalized_down 越接近 1，房间越接近当前结构的递归终点；
    对下方立方体来说是更深处，对上方镜像立方体来说是更高处。
    compression/darkness/chaos 是后续材质、灯光和 Geometry Nodes 可以直接消费的 0-1 强度。
    """

    room_id: str
    room_type: str
    depth_band: int
    normalized_down: float
    radial_distance: float
    volume: float
    compression: float
    darkness: float
    chaos: float
    rituality: float
    pressure: float
    light_scarcity: float
    ceiling_bias: float
    erosion_bias: float
    ritual_bias: float
    circulation_bias: float
    is_on_dante_path: bool


def classify_rooms(
    rooms: list[RoomBox],
    graph: AdjacencyGraph,
    dante_path: list[str],
    config: AbyssConfig,
) -> dict[str, RoomSemantic]:
    """为每个房间生成一个稳定的建筑语义记录。"""

    path_set = set(dante_path)
    path_index = {room_id: index for index, room_id in enumerate(dante_path)}
    first_path_id = dante_path[0] if dante_path else None
    last_path_id = dante_path[-1] if dante_path else None
    max_radius = max(1.0, math.sqrt(2.0) * config.cube_size / 2)

    semantics: dict[str, RoomSemantic] = {}
    for room in rooms:
        metrics = compute_room_metrics(room, graph, path_set, max_radius, config)
        room_type = _classify_room_type(
            room=room,
            graph=graph,
            metrics=metrics,
            first_path_id=first_path_id,
            last_path_id=last_path_id,
            path_index=path_index,
        )
        semantics[room.id] = RoomSemantic(room_id=room.id, room_type=room_type, **metrics)
    return semantics


def compute_room_metrics(
    room: RoomBox,
    graph: AdjacencyGraph,
    path_set: set[str],
    max_radius: float,
    config: AbyssConfig,
) -> dict[str, float | int | bool]:
    x, y, _ = room.center
    normalized_down = room_depth_progress(room)
    radial_distance = math.sqrt(x * x + y * y)
    volume_ratio = room.volume / max(1.0, config.cube_size**3)
    character = room.character

    # 递归压缩感：小体量、深层、低连接度都会更幽闭。
    degree = len(graph.get(room.id, ()))
    low_connectivity = 1.0 - _clamp(degree / 6.0, 0.0, 1.0)
    compression = _clamp(
        (1.0 - volume_ratio * 18.0) * 0.52
        + character.pressure * 0.26
        + character.ceiling_bias * 0.14
        + low_connectivity * 0.08,
        0.0,
        1.0,
    )
    darkness = _clamp(_smoothstep(normalized_down) * 0.72 + character.light_scarcity * 0.28, 0.0, 1.0)
    recursive_pressure = _clamp(room.depth / max(1, config.max_depth + config.lower_extra_depth), 0.0, 1.0)
    chaos = _clamp(
        _smoothstep(normalized_down) * (0.62 + 0.18 * recursive_pressure + 0.20 * character.erosion_bias),
        0.0,
        1.0,
    )
    is_on_path = room.id in path_set
    rituality = (
        _clamp(0.82 + character.ritual_bias * 0.18, 0.0, 1.0)
        if is_on_path
        else _clamp((1.0 - radial_distance / max_radius) * 0.20 + character.ritual_bias * 0.25, 0.0, 1.0)
    )

    return {
        "depth_band": depth_band(room, config),
        "normalized_down": normalized_down,
        "radial_distance": radial_distance,
        "volume": float(room.volume),
        "compression": compression,
        "darkness": darkness,
        "chaos": chaos,
        "rituality": rituality,
        "pressure": character.pressure,
        "light_scarcity": character.light_scarcity,
        "ceiling_bias": character.ceiling_bias,
        "erosion_bias": character.erosion_bias,
        "ritual_bias": character.ritual_bias,
        "circulation_bias": character.circulation_bias,
        "is_on_dante_path": is_on_path,
    }


def _classify_room_type(
    room: RoomBox,
    graph: AdjacencyGraph,
    metrics: dict[str, float | int | bool],
    first_path_id: str | None,
    last_path_id: str | None,
    path_index: dict[str, int],
) -> str:
    normalized_down = float(metrics["normalized_down"])
    radial_distance = float(metrics["radial_distance"])
    volume = float(metrics["volume"])
    compression = float(metrics["compression"])
    chaos = float(metrics["chaos"])
    pressure = float(metrics["pressure"])
    ceiling_bias = float(metrics["ceiling_bias"])
    erosion_bias = float(metrics["erosion_bias"])
    ritual_bias = float(metrics["ritual_bias"])
    circulation_bias = float(metrics["circulation_bias"])
    is_on_path = bool(metrics["is_on_dante_path"])
    degree = len(graph.get(room.id, ()))
    has_downward_path_connection = _has_downward_path_connection(room.id, path_index, graph)

    if room.id == first_path_id:
        return ROOM_TYPE_ENTRANCE
    if room.id == last_path_id:
        return ROOM_TYPE_ABYSS_EDGE
    if normalized_down < 0.22 and volume >= 900 and ritual_bias >= 0.48:
        return ROOM_TYPE_MEMORIAL_HALL
    if normalized_down < 0.28 and radial_distance <= 9 and ritual_bias >= 0.44:
        return ROOM_TYPE_OVERLOOK
    if is_on_path and has_downward_path_connection and circulation_bias >= 0.36:
        return ROOM_TYPE_DESCENT_CHAMBER
    if is_on_path and compression + ceiling_bias * 0.18 >= 0.58:
        return ROOM_TYPE_COMPRESSION
    if is_on_path and degree == 2 and circulation_bias >= 0.52:
        return ROOM_TYPE_CORRIDOR
    if normalized_down > 0.72 and chaos + erosion_bias * 0.12 >= 0.68:
        return ROOM_TYPE_RUIN_CHAMBER
    if normalized_down > 0.62 and pressure + ceiling_bias * 0.12 >= 0.62:
        return ROOM_TYPE_PENITENCE_CELL
    if not is_on_path and degree <= 1 and circulation_bias <= 0.42:
        return ROOM_TYPE_LOST_ROOM
    if not is_on_path and radial_distance >= 13 and ritual_bias <= 0.52:
        return ROOM_TYPE_SIDE_VOID
    return ROOM_TYPE_TRANSITION


def _has_downward_path_connection(room_id: str, path_index: dict[str, int], graph: AdjacencyGraph) -> bool:
    index = path_index.get(room_id)
    if index is None:
        return False
    next_path_ids = {path_id for path_id, path_pos in path_index.items() if path_pos == index + 1}
    return bool(next_path_ids & graph.get(room_id, set()))


def _smoothstep(value: float) -> float:
    value = _clamp(value, 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))
