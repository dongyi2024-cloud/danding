"""拓扑连接与 Dante agent 寻路。"""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
from typing import Iterable

from .generators import AbyssConfig, RoomBox, room_depth_progress, rooms_by_depth

AdjacencyGraph = dict[str, set[str]]


@dataclass(frozen=True)
class DantePathMetrics:
    room_count: int
    segment_count: int
    total_length: float
    total_descent: float
    total_ascent: float
    average_radial_distance: float
    max_radial_distance: float


def build_adjacency_graph(rooms: Iterable[RoomBox], module_size: int = 3) -> AdjacencyGraph:
    """基于面接触或一模数近接关系建立无向邻接图。"""

    room_list = list(rooms)
    graph: dict[str, set[str]] = {room.id: set() for room in room_list}
    for index, left in enumerate(room_list):
        for right in room_list[index + 1 :]:
            if left.structure_id != right.structure_id:
                continue
            if are_adjacent(left, right, module_size):
                graph[left.id].add(right.id)
                graph[right.id].add(left.id)
    return graph


def are_adjacent(left: RoomBox, right: RoomBox, module_size: int = 3) -> bool:
    gaps = (
        _axis_gap(left.min_x, left.max_x, right.min_x, right.max_x),
        _axis_gap(left.min_y, left.max_y, right.min_y, right.max_y),
        _axis_gap(left.min_z, left.max_z, right.min_z, right.max_z),
    )
    touching_axes = sum(1 for gap in gaps if 0 <= gap <= module_size)
    overlapping_axes = sum(
        1
        for a_min, a_max, b_min, b_max in (
            (left.min_x, left.max_x, right.min_x, right.max_x),
            (left.min_y, left.max_y, right.min_y, right.max_y),
            (left.min_z, left.max_z, right.min_z, right.max_z),
        )
        if _overlap_length(a_min, a_max, b_min, b_max) > 0
    )
    return touching_axes >= 1 and overlapping_axes >= 2


def graph_degrees(graph: AdjacencyGraph) -> dict[str, int]:
    return {node: len(neighbors) for node, neighbors in graph.items()}


def connected_components(graph: AdjacencyGraph) -> list[set[str]]:
    unseen = set(graph)
    components: list[set[str]] = []
    while unseen:
        start = unseen.pop()
        stack = [start]
        component = {start}
        while stack:
            node = stack.pop()
            for neighbor in graph[node]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    component.add(neighbor)
                    stack.append(neighbor)
        components.append(component)
    return components


def find_dante_path(rooms: Iterable[RoomBox], graph: AdjacencyGraph, config: AbyssConfig) -> list[str]:
    """用 A* 找出一条从顶部入口到底部深渊目标的 Dante agent 路径。

    建筑意义：
    - 起点选择最高、最靠近中心的房间，像从纪念立方体顶端进入；
    - 终点选择最低、最靠近中心的房间，像被深渊中心牵引；
    - 代价函数鼓励向下、靠近中心，并轻微惩罚直线坠落，让路径更像被维吉尔引导的盘旋下降。
    """

    room_list = list(rooms)
    if not room_list:
        return []

    by_id = {room.id: room for room in room_list}
    start = min(room_list, key=lambda room: (room_depth_progress(room), _radial_distance(room)))
    goal = min(room_list, key=lambda room: (-room_depth_progress(room), _radial_distance(room)))

    if start.id == goal.id:
        return [start.id]

    targets = _dante_waypoints(room_list, start, goal, config)
    full_path = [start.id]
    current = start
    for target in targets:
        segment = _a_star_segment(current, target, by_id, graph, config)
        if len(segment) > 1:
            full_path.extend(segment[1:])
        current = target
    return _dedupe_consecutive(full_path)


def measure_dante_path(rooms: Iterable[RoomBox], dante_path: list[str]) -> DantePathMetrics:
    """把路径转成可读的空间指标，便于后续按氛围调参。"""

    by_id = {room.id: room for room in rooms}
    path_rooms = [by_id[room_id] for room_id in dante_path if room_id in by_id]
    if not path_rooms:
        return DantePathMetrics(0, 0, 0.0, 0.0, 0.0, 0.0, 0.0)

    total_length = 0.0
    total_descent = 0.0
    total_ascent = 0.0
    radial_distances = [_radial_distance(room) for room in path_rooms]

    for left, right in zip(path_rooms, path_rooms[1:]):
        total_length += math.dist(left.center, right.center)
        vertical_delta = right.center[2] - left.center[2]
        total_descent += max(0.0, -vertical_delta)
        total_ascent += max(0.0, vertical_delta)

    return DantePathMetrics(
        room_count=len(path_rooms),
        segment_count=max(0, len(path_rooms) - 1),
        total_length=total_length,
        total_descent=total_descent,
        total_ascent=total_ascent,
        average_radial_distance=sum(radial_distances) / len(radial_distances),
        max_radial_distance=max(radial_distances),
    )


