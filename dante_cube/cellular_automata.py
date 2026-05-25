"""3D 细胞自动机：把深层 RoomBox 腐蚀成可实例化的体素点云。"""

from __future__ import annotations

from dataclasses import dataclass
import random

from .generators import AbyssConfig, RoomBox


@dataclass(frozen=True)
class SurvivorPoint:
    """存活体素中心点。

    这里输出的是点云，不直接输出小方块；Blender 端用单个 Mesh 承载所有顶点，
    后续交给 Geometry Nodes 的 Instance on Points 实例化体素。
    """

    co: tuple[float, float, float]
    voxel_size: float
    source_room_id: str


_NEIGHBOR_OFFSETS = tuple(
    (dx, dy, dz)
    for dx in (-1, 0, 1)
    for dy in (-1, 0, 1)
    for dz in (-1, 0, 1)
    if not (dx == 0 and dy == 0 and dz == 0)
)


def should_collapse_room(room: RoomBox, config: AbyssConfig) -> bool:
    """判断房间是否进入 CA 溃散层。

    建筑意义：
    - 深渊底层：空间被压力和风化吞噬，允许从理性 Box 退化为体素废墟。
    - 最大递归深度：算法切分已经抵达极限，继续用完整方块会显得过于现代主义。
    """

    _, _, center_z = room.center
    normalized_down = min(1.0, max(0.0, -center_z / config.cube_size))
    max_generation_depth = config.max_depth + config.lower_extra_depth
    return normalized_down >= config.ca_trigger_depth_ratio or room.depth >= max_generation_depth


def generate_ca_survivor_points(room: RoomBox, config: AbyssConfig) -> list[SurvivorPoint]:
    """为单个房间运行 3D CA，并返回所有存活体素的中心点。

    性能策略：
    - CA 用 set[(x, y, z)] 表示存活体素，适合稀疏腐蚀；
    - 不使用 bpy，也不创建对象；
    - 输出只包含点，避免 Python 循环生成大量 cube。
    """

    resolution = config.ca_grid_resolution
    rng = random.Random(_room_seed(room, config))
    initial_alive = _initial_alive_cells(room, config, resolution, rng)
    alive = set(initial_alive)
    for _ in range(config.ca_iterations):
        alive = _step_ca(alive, resolution)

    # 兜底：CA 是风化层，不应该把一个深层房间完全删除。
    # 如果规则在小房间里过度清空，回退到初始腐蚀结果；如果初始也为空，则生成边界残骸点。
    if not alive:
        alive = initial_alive or _fallback_boundary_cells(resolution)

    voxel_size = min(room.width, room.depth_y, room.height) / resolution
    points: list[SurvivorPoint] = []
    for cell in sorted(alive):
        points.append(SurvivorPoint(_cell_center(room, cell, resolution), voxel_size, room.id))
    return points


def _initial_alive_cells(
    room: RoomBox, config: AbyssConfig, resolution: int, rng: random.Random
) -> set[tuple[int, int, int]]:
    alive: set[tuple[int, int, int]] = set()
    max_radius = 3**0.5

    for ix in range(resolution):
        for iy in range(resolution):
            for iz in range(resolution):
                nx = ((ix + 0.5) / resolution) * 2.0 - 1.0
                ny = ((iy + 0.5) / resolution) * 2.0 - 1.0
                nz = ((iz + 0.5) / resolution) * 2.0 - 1.0

                # 越靠近房间中心，存活率越低：中心被“深渊空洞”掏空，边缘更像残存墙体。
                center_proximity = 1.0 - min(1.0, (nx * nx + ny * ny + nz * nz) ** 0.5 / max_radius)
                survival_rate = config.ca_base_survival_rate - config.ca_center_decay * center_proximity

                # 保留少量底部残渣，让 CA 输出更像坍塌废墟，而不是均匀噪声。
                if iz < resolution * 0.18:
                    survival_rate += 0.12

                if rng.random() < min(0.95, max(0.18, survival_rate)):
                    alive.add((ix, iy, iz))
    return alive


def _step_ca(alive: set[tuple[int, int, int]], resolution: int) -> set[tuple[int, int, int]]:
    next_alive: set[tuple[int, int, int]] = set()
    for ix in range(resolution):
        for iy in range(resolution):
            for iz in range(resolution):
                cell = (ix, iy, iz)
                neighbors = _count_alive_neighbors(alive, cell, resolution)
                if cell in alive:
                    # 腐蚀与风化：放宽生存窗口，避免深层房间被完全吃空。
                    if 3 <= neighbors <= 15:
                        next_alive.add(cell)
                elif 5 <= neighbors <= 12:
                    # 少量再沉积：让废墟形成桥接和颗粒团簇，而不是完全散掉。
                    next_alive.add(cell)
    return next_alive


def _fallback_boundary_cells(resolution: int) -> set[tuple[int, int, int]]:
    """生成最低限度的边界残骸，确保 CA 房间不会输出 0 点。"""

    cells: set[tuple[int, int, int]] = set()
    for ix in range(resolution):
        for iy in range(resolution):
            for iz in range(resolution):
                on_boundary = ix in (0, resolution - 1) or iy in (0, resolution - 1) or iz in (0, resolution - 1)
                checker = (ix + iy + iz) % 3 == 0
                if on_boundary and checker:
                    cells.add((ix, iy, iz))
    return cells


def _count_alive_neighbors(alive: set[tuple[int, int, int]], cell: tuple[int, int, int], resolution: int) -> int:
    count = 0
    ix, iy, iz = cell
    for dx, dy, dz in _NEIGHBOR_OFFSETS:
        neighbor = (ix + dx, iy + dy, iz + dz)
        if (
            0 <= neighbor[0] < resolution
            and 0 <= neighbor[1] < resolution
            and 0 <= neighbor[2] < resolution
            and neighbor in alive
        ):
            count += 1
    return count


def _cell_center(room: RoomBox, cell: tuple[int, int, int], resolution: int) -> tuple[float, float, float]:
    ix, iy, iz = cell
    return (
        room.min_x + (ix + 0.5) * room.width / resolution,
        room.min_y + (iy + 0.5) * room.depth_y / resolution,
        room.min_z + (iz + 0.5) * room.height / resolution,
    )


def _room_seed(room: RoomBox, config: AbyssConfig) -> int:
    room_number = int(room.id.rsplit("_", 1)[-1])
    return config.seed * 1009 + room_number * 9176 + room.depth * 37
