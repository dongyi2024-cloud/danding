"""递归空间生成：完整 3D BSP + 倒三角深渊约束。"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
from typing import Iterable


RECURSION_ORIGIN_TOP = "top"
RECURSION_ORIGIN_BOTTOM = "bottom"


@dataclass(frozen=True)
class RoomCharacter:
    """房间的建筑性格参数。

    这些值不直接改变房间拓扑，而是为后续语义分类、开口、楼梯、侵蚀和材质
    提供稳定的 0-1 驱动量。这样我们可以持续迭代空间表现，而不必重写递归主循环。
    """

    pressure: float
    light_scarcity: float
    ceiling_bias: float
    erosion_bias: float
    ritual_bias: float
    circulation_bias: float
    aperture_budget: float


def _neutral_room_character() -> RoomCharacter:
    return RoomCharacter(
        pressure=0.0,
        light_scarcity=0.0,
        ceiling_bias=0.0,
        erosion_bias=0.0,
        ritual_bias=0.0,
        circulation_bias=0.0,
        aperture_budget=0.0,
    )


@dataclass(frozen=True)
class RoomLineage:
    """记录房间来自哪些递归切分，以及四面墙继承到的暴露度。"""

    split_axes: tuple[str, ...] = ()
    split_biases: tuple[float, ...] = ()
    wall_exposure_x_min: float = 0.0
    wall_exposure_x_max: float = 0.0
    wall_exposure_y_min: float = 0.0
    wall_exposure_y_max: float = 0.0


def _neutral_room_lineage() -> RoomLineage:
    return RoomLineage()


@dataclass(frozen=True)
class RoomBox:
    """以米为单位的房间盒子，坐标默认位于外部立方体中心坐标系。"""

    id: str
    min_x: int
    min_y: int
    min_z: int
    max_x: int
    max_y: int
    max_z: int
    depth: int
    structure_id: str = "lower"
    structure_min_z: int = -36
    structure_max_z: int = 0
    recursion_origin: str = RECURSION_ORIGIN_TOP
    character: RoomCharacter = field(default_factory=_neutral_room_character)
    lineage: RoomLineage = field(default_factory=_neutral_room_lineage)

    @property
    def width(self) -> int:
        return self.max_x - self.min_x

    @property
    def depth_y(self) -> int:
        return self.max_y - self.min_y

    @property
    def height(self) -> int:
        return self.max_z - self.min_z

    @property
    def volume(self) -> int:
        return self.width * self.depth_y * self.height

    @property
    def center(self) -> tuple[float, float, float]:
        return (
            (self.min_x + self.max_x) / 2,
            (self.min_y + self.max_y) / 2,
            (self.min_z + self.max_z) / 2,
        )

    def bounds(self) -> tuple[int, int, int, int, int, int]:
        return (self.min_x, self.min_y, self.min_z, self.max_x, self.max_y, self.max_z)


@dataclass(frozen=True)
class AbyssConfig:
    """Dante Cube 生成参数。

    module_size 是建筑模数，默认 3m。cube_size 必须是 module_size 的整数倍。
    """

    cube_size: int = 36
    module_size: int = 3
    skin_thickness: float = 0.1
    exterior_skin_gap: float = 1.0
    wall_thickness: float = 0.2
    max_depth: int = 4
    lower_extra_depth: int = 2
    min_room_modules: int = 1
    abyss_taper: float = 0.72
    min_core_ratio: float = 0.22
    seed: int = 42
    ca_grid_resolution: int = 8
    ca_iterations: int = 7
    ca_trigger_depth_ratio: float = 0.62
    ca_base_survival_rate: float = 0.48
    ca_center_decay: float = 0.35
    path_downward_reward: float = 0.35
    path_upward_penalty: float = 2.4
    path_radial_pull: float = 1.8
    path_goal_pull: float = 0.8
    path_direct_drop_penalty: float = 0.65
    path_heuristic_distance_weight: float = 0.45
    path_heuristic_radial_weight: float = 0.25
    path_waypoint_goal_bias: float = 0.15
    stair_pitch_degrees: float = 32.0
    stair_wall_clearance: float = 0.42
    stair_landing_length: float = 1.2
    enable_opening_booleans: bool = False
    aperture_min_scale: float = 0.28
    aperture_max_scale: float = 0.72
    aperture_outer_bonus: float = 0.16
    aperture_axis_shape_strength: float = 0.24
    interior_aperture_boost: float = 1.35
    interior_aperture_min_half: float = 0.42
    opening_sill_offset: float = 0.18
    opening_vertical_jitter: float = 0.16
    upper_vertical_aperture_boost: float = 1.42
    upper_vertical_aperture_fade_down: float = 0.48
    upper_vertical_aperture_max_ratio: float = 0.74
    include_upper_cube: bool = True
    stacked_cube_offset: int = 6

    def __post_init__(self) -> None:
        if self.module_size <= 0:
            raise ValueError("module_size must be positive")
        if self.skin_thickness <= 0:
            raise ValueError("skin_thickness must be positive")
        if self.exterior_skin_gap < 0:
            raise ValueError("exterior_skin_gap must be non-negative")
        if self.wall_thickness <= 0:
            raise ValueError("wall_thickness must be positive")
        if self.cube_size <= 0 or self.cube_size % self.module_size != 0:
            raise ValueError("cube_size must be a positive multiple of module_size")
        if self.max_depth < 0 or self.lower_extra_depth < 0:
            raise ValueError("recursion depths must be non-negative")
        if self.min_room_modules < 1:
            raise ValueError("min_room_modules must be at least 1")
        if not 0 <= self.abyss_taper < 1:
            raise ValueError("abyss_taper must be in [0, 1)")
        if not 0 < self.min_core_ratio <= 1:
            raise ValueError("min_core_ratio must be in (0, 1]")
        if self.ca_grid_resolution < 2:
            raise ValueError("ca_grid_resolution must be at least 2")
        if self.ca_iterations < 0:
            raise ValueError("ca_iterations must be non-negative")
        if not 0 <= self.ca_trigger_depth_ratio <= 1:
            raise ValueError("ca_trigger_depth_ratio must be in [0, 1]")
        if not 0 <= self.ca_base_survival_rate <= 1:
            raise ValueError("ca_base_survival_rate must be in [0, 1]")
        if not 0 <= self.ca_center_decay <= 1:
            raise ValueError("ca_center_decay must be in [0, 1]")
        if self.path_downward_reward < 0:
            raise ValueError("path_downward_reward must be non-negative")
        if self.path_upward_penalty < 0:
            raise ValueError("path_upward_penalty must be non-negative")
        if self.path_radial_pull < 0:
            raise ValueError("path_radial_pull must be non-negative")
        if self.path_goal_pull < 0:
            raise ValueError("path_goal_pull must be non-negative")
        if self.path_direct_drop_penalty < 0:
            raise ValueError("path_direct_drop_penalty must be non-negative")
        if self.path_heuristic_distance_weight < 0:
            raise ValueError("path_heuristic_distance_weight must be non-negative")
        if self.path_heuristic_radial_weight < 0:
            raise ValueError("path_heuristic_radial_weight must be non-negative")
        if self.path_waypoint_goal_bias < 0:
            raise ValueError("path_waypoint_goal_bias must be non-negative")
        if not 15.0 <= self.stair_pitch_degrees <= 60.0:
            raise ValueError("stair_pitch_degrees must be in [15, 60]")
        if self.stair_wall_clearance <= 0:
            raise ValueError("stair_wall_clearance must be positive")
        if self.stair_landing_length < 0:
            raise ValueError("stair_landing_length must be non-negative")
        if not 0 < self.aperture_min_scale <= 1:
            raise ValueError("aperture_min_scale must be in (0, 1]")
        if not 0 < self.aperture_max_scale <= 1:
            raise ValueError("aperture_max_scale must be in (0, 1]")
        if self.aperture_min_scale > self.aperture_max_scale:
            raise ValueError("aperture_min_scale must be <= aperture_max_scale")
        if not 0 <= self.aperture_outer_bonus <= 1:
            raise ValueError("aperture_outer_bonus must be in [0, 1]")
        if not 0 <= self.aperture_axis_shape_strength <= 1:
            raise ValueError("aperture_axis_shape_strength must be in [0, 1]")
        if self.interior_aperture_boost < 1.0:
            raise ValueError("interior_aperture_boost must be at least 1.0")
        if self.interior_aperture_min_half <= 0:
            raise ValueError("interior_aperture_min_half must be positive")
        if self.opening_sill_offset < 0:
            raise ValueError("opening_sill_offset must be non-negative")
        if self.opening_vertical_jitter < 0:
            raise ValueError("opening_vertical_jitter must be non-negative")
        if self.upper_vertical_aperture_boost < 1.0:
            raise ValueError("upper_vertical_aperture_boost must be at least 1.0")
        if not 0 < self.upper_vertical_aperture_fade_down <= 1:
            raise ValueError("upper_vertical_aperture_fade_down must be in (0, 1]")
        if not 0 < self.upper_vertical_aperture_max_ratio < 1:
            raise ValueError("upper_vertical_aperture_max_ratio must be in (0, 1)")
        if self.stacked_cube_offset < 0:
            raise ValueError("stacked_cube_offset must be non-negative")
        if self.stacked_cube_offset % self.module_size != 0:
            raise ValueError("stacked_cube_offset must align to module_size")

    @property
    def min_room_size(self) -> int:
        return self.min_room_modules * self.module_size


@dataclass(frozen=True)
class _Node:
    min_x: int
    min_y: int
    min_z: int
    max_x: int
    max_y: int
    max_z: int
    depth: int
    structure_id: str = "lower"
    structure_min_z: int = -36
    structure_max_z: int = 0
    recursion_origin: str = RECURSION_ORIGIN_TOP
    split_axes: tuple[str, ...] = ()
    split_biases: tuple[float, ...] = ()
    wall_exposure_x_min: float = 1.0
    wall_exposure_x_max: float = 1.0
    wall_exposure_y_min: float = 1.0
    wall_exposure_y_max: float = 1.0

    def size(self, axis: str) -> int:
        if axis == "x":
            return self.max_x - self.min_x
        if axis == "y":
            return self.max_y - self.min_y
        return self.max_z - self.min_z

    def center_z(self) -> float:
        return (self.min_z + self.max_z) / 2


def generate_abyss_rooms(config: AbyssConfig | None = None) -> list[RoomBox]:
    """生成 Dante Cube 房间。

    每个外部立方体水平居中；默认下方立方体整体下移，默认上方镜像立方体整体上移，
    二者之间留出一层可读的空隙。
    """

    cfg = config or AbyssConfig()
    rooms: list[RoomBox] = []
    lower_min_z = -cfg.cube_size - cfg.stacked_cube_offset
    lower_max_z = -cfg.stacked_cube_offset
    upper_min_z = cfg.stacked_cube_offset
    upper_max_z = cfg.cube_size + cfg.stacked_cube_offset

    structure_specs = [
        ("lower", lower_min_z, lower_max_z, RECURSION_ORIGIN_TOP),
    ]
    if cfg.include_upper_cube:
        structure_specs.append(("upper", upper_min_z, upper_max_z, RECURSION_ORIGIN_BOTTOM))

    half = cfg.cube_size // 2
    for structure_id, structure_min_z, structure_max_z, recursion_origin in structure_specs:
        root = _Node(
            -half,
            -half,
            structure_min_z,
            half,
            half,
            structure_max_z,
            0,
            structure_id=structure_id,
            structure_min_z=structure_min_z,
            structure_max_z=structure_max_z,
            recursion_origin=recursion_origin,
        )
        rng = random.Random(cfg.seed)
        leaves: list[_Node] = []
        _split_node(root, cfg, rng, leaves)
        for index, leaf in enumerate(leaves):
            constrained = _apply_abyss_constraint(leaf, cfg)
            if constrained is None:
                continue
            room_id = f"room_{index:04d}" if structure_id == "lower" else f"{structure_id}_room_{index:04d}"
            rooms.append(
                RoomBox(
                    id=room_id,
                    min_x=constrained[0],
                    min_y=constrained[1],
                    min_z=constrained[2],
                    max_x=constrained[3],
                    max_y=constrained[4],
                    max_z=constrained[5],
                    depth=leaf.depth,
                    structure_id=structure_id,
                    structure_min_z=structure_min_z,
                    structure_max_z=structure_max_z,
                    recursion_origin=recursion_origin,
                    character=_derive_room_character(constrained, leaf.depth, leaf, cfg),
                    lineage=_node_lineage(leaf),
                )
            )
    return rooms


def cube_bounds(config: AbyssConfig) -> tuple[int, int, int, int, int, int]:
    half = config.cube_size // 2
    return (-half, -half, -config.cube_size, half, half, 0)


def structure_bounds_from_room(room: RoomBox) -> tuple[int, int, int, int, int, int]:
    """返回房间所属结构的固定外包立方体边界。

    这里不能从单个房间的平面尺寸反推外壳，否则会错误地得到一批
    “整高但不同平面尺度”的假立方体。结构外壳应只由结构总高决定，
    平面保持标准正方体尺度。
    """

    structure_height = room.structure_max_z - room.structure_min_z
    half_span = int(round(structure_height / 2))
    return (-half_span, -half_span, room.structure_min_z, half_span, half_span, room.structure_max_z)


def room_depth_progress(room: RoomBox) -> float:
    return _vertical_progress(
        (room.min_z + room.max_z) / 2,
        room.structure_min_z,
        room.structure_max_z,
        room.recursion_origin,
    )


def rooms_by_structure(rooms: Iterable[RoomBox]) -> dict[str, list[RoomBox]]:
    grouped: dict[str, list[RoomBox]] = {}
    for room in rooms:
        grouped.setdefault(room.structure_id, []).append(room)
    return grouped


def depth_band(room: RoomBox, config: AbyssConfig) -> int:
    """返回沿递归方向递增的深度带编号。"""

    normalized_down = room_depth_progress(room)
    band_count = max(1, config.max_depth + config.lower_extra_depth)
    return min(band_count - 1, int(normalized_down * band_count))


def rooms_by_depth(rooms: Iterable[RoomBox], config: AbyssConfig) -> dict[int, list[RoomBox]]:
    groups: dict[int, list[RoomBox]] = {}
    for room in rooms:
        groups.setdefault(depth_band(room, config), []).append(room)
    return groups


def _split_node(node: _Node, cfg: AbyssConfig, rng: random.Random, leaves: list[_Node]) -> None:
    normalized_down = _node_depth_progress(node)
    target_depth = cfg.max_depth + round(normalized_down * cfg.lower_extra_depth)
    axes = [axis for axis in ("x", "y", "z") if node.size(axis) >= cfg.min_room_size * 2]

    if node.depth >= target_depth or not axes:
        leaves.append(node)
        return

    # 优先沿长轴切分，保留少量随机性避免过度机械。
    axes.sort(key=node.size, reverse=True)
    axis = axes[0] if rng.random() < 0.72 else rng.choice(axes)
    split = _choose_split(node, axis, cfg, rng)
    if split is None:
        leaves.append(node)
        return

    first, second = _bisect(node, axis, split, cfg)
    _split_node(first, cfg, rng, leaves)
    _split_node(second, cfg, rng, leaves)


def _choose_split(node: _Node, axis: str, cfg: AbyssConfig, rng: random.Random) -> int | None:
    start = getattr(node, f"min_{axis}") + cfg.min_room_size
    end = getattr(node, f"max_{axis}") - cfg.min_room_size
    candidates = list(range(start, end + 1, cfg.module_size))
    if not candidates:
        return None

    midpoint = (getattr(node, f"min_{axis}") + getattr(node, f"max_{axis}")) / 2
    candidates.sort(key=lambda value: abs(value - midpoint))
    narrow = candidates[: max(1, min(3, len(candidates)))]
    return rng.choice(narrow)


def _bisect(node: _Node, axis: str, split: int, cfg: AbyssConfig) -> tuple[_Node, _Node]:
    values = node.__dict__.copy()
    first_values = values.copy()
    second_values = values.copy()
    first_values[f"max_{axis}"] = split
    second_values[f"min_{axis}"] = split
    first_values["depth"] = node.depth + 1
    second_values["depth"] = node.depth + 1
    bias = _normalized_split_bias(node, axis, split)
    split_axes = node.split_axes + (axis,)
    split_biases = node.split_biases + (bias,)
    first_values["split_axes"] = split_axes
    second_values["split_axes"] = split_axes
    first_values["split_biases"] = split_biases
    second_values["split_biases"] = split_biases
    if axis == "x":
        interior_exposure = _interior_face_exposure(node, axis, bias, cfg)
        first_values["wall_exposure_x_max"] = interior_exposure
        second_values["wall_exposure_x_min"] = interior_exposure
    elif axis == "y":
        interior_exposure = _interior_face_exposure(node, axis, bias, cfg)
        first_values["wall_exposure_y_max"] = interior_exposure
        second_values["wall_exposure_y_min"] = interior_exposure
    return _Node(**first_values), _Node(**second_values)


def _apply_abyss_constraint(node: _Node, cfg: AbyssConfig) -> tuple[int, int, int, int, int, int] | None:
    normalized_down = _node_depth_progress(node)
    half = cfg.cube_size / 2
    allowed_half = half * max(cfg.min_core_ratio, 1.0 - cfg.abyss_taper * normalized_down)

    min_x = max(node.min_x, _snap_down(-allowed_half, cfg.module_size))
    max_x = min(node.max_x, _snap_up(allowed_half, cfg.module_size))
    min_y = max(node.min_y, _snap_down(-allowed_half, cfg.module_size))
    max_y = min(node.max_y, _snap_up(allowed_half, cfg.module_size))

    if max_x - min_x < cfg.min_room_size or max_y - min_y < cfg.min_room_size:
        return None
    if node.max_z - node.min_z < cfg.min_room_size:
        return None
    return (min_x, min_y, node.min_z, max_x, max_y, node.max_z)


def _derive_room_character(
    bounds: tuple[int, int, int, int, int, int],
    depth: int,
    lineage: _Node,
    cfg: AbyssConfig,
) -> RoomCharacter:
    """从几何盒体中提取可复用的空间性格。

    建筑意义：
    - `pressure` 描述“被深渊挤压”的总体感受；
    - `light_scarcity` 和 `ceiling_bias` 对应黑暗与低矮感；
    - `erosion_bias` 给深层风化和未来 Geometry Nodes 侵蚀准备权重；
    - `ritual_bias` 对应纪念性/仪式性；
    - `circulation_bias` 对应这个房间是否适合作为通行节点，而不是死角。
    """

    min_x, min_y, min_z, max_x, max_y, max_z = bounds
    width = max_x - min_x
    depth_y = max_y - min_y
    height = max_z - min_z
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    center_z = (min_z + max_z) / 2

    normalized_down = _vertical_progress(center_z, lineage.structure_min_z, lineage.structure_max_z, lineage.recursion_origin)
    max_generation_depth = max(1, cfg.max_depth + cfg.lower_extra_depth)
    recursive_pressure = _clamp(depth / max_generation_depth, 0.0, 1.0)
    split_count = len(lineage.split_axes)
    axis_variety = len(set(lineage.split_axes)) / 3.0 if lineage.split_axes else 0.0
    mean_split_bias = sum(lineage.split_biases) / split_count if split_count else 0.0
    vertical_split_ratio = lineage.split_axes.count("z") / split_count if split_count else 0.0
    wall_exposures = (
        lineage.wall_exposure_x_min,
        lineage.wall_exposure_x_max,
        lineage.wall_exposure_y_min,
        lineage.wall_exposure_y_max,
    )
    mean_wall_exposure = sum(wall_exposures) / len(wall_exposures)
    max_radius = max(1.0, math.sqrt(2.0) * cfg.cube_size / 2)
    radial_ratio = _clamp(math.sqrt(center_x * center_x + center_y * center_y) / max_radius, 0.0, 1.0)

    volume_ratio = (width * depth_y * height) / max(1.0, cfg.cube_size**3)
    plan_ratio = max(width, depth_y) / max(float(cfg.module_size), min(width, depth_y))
    balanced_plan = 1.0 - _clamp((plan_ratio - 1.0) / 2.5, 0.0, 1.0)
    low_ceiling = 1.0 - _clamp(height / max(float(cfg.module_size * 4), 1.0), 0.0, 1.0)
    spatial_openness = _clamp(max(width, depth_y) / max(float(cfg.module_size * 6), 1.0), 0.0, 1.0)
    compactness = 1.0 - _clamp(volume_ratio * 20.0, 0.0, 1.0)

    pressure = _clamp(
        normalized_down * 0.46 + recursive_pressure * 0.22 + compactness * 0.18 + (1.0 - radial_ratio) * 0.14,
        0.0,
        1.0,
    )
    light_scarcity = _clamp(
        normalized_down * 0.54 + low_ceiling * 0.28 + (1.0 - radial_ratio) * 0.18,
        0.0,
        1.0,
    )
    ceiling_bias = _clamp(low_ceiling * 0.72 + normalized_down * 0.28, 0.0, 1.0)
    erosion_bias = _clamp(
        normalized_down * 0.50 + recursive_pressure * 0.22 + (1.0 - radial_ratio) * 0.20 + compactness * 0.08,
        0.0,
        1.0,
    )
    ritual_bias = _clamp(
        (1.0 - radial_ratio) * 0.46 + balanced_plan * 0.34 + (1.0 - normalized_down) * 0.20,
        0.0,
        1.0,
    )
    circulation_bias = _clamp(
        spatial_openness * 0.38 + balanced_plan * 0.24 + (1.0 - ceiling_bias) * 0.18 + (1.0 - radial_ratio) * 0.20,
        0.0,
        1.0,
    )
    aperture_budget = _clamp(
        mean_wall_exposure * 0.46
        + axis_variety * 0.16
        + (1.0 - mean_split_bias) * 0.10
        + vertical_split_ratio * 0.12
        + (1.0 - normalized_down) * 0.08
        + recursive_pressure * 0.08,
        0.0,
        1.0,
    )

    return RoomCharacter(
        pressure=pressure,
        light_scarcity=light_scarcity,
        ceiling_bias=ceiling_bias,
        erosion_bias=erosion_bias,
        ritual_bias=ritual_bias,
        circulation_bias=circulation_bias,
        aperture_budget=aperture_budget,
    )


def _node_lineage(node: _Node) -> RoomLineage:
    return RoomLineage(
        split_axes=node.split_axes,
        split_biases=node.split_biases,
        wall_exposure_x_min=node.wall_exposure_x_min,
        wall_exposure_x_max=node.wall_exposure_x_max,
        wall_exposure_y_min=node.wall_exposure_y_min,
        wall_exposure_y_max=node.wall_exposure_y_max,
    )


def _normalized_split_bias(node: _Node, axis: str, split: int) -> float:
    midpoint = (getattr(node, f"min_{axis}") + getattr(node, f"max_{axis}")) / 2
    half_span = max(1.0, node.size(axis) / 2)
    return _clamp(abs(split - midpoint) / half_span, 0.0, 1.0)


def _interior_face_exposure(node: _Node, axis: str, split_bias: float, cfg: AbyssConfig) -> float:
    normalized_down = _node_depth_progress(node)
    depth_ratio = _clamp(node.depth / max(1, cfg.max_depth + cfg.lower_extra_depth), 0.0, 1.0)
    axis_bonus = 0.08 if axis == "z" else 0.0
    return _clamp(0.28 + (1.0 - split_bias) * 0.22 + normalized_down * 0.12 + depth_ratio * 0.10 + axis_bonus, 0.0, 1.0)


def _snap_down(value: float, module: int) -> int:
    return int(value // module) * module


def _snap_up(value: float, module: int) -> int:
    return int(-(-value // module)) * module


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def _node_depth_progress(node: _Node) -> float:
    return _vertical_progress(node.center_z(), node.structure_min_z, node.structure_max_z, node.recursion_origin)


def _vertical_progress(center_z: float, structure_min_z: float, structure_max_z: float, recursion_origin: str) -> float:
    span = max(1.0, structure_max_z - structure_min_z)
    if recursion_origin == RECURSION_ORIGIN_BOTTOM:
        return _clamp((center_z - structure_min_z) / span, 0.0, 1.0)
    return _clamp((structure_max_z - center_z) / span, 0.0, 1.0)