def _a_star_segment(
    start: RoomBox,
    goal: RoomBox,
    by_id: dict[str, RoomBox],
    graph: AdjacencyGraph,
    config: AbyssConfig,
) -> list[str]:
    queue: list[tuple[float, int, str]] = []
    heapq.heappush(queue, (0.0, 0, start.id))
    came_from: dict[str, str | None] = {start.id: None}
    cost_so_far: dict[str, float] = {start.id: 0.0}
    steps = 0

    while queue:
        _, _, current_id = heapq.heappop(queue)
        if current_id == goal.id:
            break

        current = by_id[current_id]
        for next_id in sorted(graph.get(current_id, ())):
            neighbor = by_id[next_id]
            new_cost = cost_so_far[current_id] + _dante_step_cost(current, neighbor, goal, config)
            if next_id not in cost_so_far or new_cost < cost_so_far[next_id]:
                cost_so_far[next_id] = new_cost
                steps += 1
                priority = new_cost + _dante_heuristic(neighbor, goal, config)
                heapq.heappush(queue, (priority, steps, next_id))
                came_from[next_id] = current_id

    if goal.id not in came_from:
        return [start.id]

    path = [goal.id]
    while path[-1] != start.id:
        previous = came_from[path[-1]]
        if previous is None:
            break
        path.append(previous)
    path.reverse()
    return path


def _dante_waypoints(
    rooms: list[RoomBox],
    start: RoomBox,
    goal: RoomBox,
    config: AbyssConfig,
) -> list[RoomBox]:
    targets: list[RoomBox] = []
    used = {start.id}
    for _, band_rooms in sorted(rooms_by_depth(rooms, config).items()):
        candidates = [room for room in band_rooms if room.id not in used]
        if not candidates:
            continue
        waypoint = min(
            candidates,
            key=lambda room: (
                _radial_distance(room),
                abs(room.center[2] - goal.center[2]) * config.path_waypoint_goal_bias,
            ),
        )
        if waypoint.id != goal.id:
            targets.append(waypoint)
            used.add(waypoint.id)
    if not targets or targets[-1].id != goal.id:
        targets.append(goal)
    return targets


def _dedupe_consecutive(room_ids: list[str]) -> list[str]:
    deduped: list[str] = []
    for room_id in room_ids:
        if not deduped or deduped[-1] != room_id:
            deduped.append(room_id)
    return deduped


def _axis_gap(a_min: int, a_max: int, b_min: int, b_max: int) -> int:
    if a_max < b_min:
        return b_min - a_max
    if b_max < a_min:
        return a_min - b_max
    return 0


def _overlap_length(a_min: int, a_max: int, b_min: int, b_max: int) -> int:
    return max(0, min(a_max, b_max) - max(a_min, b_min))


def _dante_step_cost(current: RoomBox, neighbor: RoomBox, goal: RoomBox, config: AbyssConfig) -> float:
    cx, cy, cz = current.center
    nx, ny, nz = neighbor.center
    distance = math.dist((cx, cy, cz), (nx, ny, nz))
    depth_delta = room_depth_progress(neighbor) - room_depth_progress(current)
    radial_pull = _radial_distance(neighbor) / max(1.0, config.cube_size / 2)
    goal_pull = math.dist(neighbor.center, goal.center) / max(1.0, config.cube_size)

    upward_penalty = max(0.0, -depth_delta) * config.path_upward_penalty * config.cube_size
    downward_reward = max(0.0, depth_delta) * config.path_downward_reward * config.cube_size
    direct_drop_penalty = (
        config.path_direct_drop_penalty
        if depth_delta > 0 and abs(nx - cx) + abs(ny - cy) < config.module_size
        else 0.0
    )

    return max(
        0.1,
        distance
        + upward_penalty
        + radial_pull * config.path_radial_pull
        + goal_pull * config.path_goal_pull
        + direct_drop_penalty
        - downward_reward,
    )


def _dante_heuristic(room: RoomBox, goal: RoomBox, config: AbyssConfig) -> float:
    return (
        math.dist(room.center, goal.center) * config.path_heuristic_distance_weight
        + _radial_distance(room) * config.path_heuristic_radial_weight
    )


def _radial_distance(room: RoomBox) -> float:
    x, y, _ = room.center
    return math.sqrt(x * x + y * y)
