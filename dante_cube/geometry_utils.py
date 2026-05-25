"""Blender 构建工具：把数据层房间转换为可检查的 Dante Cube 场景。"""

from __future__ import annotations

import math

from .generators import AbyssConfig, RoomBox, rooms_by_structure, structure_bounds_from_room
from .openings import (
    OPENING_BLOCKED,
    OPENING_CRACK,
    OPENING_DOOR,
    OPENING_DROP_SHAFT,
    OPENING_LADDER,
    OPENING_RITUAL_GATE,
    OPENING_STAIR_HINT,
    Opening,
    generate_openings,
    opening_floor_aligned_bottom,
    opening_uses_floor_aligned_bottom,
)
from .pathfinding import AdjacencyGraph, find_dante_path
from .room_semantics import LEGAL_ROOM_TYPES, RoomSemantic, classify_rooms
from .stairs import STAIR_KIND_LADDER, StairFlight, generate_stairs


COLLECTION_ROOMS = "DanteCube_Rooms"
COLLECTION_ABYSS = "DanteCube_Abyss"
COLLECTION_PATH = "DanteCube_Path"
COLLECTION_LIGHTS = "DanteCube_Lights"
COLLECTION_OPENINGS = "DanteCube_Openings"
COLLECTION_STAIRS = "DanteCube_Stairs"
COLLECTION_CUTTERS = "DanteCube_Cutters"
COLLECTION_ROOM_CELLS = "DanteCube_RoomCells"
COLLECTION_CORRIDOR = "DanteCube_Corridor"
STRUCTURE_LOWER = "lower"
STRUCTURE_UPPER = "upper"
FACE_FLOOR = "floor"
FACE_CEILING = "ceiling"
FACE_Y_MIN = "y_min"
FACE_X_MAX = "x_max"
FACE_Y_MAX = "y_max"
FACE_X_MIN = "x_min"


def _structure_accent_color(structure_id: str) -> tuple[float, float, float, float]:
    """按上下结构返回重点色。下部保持红色，上部切成白色。"""

    if structure_id == STRUCTURE_UPPER:
        return (0.96, 0.96, 0.94, 1.0)
    return (0.95, 0.02, 0.01, 1.0)


def build_scene(rooms: list[RoomBox], graph: AdjacencyGraph, config: AbyssConfig) -> None:
    """在 Blender 中创建完整 v1 表现层。

    这个函数只在 Blender Python 环境中导入 bpy，避免污染标准 Python 验证。
    """

    import bpy

    _clear_scene(bpy)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0

    collections = {
        COLLECTION_ROOMS: _ensure_collection(bpy, COLLECTION_ROOMS),
        COLLECTION_ABYSS: _ensure_collection(bpy, COLLECTION_ABYSS),
        COLLECTION_PATH: _ensure_collection(bpy, COLLECTION_PATH),
        COLLECTION_LIGHTS: _ensure_collection(bpy, COLLECTION_LIGHTS),
        COLLECTION_OPENINGS: _ensure_collection(bpy, COLLECTION_OPENINGS),
        COLLECTION_STAIRS: _ensure_collection(bpy, COLLECTION_STAIRS),
        COLLECTION_CUTTERS: _ensure_collection(bpy, COLLECTION_CUTTERS),
        COLLECTION_ROOM_CELLS: _ensure_collection(bpy, COLLECTION_ROOM_CELLS),
    }

    materials = _create_depth_materials(bpy, config)
    structure_groups = rooms_by_structure(rooms)
    dante_path: list[str] = []
    semantics: dict[str, RoomSemantic] = {}
    openings: list[Opening] = []
    stairs: list[StairFlight] = []

    for structure_id, structure_rooms in sorted(structure_groups.items()):
        room_ids = {room.id for room in structure_rooms}
        structure_graph = _subgraph(graph, room_ids)
        structure_path = find_dante_path(structure_rooms, structure_graph, config)
        structure_semantics = classify_rooms(structure_rooms, structure_graph, structure_path, config)
        structure_openings = generate_openings(structure_rooms, structure_graph, structure_semantics, structure_path, config)
        structure_stairs = generate_stairs(structure_rooms, structure_openings, structure_semantics, structure_path, config)
        dante_path.extend(structure_path)
        semantics.update(structure_semantics)
        openings.extend(structure_openings)
        stairs.extend(structure_stairs)

    room_apertures = _collect_room_apertures(rooms, openings, semantics, config)
    _create_exterior_cubes(bpy, collections[COLLECTION_ABYSS], rooms, config)
    _create_transition_corner_columns(bpy, collections[COLLECTION_ABYSS], structure_groups, config)
    rooms_obj = _create_rooms(bpy, collections[COLLECTION_ROOMS], rooms, config, materials, dante_path, semantics, room_apertures)
    _create_room_cells(bpy, collections[COLLECTION_ROOM_CELLS], rooms, config, semantics, room_apertures)
    if config.enable_opening_booleans:
        _apply_opening_booleans(bpy, collections[COLLECTION_CUTTERS], rooms_obj, openings, config)
    collections[COLLECTION_ROOMS].hide_viewport = True
    _create_dante_path_curve(bpy, collections[COLLECTION_PATH], rooms, dante_path)
    _create_opening_markers(bpy, collections[COLLECTION_OPENINGS], openings, rooms)
    _create_stair_markers(bpy, collections[COLLECTION_STAIRS], stairs)
    _create_lights(bpy, collections[COLLECTION_LIGHTS], rooms, config)


def _clear_scene(bpy) -> None:
    # 直接移除 bpy.data.objects，避免未链接到 Collection 的旧对象残留。
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def _ensure_collection(bpy, name: str):
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
    return collection


def _link_to_collection(bpy, obj, collection) -> None:
    collection.objects.link(obj)
    for existing in list(obj.users_collection):
        if existing != collection:
            existing.objects.unlink(obj)


def _subgraph(graph: AdjacencyGraph, room_ids: set[str]) -> AdjacencyGraph:
    return {room_id: graph.get(room_id, set()) & room_ids for room_id in room_ids}


def _create_depth_materials(bpy, config: AbyssConfig):
    materials = []
    count = max(2, config.max_depth + config.lower_extra_depth + 1)
    for index in range(count):
        t = index / (count - 1)
        mat = bpy.data.materials.new(f"Dante_Depth_{index:02d}")
        mat.diffuse_color = (0.42 - 0.26 * t, 0.36 - 0.24 * t, 0.31 - 0.22 * t, 0.5)
        mat.blend_method = "BLEND"
        mat.show_transparent_back = True
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            color = (0.42 - 0.26 * t, 0.36 - 0.24 * t, 0.31 - 0.22 * t, 0.5)
            bsdf.inputs["Base Color"].default_value = color
            bsdf.inputs["Alpha"].default_value = 0.5
            bsdf.inputs["Roughness"].default_value = 0.78
        materials.append(mat)
    return materials


def _create_dante_path_material(bpy, structure_id: str):
    color = _structure_accent_color(structure_id)
    material = bpy.data.materials.new(f"Dante_Agent_{structure_id}")
    material.diffuse_color = color
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Alpha"].default_value = color[3]
        bsdf.inputs["Roughness"].default_value = 0.55
        if structure_id == STRUCTURE_UPPER:
            bsdf.inputs["Emission Color"].default_value = (0.96, 0.96, 0.94, 1.0)
            bsdf.inputs["Emission Strength"].default_value = 0.06
    return material


def _create_transition_column_material(bpy):
    material = bpy.data.materials.new("Dante_Transition_Column")
    color = (0.075, 0.068, 0.058, 0.9)
    material.diffuse_color = color
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Alpha"].default_value = color[3]
        bsdf.inputs["Roughness"].default_value = 0.86
    material.blend_method = "BLEND"
    material.show_transparent_back = True
    return material


def _create_exterior_cubes(bpy, collection, rooms: list[RoomBox], config: AbyssConfig) -> None:
    material = bpy.data.materials.new("Dante_Exterior_Skin")
    material.diffuse_color = (0.075, 0.068, 0.058, 0.1)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (0.075, 0.068, 0.058, 0.1)
        bsdf.inputs["Alpha"].default_value = 0.1
        bsdf.inputs["Roughness"].default_value = 0.9
    material.blend_method = "BLEND"
    material.use_screen_refraction = True
    material.show_transparent_back = False

    t = config.skin_thickness
    seen_bounds: set[tuple[int, int, int, int, int, int]] = set()
    for room in rooms:
        bounds = structure_bounds_from_room(room)
        if bounds in seen_bounds:
            continue
        seen_bounds.add(bounds)
        min_x, min_y, min_z, max_x, max_y, max_z = bounds
        gap = config.exterior_skin_gap
        min_x -= gap
        min_y -= gap
        min_z -= gap
        max_x += gap
        max_y += gap
        max_z += gap

        mesh = bpy.data.meshes.new(f"DanteCube_Exterior_Skin_Mesh_{room.structure_id}")
        vertices, faces = _create_closed_cube_shell_geometry(min_x, min_y, min_z, max_x, max_y, max_z, t)
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        mesh.materials.append(material)

        obj = bpy.data.objects.new(f"DanteCube_Exterior_Skin_{room.structure_id}", mesh)
        collection.objects.link(obj)
        bevel = obj.modifiers.new("Exterior arris", "BEVEL")
        bevel.width = min(0.12, t * 0.12)
        bevel.segments = 1


def _create_transition_corner_columns(bpy, collection, structure_groups: dict[str, list[RoomBox]], config: AbyssConfig) -> None:
    """在上下立方体之间的转换层四角插入纤细柱子。"""

    lower_rooms = structure_groups.get(STRUCTURE_LOWER, [])
    upper_rooms = structure_groups.get(STRUCTURE_UPPER, [])
    if not lower_rooms or not upper_rooms:
        return

    lower_min_x, lower_min_y, _, lower_max_x, lower_max_y, lower_max_z = structure_bounds_from_room(lower_rooms[0])
    upper_min_x, upper_min_y, upper_min_z, upper_max_x, upper_max_y, _ = structure_bounds_from_room(upper_rooms[0])
    shell_min_x = min(lower_min_x, upper_min_x) - config.exterior_skin_gap
    shell_min_y = min(lower_min_y, upper_min_y) - config.exterior_skin_gap
    shell_max_x = max(lower_max_x, upper_max_x) + config.exterior_skin_gap
    shell_max_y = max(lower_max_y, upper_max_y) + config.exterior_skin_gap

    z_min = lower_max_z + config.exterior_skin_gap
    z_max = upper_min_z - config.exterior_skin_gap
    if z_max - z_min <= 0.24:
        return

    width = max(0.24, config.module_size * 0.12)
    corner_offset = max(width * 1.5, config.module_size * 0.22)
    xs = (shell_min_x + corner_offset, shell_max_x - corner_offset)
    ys = (shell_min_y + corner_offset, shell_max_y - corner_offset)
    material = _create_transition_column_material(bpy)

    for ix, x in enumerate(xs):
        for iy, y in enumerate(ys):
            bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, (z_min + z_max) * 0.5))
            obj = bpy.context.object
            obj.name = f"DanteTransitionColumn_{ix}_{iy}"
            obj.dimensions = (width, width, z_max - z_min)
            obj.data.materials.append(material)
            _link_to_collection(bpy, obj, collection)


def _create_exterior_corridor(
    bpy,
    collection,
    rooms: list[RoomBox],
    room_apertures: dict[str, dict[str, list[dict[str, object]]]],
    config: AbyssConfig,
) -> None:
    target = _select_exterior_corridor_target(rooms, room_apertures, config)
    if target is None:
        return

    room, face_name, aperture = target
    reference_aperture = _corridor_reference_aperture(room_apertures.get(room.id, {}), aperture)
    bounds = _exterior_corridor_inner_bounds(room, face_name, reference_aperture, config)
    if bounds is None:
        return

    material = _create_corridor_material(bpy)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    for segment in _corridor_wall_segments(bounds, config.wall_thickness):
        _append_box_bounds_geometry(vertices, faces, segment)
    _append_corridor_barrel_vault(vertices, faces, bounds, config.wall_thickness)

    mesh = bpy.data.meshes.new("DanteCube_Exterior_Corridor_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    mesh.materials.append(material)

    obj = bpy.data.objects.new("DanteCube_Exterior_Corridor", mesh)
    obj["room_id"] = room.id
    obj["face_name"] = face_name
    collection.objects.link(obj)


def _select_exterior_corridor_target(
    rooms: list[RoomBox],
    room_apertures: dict[str, dict[str, list[dict[str, object]]]],
    config: AbyssConfig,
) -> tuple[RoomBox, str, dict[str, object]] | None:
    candidates: list[tuple[float, float, str, str, RoomBox, dict[str, object]]] = []
    for room in rooms:
        shell_min_x, shell_min_y, _, shell_max_x, shell_max_y, _ = structure_bounds_from_room(room)
        shell_min_x -= config.exterior_skin_gap
        shell_min_y -= config.exterior_skin_gap
        shell_max_x += config.exterior_skin_gap
        shell_max_y += config.exterior_skin_gap
        apertures = room_apertures.get(room.id, {})
        for face_name in (FACE_X_MIN, FACE_X_MAX, FACE_Y_MIN, FACE_Y_MAX):
            specs = apertures.get(face_name, [])
            if not specs:
                continue
            spec = specs[0]
            if not str(spec.get("id", "")).startswith("default_wall_"):
                continue
            if face_name == FACE_X_MIN:
                distance = room.min_x - shell_min_x
            elif face_name == FACE_X_MAX:
                distance = shell_max_x - room.max_x
            elif face_name == FACE_Y_MIN:
                distance = room.min_y - shell_min_y
            else:
                distance = shell_max_y - room.max_y
            if distance <= 0.18:
                continue
            candidates.append((room.center[2], distance, room.id, face_name, room, spec))

    if not candidates:
        return None

    _, _, _, face_name, room, spec = min(candidates, key=lambda item: (item[0], item[1], item[2], item[3]))
    return (room, face_name, spec)


def _exterior_corridor_inner_bounds(
    room: RoomBox,
    face_name: str,
    aperture: dict[str, object],
    config: AbyssConfig,
) -> tuple[float, float, float, float, float, float] | None:
    shell_min_x, shell_min_y, _, shell_max_x, shell_max_y, _ = structure_bounds_from_room(room)
    shell_min_x -= config.exterior_skin_gap
    shell_min_y -= config.exterior_skin_gap
    shell_max_x += config.exterior_skin_gap
    shell_max_y += config.exterior_skin_gap

    u_center = float(aperture["u_center"])
    v_center = float(aperture["v_center"])
    half_u = float(aperture["half_u"])
    half_v = float(aperture["half_v"])

    z_min = room.min_z + u_center - half_u
    z_max = room.min_z + u_center + half_u

    if face_name == FACE_X_MIN:
        y_center = room.max_y - v_center
        return (shell_min_x, y_center - half_v, z_min, room.min_x, y_center + half_v, z_max)
    if face_name == FACE_X_MAX:
        y_center = room.min_y + v_center
        return (room.max_x, y_center - half_v, z_min, shell_max_x, y_center + half_v, z_max)
    if face_name == FACE_Y_MIN:
        x_center = room.min_x + v_center
        return (x_center - half_v, shell_min_y, z_min, x_center + half_v, room.min_y, z_max)
    x_center = room.max_x - v_center
    return (x_center - half_v, room.max_y, z_min, x_center + half_v, shell_max_y, z_max)


def _corridor_reference_aperture(
    room_apertures: dict[str, list[dict[str, object]]],
    default_aperture: dict[str, object],
) -> dict[str, object]:
    """让外部走廊净空继承该房间内侧最小侧墙门洞，而不是外墙默认大洞。"""

    candidates: list[dict[str, object]] = []
    for face_name in (FACE_X_MIN, FACE_X_MAX, FACE_Y_MIN, FACE_Y_MAX):
        for spec in room_apertures.get(face_name, []):
            spec_id = str(spec.get("id", ""))
            if spec_id.startswith("default_wall_"):
                continue
            candidates.append(spec)

    if not candidates:
        return default_aperture

    reference = min(candidates, key=lambda spec: (float(spec["half_u"]) * float(spec["half_v"]), str(spec.get("id", ""))))
    return {
        "id": f"corridor_ref_{reference.get('id', 'aperture')}",
        "u_center": default_aperture["u_center"],
        "v_center": default_aperture["v_center"],
        "half_u": reference["half_u"],
        "half_v": reference["half_v"],
    }


def _corridor_wall_segments(
    inner_bounds: tuple[float, float, float, float, float, float],
    thickness: float,
) -> list[tuple[float, float, float, float, float, float]]:
    min_x, min_y, min_z, max_x, max_y, max_z = inner_bounds
    t = thickness
    span_x = max_x - min_x
    span_y = max_y - min_y
    half_width = min(span_x, span_y) * 0.5
    spring_z = max(min_z, max_z - half_width)
    if span_x >= span_y:
        return [
            (min_x, min_y - t, min_z - t, max_x, max_y + t, min_z),
            (min_x, min_y - t, min_z, max_x, min_y, spring_z),
            (min_x, max_y, min_z, max_x, max_y + t, spring_z),
        ]
    return [
        (min_x - t, min_y, min_z - t, max_x + t, max_y, min_z),
        (min_x - t, min_y, min_z, min_x, max_y, spring_z),
        (max_x, min_y, min_z, max_x + t, max_y, spring_z),
    ]


def _create_corridor_material(bpy):
    material = bpy.data.materials.new("Dante_Corridor")
    material.diffuse_color = (0.95, 0.02, 0.01, 0.8)
    material.blend_method = "BLEND"
    material.show_transparent_back = True
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (0.95, 0.02, 0.01, 0.8)
        bsdf.inputs["Alpha"].default_value = 0.8
        bsdf.inputs["Roughness"].default_value = 0.62
        bsdf.inputs["Emission Color"].default_value = (0.95, 0.02, 0.01, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 0.18
    return material


def _append_corridor_barrel_vault(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int, int]],
    inner_bounds: tuple[float, float, float, float, float, float],
    thickness: float,
    arch_segments: int = 16,
) -> None:
    """在走廊顶部生成沿通道方向挤出的半圆筒拱壳。"""

    min_x, min_y, min_z, max_x, max_y, max_z = inner_bounds
    span_x = max_x - min_x
    span_y = max_y - min_y

    if span_x >= span_y:
        axis_values = (min_x, max_x)
        lateral_center = (min_y + max_y) * 0.5
        half_width = span_y * 0.5
        place_vertex = lambda axis, lateral, z: (axis, lateral, z)
    else:
        axis_values = (min_y, max_y)
        lateral_center = (min_x + max_x) * 0.5
        half_width = span_x * 0.5
        place_vertex = lambda axis, lateral, z: (lateral, axis, z)

    if half_width <= 0.0:
        return

    radius_inner = half_width
    radius_outer = radius_inner + thickness
    spring_z = max(min_z, max_z - radius_inner)
    center_z = spring_z

    inner_start: list[int] = []
    inner_end: list[int] = []
    outer_start: list[int] = []
    outer_end: list[int] = []

    for step in range(arch_segments + 1):
        theta = math.pi * (step / arch_segments)
        cos_theta = math.cos(theta)
        sin_theta = math.sin(theta)
        inner_lateral = lateral_center + radius_inner * cos_theta
        inner_z = center_z + radius_inner * sin_theta
        outer_lateral = lateral_center + radius_outer * cos_theta
        outer_z = center_z + radius_outer * sin_theta

        inner_start.append(len(vertices))
        vertices.append(place_vertex(axis_values[0], inner_lateral, inner_z))
        inner_end.append(len(vertices))
        vertices.append(place_vertex(axis_values[1], inner_lateral, inner_z))
        outer_start.append(len(vertices))
        vertices.append(place_vertex(axis_values[0], outer_lateral, outer_z))
        outer_end.append(len(vertices))
        vertices.append(place_vertex(axis_values[1], outer_lateral, outer_z))

    for step in range(arch_segments):
        i0 = inner_start[step]
        i1 = inner_start[step + 1]
        j0 = inner_end[step]
        j1 = inner_end[step + 1]
        o0 = outer_start[step]
        o1 = outer_start[step + 1]
        p0 = outer_end[step]
        p1 = outer_end[step + 1]

        faces.append((i0, j0, j1, i1))
        faces.append((o0, o1, p1, p0))
        faces.append((i1, j1, p1, o1))
        faces.append((o0, p0, j0, i0))


def _create_closed_cube_shell_geometry(
    min_x: float,
    min_y: float,
    min_z: float,
    max_x: float,
    max_y: float,
    max_z: float,
    thickness: float,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int, int]]]:
    """创建闭合立方体表皮。

    建筑意义：它不是四块墙板拼接，而是一个外部正方体从顶部向下掏出深渊空腔。
    拓扑上包含外表面、内壁、底面和顶部洞口翻边，是一个连续的薄壳 Mesh。
    """

    outer = (min_x - thickness, min_y - thickness, min_z - thickness, max_x + thickness, max_y + thickness, max_z + thickness)
    inner = (min_x, min_y, min_z, max_x, max_y, max_z)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []

    outer_indices = _append_box_vertices(vertices, outer)
    inner_indices = _append_box_vertices(vertices, inner)

    # 外表面：保留四个立面和底面；顶部由洞口翻边环面表达。
    faces.extend(
        [
            (outer_indices[0], outer_indices[1], outer_indices[2], outer_indices[3]),
            (outer_indices[0], outer_indices[4], outer_indices[5], outer_indices[1]),
            (outer_indices[1], outer_indices[5], outer_indices[6], outer_indices[2]),
            (outer_indices[2], outer_indices[6], outer_indices[7], outer_indices[3]),
            (outer_indices[3], outer_indices[7], outer_indices[4], outer_indices[0]),
        ]
    )

    # 内表面：反向法线面向深渊净空间，形成被掏空的腔体；底面封闭，像一个向上开口的深井。
    faces.extend(
        [
            (inner_indices[3], inner_indices[2], inner_indices[1], inner_indices[0]),
            (inner_indices[1], inner_indices[5], inner_indices[4], inner_indices[0]),
            (inner_indices[2], inner_indices[6], inner_indices[5], inner_indices[1]),
            (inner_indices[3], inner_indices[7], inner_indices[6], inner_indices[2]),
            (inner_indices[0], inner_indices[4], inner_indices[7], inner_indices[3]),
        ]
    )

    # 顶部洞口翻边：把外顶边和内顶边连接起来，避免视觉上像四块独立矩形墙。
    faces.extend(
        [
            (outer_indices[4], inner_indices[4], inner_indices[5], outer_indices[5]),
            (outer_indices[5], inner_indices[5], inner_indices[6], outer_indices[6]),
            (outer_indices[6], inner_indices[6], inner_indices[7], outer_indices[7]),
            (outer_indices[7], inner_indices[7], inner_indices[4], outer_indices[4]),
        ]
    )
    return vertices, faces


def _append_box_vertices(
    vertices: list[tuple[float, float, float]], bounds: tuple[float, float, float, float, float, float]
) -> tuple[int, int, int, int, int, int, int, int]:
    min_x, min_y, min_z, max_x, max_y, max_z = bounds
    start = len(vertices)
    vertices.extend(
        [
            (min_x, min_y, min_z),
            (max_x, min_y, min_z),
            (max_x, max_y, min_z),
            (min_x, max_y, min_z),
            (min_x, min_y, max_z),
            (max_x, min_y, max_z),
            (max_x, max_y, max_z),
            (min_x, max_y, max_z),
        ]
    )
    return tuple(range(start, start + 8))


def _append_box_bounds_geometry(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int, int]],
    bounds: tuple[float, float, float, float, float, float],
) -> int:
    min_x, min_y, min_z, max_x, max_y, max_z = bounds
    start = len(vertices)
    vertices.extend(
        [
            (min_x, min_y, min_z),
            (max_x, min_y, min_z),
            (max_x, max_y, min_z),
            (min_x, max_y, min_z),
            (min_x, min_y, max_z),
            (max_x, min_y, max_z),
            (max_x, max_y, max_z),
            (min_x, max_y, max_z),
        ]
    )
    faces.extend(
        [
            (start + 0, start + 1, start + 2, start + 3),
            (start + 4, start + 7, start + 6, start + 5),
            (start + 0, start + 4, start + 5, start + 1),
            (start + 1, start + 5, start + 6, start + 2),
            (start + 2, start + 6, start + 7, start + 3),
            (start + 3, start + 7, start + 4, start + 0),
        ]
    )
    return 6


def _create_rooms(
    bpy,
    collection,
    rooms: list[RoomBox],
    config: AbyssConfig,
    materials,
    dante_path: list[str],
    semantics: dict[str, RoomSemantic],
    room_apertures: dict[str, dict[str, list[dict[str, object]]]],
):
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    face_room_type_values: list[int] = []
    face_compression_values: list[float] = []
    face_darkness_values: list[float] = []
    face_rituality_values: list[float] = []
    face_pressure_values: list[float] = []
    face_light_scarcity_values: list[float] = []
    face_ceiling_bias_values: list[float] = []
    face_ritual_bias_values: list[float] = []
    face_circulation_bias_values: list[float] = []
    room_face_maps: dict[str, dict[str, list[int]]] = {}
    room_type_indices = {room_type: index for index, room_type in enumerate(sorted(LEGAL_ROOM_TYPES))}

    for room in rooms:
        face_map = _append_room_box_geometry(vertices, faces, room, room_apertures.get(room.id, {}))
        room_face_maps[room.id] = face_map
        room_faces = sum(len(indices) for indices in face_map.values())
        semantic = semantics.get(room.id)
        room_type_index = room_type_indices.get(semantic.room_type if semantic is not None else "", -1)
        face_room_type_values.extend([room_type_index] * room_faces)
        face_compression_values.extend([semantic.compression if semantic is not None else 0.0] * room_faces)
        face_darkness_values.extend([semantic.darkness if semantic is not None else 0.0] * room_faces)
        face_rituality_values.extend([semantic.rituality if semantic is not None else 0.0] * room_faces)
        face_pressure_values.extend([semantic.pressure if semantic is not None else 0.0] * room_faces)
        face_light_scarcity_values.extend([semantic.light_scarcity if semantic is not None else 0.0] * room_faces)
        face_ceiling_bias_values.extend([semantic.ceiling_bias if semantic is not None else 0.0] * room_faces)
        face_ritual_bias_values.extend([semantic.ritual_bias if semantic is not None else 0.0] * room_faces)
        face_circulation_bias_values.extend([semantic.circulation_bias if semantic is not None else 0.0] * room_faces)

    mesh = bpy.data.meshes.new("DanteCube_Rooms_Chaos_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    # Blender 4.x 中面属性在 mesh 刚更新后写入最稳定。
    # 当前只保留与空间阅读直接相关的语义，不再把腐蚀/混沌权重接到可视化链上。
    room_type_attribute = mesh.attributes.new("room_type_index", "INT", "FACE")
    compression_attribute = mesh.attributes.new("compression", "FLOAT", "FACE")
    darkness_attribute = mesh.attributes.new("darkness", "FLOAT", "FACE")
    rituality_attribute = mesh.attributes.new("rituality", "FLOAT", "FACE")
    pressure_attribute = mesh.attributes.new("pressure", "FLOAT", "FACE")
    light_scarcity_attribute = mesh.attributes.new("light_scarcity", "FLOAT", "FACE")
    ceiling_bias_attribute = mesh.attributes.new("ceiling_bias", "FLOAT", "FACE")
    ritual_bias_attribute = mesh.attributes.new("ritual_bias", "FLOAT", "FACE")
    circulation_bias_attribute = mesh.attributes.new("circulation_bias", "FLOAT", "FACE")

    obj = bpy.data.objects.new("DanteCube_Rooms_Chaos_Mesh", mesh)
    obj["room_type_index_legend"] = ";".join(f"{index}:{room_type}" for room_type, index in sorted(room_type_indices.items()))
    obj["room_semantics"] = ";".join(
        f"{room_id}:{semantic.room_type}:{semantic.compression:.3f}:{semantic.darkness:.3f}:{semantic.rituality:.3f}:"
        f"{semantic.pressure:.3f}:{semantic.light_scarcity:.3f}:{semantic.circulation_bias:.3f}"
        for room_id, semantic in sorted(semantics.items())
    )
    mesh.materials.append(_create_room_mass_material(bpy))
    lower_path_material_index = len(mesh.materials)
    mesh.materials.append(_create_dante_path_material(bpy, STRUCTURE_LOWER))
    upper_path_material_index = len(mesh.materials)
    mesh.materials.append(_create_dante_path_material(bpy, STRUCTURE_UPPER))
    for material in materials:
        mesh.materials.append(material)

    route_faces = _dante_route_face_material_indices(
        rooms,
        dante_path,
        room_face_maps,
        {
            STRUCTURE_LOWER: lower_path_material_index,
            STRUCTURE_UPPER: upper_path_material_index,
        },
    )

    for polygon in mesh.polygons:
        polygon.material_index = route_faces.get(polygon.index, 0)
        _set_attribute_value(room_type_attribute, polygon.index, face_room_type_values[polygon.index])
        _set_attribute_value(compression_attribute, polygon.index, face_compression_values[polygon.index])
        _set_attribute_value(darkness_attribute, polygon.index, face_darkness_values[polygon.index])
        _set_attribute_value(rituality_attribute, polygon.index, face_rituality_values[polygon.index])
        _set_attribute_value(pressure_attribute, polygon.index, face_pressure_values[polygon.index])
        _set_attribute_value(light_scarcity_attribute, polygon.index, face_light_scarcity_values[polygon.index])
        _set_attribute_value(ceiling_bias_attribute, polygon.index, face_ceiling_bias_values[polygon.index])
        _set_attribute_value(ritual_bias_attribute, polygon.index, face_ritual_bias_values[polygon.index])
        _set_attribute_value(circulation_bias_attribute, polygon.index, face_circulation_bias_values[polygon.index])

    collection.objects.link(obj)

    solidify = obj.modifiers.new("Room wall thickness", "SOLIDIFY")
    solidify.thickness = config.wall_thickness
    solidify.offset = 0.0
    if hasattr(solidify, "use_quality_normals"):
        solidify.use_quality_normals = True
    return obj


def _create_room_cells(
    bpy,
    collection,
    rooms: list[RoomBox],
    config: AbyssConfig,
    semantics: dict[str, RoomSemantic],
    room_apertures: dict[str, dict[str, list[dict[str, object]]]],
) -> None:
    default_material, path_materials = _create_room_cell_materials(bpy)
    for room in rooms:
        semantic = semantics.get(room.id)
        vertices: list[tuple[float, float, float]] = []
        faces: list[tuple[int, int, int, int]] = []
        _append_room_box_geometry(vertices, faces, room, room_apertures.get(room.id, {}))

        mesh = bpy.data.meshes.new(f"DanteRoom_{room.id}_Mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        if semantic and semantic.is_on_dante_path:
            mesh.materials.append(path_materials.get(room.structure_id, path_materials[STRUCTURE_LOWER]))
        else:
            mesh.materials.append(default_material)

        obj = bpy.data.objects.new(f"DanteRoom_{room.id}", mesh)
        obj["room_id"] = room.id
        axis_weights = _lineage_axis_weights(room)
        obj["dominant_split_axis"] = _dominant_lineage_axis(room)
        obj["split_axis_signature"] = ",".join(
            f"{axis}:{axis_weights[axis]:.3f}" for axis in ("x", "y", "z")
        )
        if semantic is not None:
            obj["room_type"] = semantic.room_type
            obj["pressure"] = semantic.pressure
            obj["aperture_budget"] = room.character.aperture_budget
            obj["compression"] = semantic.compression
            obj["is_on_dante_path"] = semantic.is_on_dante_path
        collection.objects.link(obj)

        solidify = obj.modifiers.new("Room wall thickness", "SOLIDIFY")
        solidify.thickness = config.wall_thickness
        solidify.offset = 0.0
        if hasattr(solidify, "use_quality_normals"):
            solidify.use_quality_normals = True


def _create_room_cell_materials(bpy):
    default_material = bpy.data.materials.new("Dante_Room_Cell")
    default_material.diffuse_color = (0.15, 0.15, 0.16, 0.8)
    default_material.blend_method = "BLEND"
    default_material.use_nodes = True
    default_bsdf = default_material.node_tree.nodes.get("Principled BSDF")
    if default_bsdf is not None:
        default_bsdf.inputs["Base Color"].default_value = (0.15, 0.15, 0.16, 0.8)
        default_bsdf.inputs["Alpha"].default_value = 0.8
        default_bsdf.inputs["Roughness"].default_value = 0.78

    path_materials: dict[str, object] = {}
    for structure_id in (STRUCTURE_LOWER, STRUCTURE_UPPER):
        color = _structure_accent_color(structure_id)
        path_material = bpy.data.materials.new(f"Dante_Room_Cell_Path_{structure_id}")
        path_material.diffuse_color = (color[0], color[1], color[2], 0.8)
        path_material.blend_method = "BLEND"
        path_material.use_nodes = True
        path_bsdf = path_material.node_tree.nodes.get("Principled BSDF")
        if path_bsdf is not None:
            path_bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 0.8)
            path_bsdf.inputs["Alpha"].default_value = 0.8
            path_bsdf.inputs["Roughness"].default_value = 0.62
            path_bsdf.inputs["Emission Color"].default_value = (color[0], color[1], color[2], 1.0)
            path_bsdf.inputs["Emission Strength"].default_value = 0.18 if structure_id == STRUCTURE_LOWER else 0.08
        path_materials[structure_id] = path_material
    return default_material, path_materials


def _set_attribute_value(attribute, index: int, value: float | int) -> None:
    if index < len(attribute.data):
        attribute.data[index].value = value


def _collect_room_apertures(
    rooms: list[RoomBox],
    openings: list[Opening],
    semantics: dict[str, RoomSemantic],
    config: AbyssConfig,
) -> dict[str, dict[str, list[dict[str, object]]]]:
    rooms_by_id = {room.id: room for room in rooms}
    room_ids = {room.id for room in rooms}
    selected: dict[str, dict[str, list[dict[str, object]]]] = {}

    for opening in openings:
        if not _opening_creates_local_aperture(opening):
            continue

        left_room = rooms_by_id.get(opening.from_room_id)
        right_room = rooms_by_id.get(opening.to_room_id)
        left_semantic = semantics.get(opening.from_room_id)
        right_semantic = semantics.get(opening.to_room_id)
        left_face_name = _room_face_name_for_opening(opening.from_room_id, opening)
        right_face_name = _room_face_name_for_opening(opening.to_room_id, opening)

        if (
            left_room is not None
            and right_room is not None
            and left_semantic is not None
            and right_semantic is not None
            and left_face_name is not None
            and right_face_name is not None
        ):
            left_spec, right_spec = _shared_opening_aperture_specs(
                left_room,
                right_room,
                opening,
                left_semantic,
                right_semantic,
                left_face_name,
                right_face_name,
                config,
            )
            selected.setdefault(left_room.id, {}).setdefault(left_face_name, []).append(left_spec)
            selected.setdefault(right_room.id, {}).setdefault(right_face_name, []).append(right_spec)
            continue

        for room_id, room, semantic, face_name, counterpart_semantic in (
            (opening.from_room_id, left_room, left_semantic, left_face_name, right_semantic),
            (opening.to_room_id, right_room, right_semantic, right_face_name, left_semantic),
        ):
            if room_id not in room_ids or room is None or semantic is None or face_name is None:
                continue
            spec = _room_aperture_spec(room, opening, semantic, counterpart_semantic, face_name, config)
            selected.setdefault(room_id, {}).setdefault(face_name, []).append(spec)

    _append_uniform_wall_apertures(rooms, semantics, selected, config)
    return selected


def _opening_creates_local_aperture(opening: Opening) -> bool:
    return opening.opening_type in {
        OPENING_DOOR,
        OPENING_RITUAL_GATE,
        OPENING_STAIR_HINT,
        OPENING_LADDER,
        OPENING_DROP_SHAFT,
    }


def _room_face_name_for_opening(room_id: str, opening: Opening) -> str | None:
    is_from = room_id == opening.from_room_id
    if room_id not in {opening.from_room_id, opening.to_room_id}:
        return None

    orientation = opening.orientation
    if orientation == "x_pos":
        return FACE_X_MAX if is_from else FACE_X_MIN
    if orientation == "x_neg":
        return FACE_X_MIN if is_from else FACE_X_MAX
    if orientation == "y_pos":
        return FACE_Y_MAX if is_from else FACE_Y_MIN
    if orientation == "y_neg":
        return FACE_Y_MIN if is_from else FACE_Y_MAX
    if orientation == "z_up":
        return FACE_CEILING if is_from else FACE_FLOOR
    if orientation == "z_down":
        return FACE_FLOOR if is_from else FACE_CEILING
    return None


def _room_aperture_spec(
    room: RoomBox,
    opening: Opening,
    semantic: RoomSemantic,
    counterpart_room: RoomBox | None,
    counterpart_semantic: RoomSemantic | None,
    face_name: str,
    config: AbyssConfig,
) -> dict[str, object]:
    del counterpart_semantic
    half_u, half_v = _opening_aperture_half_sizes(room, opening, semantic, face_name, config)

    u_center, v_center = _face_local_center(room, opening.center, face_name)
    adjusted_u_center = _side_wall_opening_u_center(
        room,
        counterpart_room,
        opening,
        face_name,
        half_u,
        config,
    )
    if adjusted_u_center is not None:
        u_center = adjusted_u_center

    return {
        "id": opening.id,
        "u_center": u_center,
        "v_center": v_center,
        "half_u": half_u,
        "half_v": half_v,
    }


def _shared_opening_aperture_specs(
    room: RoomBox,
    counterpart_room: RoomBox,
    opening: Opening,
    semantic: RoomSemantic,
    counterpart_semantic: RoomSemantic,
    face_name: str,
    counterpart_face_name: str | None,
    config: AbyssConfig,
) -> tuple[dict[str, object], dict[str, object]]:
    if counterpart_face_name is None:
        fallback = _room_aperture_spec(room, opening, semantic, counterpart_room, counterpart_semantic, face_name, config)
        counterpart = _room_aperture_spec(
            counterpart_room,
            opening,
            counterpart_semantic,
            room,
            semantic,
            _room_face_name_for_opening(counterpart_room.id, opening) or face_name,
            config,
        )
        return fallback, counterpart

    room_half_u, room_half_v = _opening_aperture_half_sizes(room, opening, semantic, face_name, config)
    counterpart_half_u, counterpart_half_v = _opening_aperture_half_sizes(
        counterpart_room,
        opening,
        counterpart_semantic,
        counterpart_face_name,
        config,
    )
    shared_half_u = _shared_opening_half_size(
        room,
        counterpart_room,
        face_name,
        counterpart_face_name,
        "u",
        room_half_u,
        counterpart_half_u,
    )
    shared_half_v = _shared_opening_half_size(
        room,
        counterpart_room,
        face_name,
        counterpart_face_name,
        "v",
        room_half_v,
        counterpart_half_v,
    )

    room_u_center, room_v_center = _face_local_center(room, opening.center, face_name)
    counterpart_u_center, counterpart_v_center = _face_local_center(counterpart_room, opening.center, counterpart_face_name)
    shared_u_centers = _shared_side_wall_opening_u_centers(
        room,
        counterpart_room,
        opening,
        face_name,
        counterpart_face_name,
        shared_half_u,
        config,
    )
    if shared_u_centers is not None:
        room_u_center, counterpart_u_center = shared_u_centers
    room_spec = {
        "id": opening.id,
        "u_center": room_u_center,
        "v_center": room_v_center,
        "half_u": shared_half_u,
        "half_v": shared_half_v,
    }
    counterpart_spec = {
        "id": opening.id,
        "u_center": counterpart_u_center,
        "v_center": counterpart_v_center,
        "half_u": shared_half_u,
        "half_v": shared_half_v,
    }
    return room_spec, counterpart_spec


def _opening_aperture_half_sizes(
    room: RoomBox,
    opening: Opening,
    semantic: RoomSemantic,
    face_name: str,
    config: AbyssConfig,
) -> tuple[float, float]:
    aperture_scale = _aperture_scale_for_face(room, semantic, face_name, config)
    half_u, half_v = _aperture_half_sizes(room, face_name, opening.size, aperture_scale)
    half_u, half_v = _apply_aperture_axis_profile(room, face_name, half_u, half_v, config)
    half_u, half_v = _apply_interior_aperture_boost(room, face_name, half_u, half_v, config)
    return _apply_upper_vertical_aperture_boost(room, semantic, face_name, half_u, half_v, config)


def _append_uniform_wall_apertures(
    rooms: list[RoomBox],
    semantics: dict[str, RoomSemantic],
    selected: dict[str, dict[str, list[dict[str, object]]]],
    config: AbyssConfig,
) -> None:
    for room in rooms:
        semantic = semantics.get(room.id)
        if semantic is None:
            continue
        room_faces = selected.setdefault(room.id, {})
        for face_name in (FACE_X_MIN, FACE_X_MAX, FACE_Y_MIN, FACE_Y_MAX):
            if room_faces.get(face_name):
                continue
            room_faces.setdefault(face_name, []).append(
                _wall_aperture_spec(room, semantic, face_name, config)
            )


def _wall_aperture_spec(
    room: RoomBox,
    semantic: RoomSemantic,
    face_name: str,
    config: AbyssConfig,
) -> dict[str, object]:
    span_u, span_v = _face_span_lengths(room, face_name)
    aperture_scale = _aperture_scale_for_face(room, semantic, face_name, config)
    min_half_u, min_half_v = _aperture_min_half_sizes(face_name)
    max_half_u = max(min_half_u, span_u * 0.5 - 0.16)
    max_half_v = max(min_half_v, span_v * 0.5 - 0.16)
    half_u = _clamp(span_u * 0.5 * aperture_scale, min_half_u, max_half_u)
    half_v = _clamp(span_v * 0.5 * aperture_scale, min_half_v, max_half_v)
    half_u, half_v = _apply_aperture_axis_profile(room, face_name, half_u, half_v, config)
    return {
        "id": f"default_wall_{room.id}_{face_name}",
        "u_center": span_u * 0.5,
        "v_center": span_v * 0.5,
        "half_u": half_u,
        "half_v": half_v,
    }


def _shared_opening_half_size(
    room: RoomBox,
    counterpart_room: RoomBox,
    face_name: str,
    counterpart_face_name: str,
    axis_name: str,
    room_half: float,
    counterpart_half: float,
) -> float:
    room_max = _face_half_size_limit(room, face_name, axis_name)
    counterpart_max = _face_half_size_limit(counterpart_room, counterpart_face_name, axis_name)
    shared_max = min(room_max, counterpart_max)
    return _clamp(max(room_half, counterpart_half), 0.0, shared_max)


def _shared_side_wall_opening_u_centers(
    room: RoomBox,
    counterpart_room: RoomBox,
    opening: Opening,
    face_name: str,
    counterpart_face_name: str,
    shared_half_u: float,
    config: AbyssConfig,
) -> tuple[float, float] | None:
    if not _opening_uses_floor_aligned_bottom(opening, face_name, counterpart_face_name):
        return None

    wall_margin = 0.12
    target_bottom = opening_floor_aligned_bottom(room, counterpart_room, opening, config)
    if target_bottom is None:
        return None
    reference_floor = max(room.min_z, counterpart_room.min_z)
    min_bottom = reference_floor + 0.04
    max_bottom = min(
        room.max_z - wall_margin - shared_half_u * 2.0,
        counterpart_room.max_z - wall_margin - shared_half_u * 2.0,
    )
    if max_bottom <= min_bottom:
        return None

    shared_bottom = _clamp(target_bottom, min_bottom, max_bottom)
    return (
        shared_bottom - room.min_z + shared_half_u,
        shared_bottom - counterpart_room.min_z + shared_half_u,
    )


def _side_wall_opening_u_center(
    room: RoomBox,
    counterpart_room: RoomBox | None,
    opening: Opening,
    face_name: str,
    half_u: float,
    config: AbyssConfig,
) -> float | None:
    if counterpart_room is None or not _opening_uses_floor_aligned_bottom(opening, face_name):
        return None

    wall_margin = 0.12
    target_bottom = opening_floor_aligned_bottom(room, counterpart_room, opening, config)
    if target_bottom is None:
        return None
    reference_floor = max(room.min_z, counterpart_room.min_z)
    min_bottom = max(room.min_z + 0.04, reference_floor + 0.04)
    max_bottom = room.max_z - wall_margin - half_u * 2.0
    if max_bottom <= min_bottom:
        return None

    opening_bottom = _clamp(target_bottom, min_bottom, max_bottom)
    return opening_bottom - room.min_z + half_u


def _opening_uses_floor_aligned_bottom(
    opening: Opening,
    face_name: str,
    counterpart_face_name: str | None = None,
) -> bool:
    if not opening_uses_floor_aligned_bottom(opening):
        return False
    if face_name not in {FACE_X_MIN, FACE_X_MAX, FACE_Y_MIN, FACE_Y_MAX}:
        return False
    if counterpart_face_name is None:
        return True
    return counterpart_face_name in {FACE_X_MIN, FACE_X_MAX, FACE_Y_MIN, FACE_Y_MAX}




def _face_span_lengths(room: RoomBox, face_name: str) -> tuple[float, float]:
    if face_name in {FACE_FLOOR, FACE_CEILING}:
        return float(room.width), float(room.depth_y)
    if face_name in {FACE_X_MAX, FACE_X_MIN}:
        return float(room.height), float(room.depth_y)
    return float(room.height), float(room.width)


def _aperture_half_sizes(
    room: RoomBox,
    face_name: str,
    opening_size: tuple[float, float, float],
    pressure_scale: float,
) -> tuple[float, float]:
    size_x, size_y, size_z = opening_size
    if face_name in {FACE_FLOOR, FACE_CEILING}:
        return (
            max(0.24, size_x * 0.5 * pressure_scale),
            max(0.24, size_y * 0.5 * pressure_scale),
        )
    if face_name in {FACE_X_MAX, FACE_X_MIN}:
        return (
            max(0.22, size_z * 0.5 * pressure_scale),
            max(0.22, size_y * 0.5 * pressure_scale),
        )
    return (
        max(0.22, size_z * 0.5 * pressure_scale),
        max(0.22, size_x * 0.5 * pressure_scale),
    )


def _apply_aperture_axis_profile(
    room: RoomBox,
    face_name: str,
    half_u: float,
    half_v: float,
    config: AbyssConfig,
) -> tuple[float, float]:
    u_multiplier, v_multiplier = _aperture_axis_profile(room, face_name, config)
    span_u, span_v = _face_span_lengths(room, face_name)
    min_half_u, min_half_v = _aperture_min_half_sizes(face_name)
    max_half_u = max(min_half_u, span_u * 0.5 - 0.16)
    max_half_v = max(min_half_v, span_v * 0.5 - 0.16)
    adjusted_u = _clamp(half_u * u_multiplier, min_half_u, max_half_u)
    adjusted_v = _clamp(half_v * v_multiplier, min_half_v, max_half_v)
    return adjusted_u, adjusted_v


def _apply_interior_aperture_boost(
    room: RoomBox,
    face_name: str,
    half_u: float,
    half_v: float,
    config: AbyssConfig,
) -> tuple[float, float]:
    span_u, span_v = _face_span_lengths(room, face_name)
    min_half_u, min_half_v = _aperture_min_half_sizes(face_name)
    boosted_u = half_u * config.interior_aperture_boost
    boosted_v = half_v * config.interior_aperture_boost
    target_min_u = max(min_half_u, min(config.interior_aperture_min_half, span_u * 0.5 - 0.16))
    target_min_v = max(min_half_v, min(config.interior_aperture_min_half * 1.12, span_v * 0.5 - 0.16))
    max_half_u = max(min_half_u, span_u * 0.5 - 0.16)
    max_half_v = max(min_half_v, span_v * 0.5 - 0.16)
    return (
        _clamp(max(boosted_u, target_min_u), min_half_u, max_half_u),
        _clamp(max(boosted_v, target_min_v), min_half_v, max_half_v),
    )


def _apply_upper_vertical_aperture_boost(
    room: RoomBox,
    semantic: RoomSemantic,
    face_name: str,
    half_u: float,
    half_v: float,
    config: AbyssConfig,
) -> tuple[float, float]:
    if face_name not in {FACE_FLOOR, FACE_CEILING}:
        return (half_u, half_v)

    upper_factor = 1.0 - _clamp(
        semantic.normalized_down / config.upper_vertical_aperture_fade_down,
        0.0,
        1.0,
    )
    if upper_factor <= 0.0:
        return (half_u, half_v)

    boost = 1.0 + (config.upper_vertical_aperture_boost - 1.0) * upper_factor
    span_u, span_v = _face_span_lengths(room, face_name)
    max_half_u = max(0.24, span_u * 0.5 * config.upper_vertical_aperture_max_ratio)
    max_half_v = max(0.24, span_v * 0.5 * config.upper_vertical_aperture_max_ratio)
    return (
        _clamp(half_u * boost, 0.24, max_half_u),
        _clamp(half_v * boost, 0.24, max_half_v),
    )


def _aperture_axis_profile(
    room: RoomBox,
    face_name: str,
    config: AbyssConfig,
) -> tuple[float, float]:
    weights = _lineage_axis_weights(room)
    strength = config.aperture_axis_shape_strength
    u_multiplier = 1.0
    v_multiplier = 1.0

    if face_name in {FACE_X_MIN, FACE_X_MAX}:
        # x 切分留下 yz 竖墙，因此更容易生成沿 y 延展的横向裂口；
        # z 切分则把侧墙洞拉成更高、更像竖井擦痕的比例。
        u_multiplier += strength * (
            weights["z"] * 0.90
            - weights["x"] * 0.42
            + weights["y"] * 0.08
        )
        v_multiplier += strength * (
            weights["x"] * 1.00
            - weights["z"] * 0.24
            - weights["y"] * 0.10
        )
    elif face_name in {FACE_Y_MIN, FACE_Y_MAX}:
        u_multiplier += strength * (
            weights["z"] * 0.90
            - weights["y"] * 0.42
            + weights["x"] * 0.08
        )
        v_multiplier += strength * (
            weights["y"] * 1.00
            - weights["z"] * 0.24
            - weights["x"] * 0.10
        )
    else:
        # 顶/底面上的孔读作平面内裂口：x/y 决定平面方向，z 让它更收束成井口。
        u_multiplier += strength * (weights["x"] * 0.78 - weights["z"] * 0.18)
        v_multiplier += strength * (weights["y"] * 0.78 - weights["z"] * 0.18)
        if weights["z"] > max(weights["x"], weights["y"]):
            u_multiplier += strength * 0.08
            v_multiplier += strength * 0.08

    return (_clamp(u_multiplier, 0.72, 1.36), _clamp(v_multiplier, 0.72, 1.36))


def _aperture_min_half_sizes(face_name: str) -> tuple[float, float]:
    if face_name in {FACE_FLOOR, FACE_CEILING}:
        return (0.24, 0.24)
    return (0.22, 0.22)


def _face_half_size_limit(room: RoomBox, face_name: str, axis_name: str) -> float:
    span_u, span_v = _face_span_lengths(room, face_name)
    span = span_u if axis_name == "u" else span_v
    return span * 0.5 - 0.16


def _aperture_scale_for_face(
    room: RoomBox,
    semantic: RoomSemantic,
    face_name: str,
    config: AbyssConfig,
) -> float:
    del semantic
    base_scale = _map_range_to_scale(
        room.character.aperture_budget,
        config.aperture_min_scale,
        config.aperture_max_scale,
    )
    outer_bonus = _lineage_wall_exposure(room, face_name) * config.aperture_outer_bonus
    return _clamp(base_scale + outer_bonus, config.aperture_min_scale, 1.0)


def _map_range_to_scale(
    value: float,
    min_scale: float,
    max_scale: float,
) -> float:
    normalized_value = _clamp(value, 0.0, 1.0)
    return min_scale + (max_scale - min_scale) * normalized_value


def _lineage_axis_weights(room: RoomBox) -> dict[str, float]:
    axes = room.lineage.split_axes
    if not axes:
        return {"x": 0.0, "y": 0.0, "z": 0.0}

    total_weight = sum(range(1, len(axes) + 1))
    weights = {"x": 0.0, "y": 0.0, "z": 0.0}
    for index, axis in enumerate(axes, start=1):
        weights[axis] += index / total_weight
    return weights


def _dominant_lineage_axis(room: RoomBox) -> str:
    weights = _lineage_axis_weights(room)
    if not any(weights.values()):
        return "none"
    return max(("x", "y", "z"), key=lambda axis: (weights[axis], axis))


def _lineage_wall_exposure(room: RoomBox, face_name: str) -> float:
    if face_name == FACE_X_MIN:
        return room.lineage.wall_exposure_x_min
    if face_name == FACE_X_MAX:
        return room.lineage.wall_exposure_x_max
    if face_name == FACE_Y_MIN:
        return room.lineage.wall_exposure_y_min
    if face_name == FACE_Y_MAX:
        return room.lineage.wall_exposure_y_max
    return 0.0


def _other_opening_room_id(room_id: str, opening: Opening) -> str:
    return opening.to_room_id if room_id == opening.from_room_id else opening.from_room_id


def _face_local_center(
    room: RoomBox,
    center: tuple[float, float, float],
    face_name: str,
) -> tuple[float, float]:
    x, y, z = center
    if face_name == FACE_FLOOR:
        return (x - room.min_x, y - room.min_y)
    if face_name == FACE_CEILING:
        return (y - room.min_y, x - room.min_x)
    if face_name == FACE_Y_MIN:
        return (z - room.min_z, x - room.min_x)
    if face_name == FACE_X_MAX:
        return (z - room.min_z, y - room.min_y)
    if face_name == FACE_Y_MAX:
        return (z - room.min_z, room.max_x - x)
    return (z - room.min_z, room.max_y - y)


def _apply_opening_booleans(bpy, collection, rooms_obj, openings: list[Opening], config: AbyssConfig) -> None:
    eligible = [opening for opening in openings if _opening_creates_real_aperture(opening)]
    if not eligible:
        return

    mesh = bpy.data.meshes.new("DanteCube_Opening_Cutters_Mesh")
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    for opening in eligible:
        _append_box_bounds_geometry(vertices, faces, _opening_cutter_bounds(opening, config))

    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    cutter = bpy.data.objects.new("DanteCube_Opening_Cutters", mesh)
    cutter.display_type = "BOUNDS"
    cutter.hide_render = True
    cutter.hide_viewport = True
    collection.objects.link(cutter)
    collection.hide_viewport = True

    boolean = rooms_obj.modifiers.new("Opening apertures", "BOOLEAN")
    boolean.operation = "DIFFERENCE"
    boolean.object = cutter
    if hasattr(boolean, "solver"):
        boolean.solver = "EXACT"
    rooms_obj["aperture_opening_count"] = len(eligible)


def _opening_creates_real_aperture(opening: Opening) -> bool:
    if opening.opening_type in {OPENING_BLOCKED, OPENING_CRACK}:
        return False
    return opening.is_on_dante_path or opening.opening_type in {
        OPENING_DOOR,
        OPENING_RITUAL_GATE,
    }


def _opening_cutter_bounds(opening: Opening, config: AbyssConfig) -> tuple[float, float, float, float, float, float]:
    cx, cy, cz = opening.center
    sx, sy, sz = opening.size
    bleed = max(config.wall_thickness * 2.4, 0.12)

    if opening.orientation in {"x_pos", "x_neg"}:
        half_x = bleed
        half_y = max(sy * 0.5, 0.2)
        half_z = max(sz * 0.5, 0.3)
    elif opening.orientation in {"y_pos", "y_neg"}:
        half_x = max(sx * 0.5, 0.2)
        half_y = bleed
        half_z = max(sz * 0.5, 0.3)
    else:
        half_x = max(sx * 0.5, 0.35)
        half_y = max(sy * 0.5, 0.35)
        half_z = bleed

    return (
        cx - half_x,
        cy - half_y,
        cz - half_z,
        cx + half_x,
        cy + half_y,
        cz + half_z,
    )


def _create_opening_markers(bpy, collection, openings: list[Opening], rooms: list[RoomBox]) -> None:
    materials = _create_opening_materials(bpy)
    by_id = {room.id: room for room in rooms}
    for opening in openings:
        if not _opening_should_display_marker(opening):
            continue
        bpy.ops.mesh.primitive_cube_add(size=1, location=opening.center)
        obj = bpy.context.object
        obj.name = f"DanteOpening_{opening.opening_type}_{opening.from_room_id}_{opening.to_room_id}"
        obj.dimensions = opening.size
        structure_id = _opening_structure_id(opening, by_id)
        material_key = f"path_{structure_id}" if opening.is_on_dante_path else opening.opening_type
        obj.data.materials.append(materials[material_key])
        obj["from_room_id"] = opening.from_room_id
        obj["to_room_id"] = opening.to_room_id
        obj["opening_type"] = opening.opening_type
        obj["orientation"] = opening.orientation
        obj["is_on_dante_path"] = opening.is_on_dante_path
        obj["structure_id"] = structure_id
        obj["difficulty"] = opening.difficulty
        if opening.is_on_dante_path:
            obj.scale = (obj.scale.x * 1.18, obj.scale.y * 1.18, obj.scale.z * 1.18)
        _link_to_collection(bpy, obj, collection)


def _opening_should_display_marker(opening: Opening) -> bool:
    if opening.opening_type in {OPENING_BLOCKED, OPENING_CRACK}:
        return False
    return opening.is_on_dante_path


def _opening_structure_id(opening: Opening, by_id: dict[str, RoomBox]) -> str:
    room = by_id.get(opening.from_room_id) or by_id.get(opening.to_room_id)
    if room is None:
        return STRUCTURE_LOWER
    return room.structure_id


def _create_opening_materials(bpy) -> dict[str, object]:
    palette = {
        OPENING_RITUAL_GATE: (1.0, 0.02, 0.0, 1.0),
        OPENING_DOOR: (0.24, 0.24, 0.23, 0.45),
        OPENING_CRACK: (0.08, 0.08, 0.08, 0.55),
        OPENING_LADDER: (0.85, 0.08, 0.04, 0.8),
        OPENING_DROP_SHAFT: (1.0, 0.0, 0.0, 0.85),
        OPENING_STAIR_HINT: (0.8, 0.12, 0.06, 0.75),
        OPENING_BLOCKED: (0.0, 0.0, 0.0, 0.65),
    }
    materials = {}
    for opening_type, color in palette.items():
        material = bpy.data.materials.new(f"Dante_Opening_{opening_type}")
        material.diffuse_color = color
        material.blend_method = "BLEND"
        material.use_nodes = True
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = color
            bsdf.inputs["Alpha"].default_value = color[3]
            bsdf.inputs["Roughness"].default_value = 0.42
            if opening_type in {OPENING_RITUAL_GATE, OPENING_DROP_SHAFT, OPENING_STAIR_HINT}:
                bsdf.inputs["Emission Color"].default_value = color
                bsdf.inputs["Emission Strength"].default_value = 0.8
        materials[opening_type] = material
    for structure_id in (STRUCTURE_LOWER, STRUCTURE_UPPER):
        color = _structure_accent_color(structure_id)
        material = bpy.data.materials.new(f"Dante_Opening_Path_{structure_id}")
        material.diffuse_color = color
        material.blend_method = "BLEND"
        material.use_nodes = True
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = color
            bsdf.inputs["Alpha"].default_value = color[3]
            bsdf.inputs["Roughness"].default_value = 0.42
            bsdf.inputs["Emission Color"].default_value = color
            bsdf.inputs["Emission Strength"].default_value = 0.8 if structure_id == STRUCTURE_LOWER else 0.2
        materials[f"path_{structure_id}"] = material
    return materials


def _create_stair_markers(bpy, collection, stairs: list[StairFlight]) -> None:
    materials = _create_stair_materials(bpy)
    for stair in stairs:
        parent = bpy.data.objects.new(f"DanteStair_{stair.room_id}", None)
        parent["room_id"] = stair.room_id
        parent["entry_room_id"] = stair.entry_room_id
        parent["exit_room_id"] = stair.exit_room_id
        parent["stair_kind"] = stair.stair_kind
        parent["difficulty"] = stair.difficulty
        parent["required_run"] = stair.required_run
        parent["actual_run"] = stair.actual_run
        collection.objects.link(parent)
        if stair.structure_id == STRUCTURE_UPPER:
            material_key = f"path_{STRUCTURE_UPPER}"
        elif stair.is_on_dante_path:
            material_key = f"path_{STRUCTURE_LOWER}"
        else:
            material_key = stair.stair_kind
        if stair.stair_kind == STAIR_KIND_LADDER:
            _create_ladder_geometry(bpy, collection, parent, stair, materials[material_key])
        else:
            _create_stair_geometry(bpy, collection, parent, stair, materials[material_key])


def _create_stair_materials(bpy) -> dict[str, object]:
    palette = {
        "stair": (0.075, 0.068, 0.058, 0.92),
        "ladder": (0.075, 0.068, 0.058, 0.92),
    }
    materials = {}
    for name, color in palette.items():
        material = bpy.data.materials.new(f"Dante_Stair_{name}")
        material.diffuse_color = color
        material.blend_method = "BLEND"
        material.use_nodes = True
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = color
            bsdf.inputs["Alpha"].default_value = color[3]
            bsdf.inputs["Roughness"].default_value = 0.9
        materials[name] = material
    for structure_id in (STRUCTURE_LOWER, STRUCTURE_UPPER):
        color = _structure_accent_color(structure_id)
        material = bpy.data.materials.new(f"Dante_Stair_path_{structure_id}")
        material.diffuse_color = (color[0], color[1], color[2], 0.92)
        material.blend_method = "BLEND"
        material.use_nodes = True
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 0.92)
            bsdf.inputs["Alpha"].default_value = 0.92
            bsdf.inputs["Roughness"].default_value = 0.62
            bsdf.inputs["Emission Color"].default_value = (color[0], color[1], color[2], 1.0)
            bsdf.inputs["Emission Strength"].default_value = 0.18 if structure_id == STRUCTURE_LOWER else 0.08
        materials[f"path_{structure_id}"] = material
    return materials


def _create_stair_geometry(bpy, collection, parent, stair: StairFlight, material) -> None:
    display_steps = max(4, min(stair.step_count, 36))
    run_depth = max(stair.tread_depth, stair.actual_run / max(1, display_steps))
    rise_height = max(0.08, stair.vertical_rise / max(1, display_steps))
    line_points = list(stair.path_points)

    for index in range(display_steps):
        distance = stair.actual_run * ((index + 0.5) / display_steps)
        x, y, z, angle = _sample_polyline(line_points, distance)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z))
        obj = bpy.context.object
        obj.name = f"{parent.name}_Step_{index:02d}"
        obj.rotation_euler[2] = angle
        obj.dimensions = (run_depth * 0.92, stair.width, rise_height * 0.94)
        obj.data.materials.append(material)
        obj.parent = parent
        _link_to_collection(bpy, obj, collection)


def _create_ladder_geometry(bpy, collection, parent, stair: StairFlight, material) -> None:
    dx = stair.end[0] - stair.start[0]
    dy = stair.end[1] - stair.start[1]
    dz = stair.end[2] - stair.start[2]
    horizontal_span = math.hypot(dx, dy)
    angle = math.atan2(dy, dx) if horizontal_span > 1e-6 else 0.0
    rung_count = max(4, min(stair.step_count, 12))
    rail_spacing = stair.width * 0.72
    rail_height = max(abs(dz), stair.riser_height * rung_count)
    center_x = (stair.start[0] + stair.end[0]) / 2
    center_y = (stair.start[1] + stair.end[1]) / 2
    center_z = (stair.start[2] + stair.end[2]) / 2

    for offset in (-rail_spacing / 2, rail_spacing / 2):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(center_x, center_y, center_z))
        rail = bpy.context.object
        rail.name = f"{parent.name}_Rail_{'L' if offset < 0 else 'R'}"
        rail.rotation_euler[2] = angle
        rail.dimensions = (0.06, 0.06, rail_height)
        rail.location.x += -math.sin(angle) * offset
        rail.location.y += math.cos(angle) * offset
        rail.data.materials.append(material)
        rail.parent = parent
        _link_to_collection(bpy, rail, collection)

    for index in range(rung_count):
        t = (index + 0.5) / rung_count
        x = stair.start[0] + dx * t
        y = stair.start[1] + dy * t
        z = stair.start[2] + dz * t
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z))
        rung = bpy.context.object
        rung.name = f"{parent.name}_Rung_{index:02d}"
        rung.rotation_euler[2] = angle
        rung.dimensions = (0.08, rail_spacing, 0.05)
        rung.data.materials.append(material)
        rung.parent = parent
        _link_to_collection(bpy, rung, collection)


def _sample_polyline(points: list[tuple[float, float, float]], distance: float) -> tuple[float, float, float, float]:
    if len(points) < 2:
        point = points[0]
        return (point[0], point[1], point[2], 0.0)

    remaining = max(0.0, distance)
    for left, right in zip(points, points[1:]):
        segment_length = math.dist(left, right)
        if segment_length <= 1e-6:
            continue
        if remaining <= segment_length:
            ratio = remaining / segment_length
            x = left[0] + (right[0] - left[0]) * ratio
            y = left[1] + (right[1] - left[1]) * ratio
            z = left[2] + (right[2] - left[2]) * ratio
            angle = math.atan2(right[1] - left[1], right[0] - left[0])
            return (x, y, z, angle)
        remaining -= segment_length

    left, right = points[-2], points[-1]
    angle = math.atan2(right[1] - left[1], right[0] - left[0])
    return (right[0], right[1], right[2], angle)


def _create_room_mass_material(bpy):
    """创建总房间体量的中性预览材质。"""

    material = bpy.data.materials.new("Dante_Room_Mass_Preview")
    material.diffuse_color = (0.02, 0.02, 0.02, 0.8)
    material.blend_method = "BLEND"
    material.show_transparent_back = True
    material.use_nodes = True

    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        return material

    bsdf.inputs["Base Color"].default_value = (0.02, 0.02, 0.02, 0.8)
    bsdf.inputs["Alpha"].default_value = 0.8
    bsdf.inputs["Roughness"].default_value = 0.82
    return material


def _dante_route_face_material_indices(
    rooms: list[RoomBox],
    dante_path: list[str],
    room_face_maps: dict[str, dict[str, list[int]]],
    material_indices: dict[str, int],
) -> dict[int, int]:
    """返回 Dante agent 踏过面片的材质索引，按上下结构分色。"""

    by_id = {room.id: room for room in rooms}
    route_faces: dict[int, int] = {}

    for room_id in dante_path:
        room = by_id.get(room_id)
        if room is None:
            continue
        face_map = room_face_maps.get(room_id, {})
        if face_map.get(FACE_FLOOR):
            route_faces[face_map[FACE_FLOOR][0]] = material_indices.get(room.structure_id, material_indices[STRUCTURE_LOWER])

    for left_id, right_id in zip(dante_path, dante_path[1:]):
        left = by_id[left_id]
        right = by_id[right_id]
        if left.structure_id != right.structure_id:
            continue
        left_face_name, right_face_name = _passage_wall_face_names(left, right)
        left_faces = room_face_maps.get(left_id, {}).get(left_face_name, [])
        right_faces = room_face_maps.get(right_id, {}).get(right_face_name, [])
        if left_faces:
            route_faces[left_faces[0]] = material_indices.get(left.structure_id, material_indices[STRUCTURE_LOWER])
        if right_faces:
            route_faces[right_faces[0]] = material_indices.get(right.structure_id, material_indices[STRUCTURE_LOWER])

    return route_faces


def _passage_wall_face_names(left: RoomBox, right: RoomBox) -> tuple[str, str]:
    if left.max_x <= right.min_x:
        return FACE_X_MAX, FACE_X_MIN
    if right.max_x <= left.min_x:
        return FACE_X_MIN, FACE_X_MAX
    if left.max_y <= right.min_y:
        return FACE_Y_MAX, FACE_Y_MIN
    if right.max_y <= left.min_y:
        return FACE_Y_MIN, FACE_Y_MAX
    return _inward_ladder_wall_face_name(left), _inward_ladder_wall_face_name(right)


def _inward_ladder_wall_face_name(room: RoomBox) -> str:
    x, y, _ = room.center
    if abs(x) >= abs(y):
        return FACE_X_MIN if x >= 0 else FACE_X_MAX
    return FACE_Y_MIN if y >= 0 else FACE_Y_MAX


def _append_room_box_geometry(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int, int]],
    room: RoomBox,
    apertures: dict[str, list[dict[str, object]]],
) -> dict[str, list[int]]:
    """把一个 RoomBox 追加进合并 Mesh。

    这里不调用 bpy.ops.mesh.primitive_cube_add，避免生成大量对象。
    局部 aperture 直接在房间面片阶段切出，避免对整座深渊反复做布尔。
    """

    face_map = {
        FACE_FLOOR: [],
        FACE_CEILING: [],
        FACE_Y_MIN: [],
        FACE_X_MAX: [],
        FACE_Y_MAX: [],
        FACE_X_MIN: [],
    }

    _append_face_quads_with_holes(
        vertices,
        faces,
        face_map[FACE_FLOOR],
        [
            (room.min_x, room.min_y, room.min_z),
            (room.max_x, room.min_y, room.min_z),
            (room.max_x, room.max_y, room.min_z),
            (room.min_x, room.max_y, room.min_z),
        ],
        apertures.get(FACE_FLOOR),
    )
    _append_face_quads_with_holes(
        vertices,
        faces,
        face_map[FACE_CEILING],
        [
            (room.min_x, room.min_y, room.max_z),
            (room.min_x, room.max_y, room.max_z),
            (room.max_x, room.max_y, room.max_z),
            (room.max_x, room.min_y, room.max_z),
        ],
        apertures.get(FACE_CEILING),
    )
    _append_face_quads_with_holes(
        vertices,
        faces,
        face_map[FACE_Y_MIN],
        [
            (room.min_x, room.min_y, room.min_z),
            (room.min_x, room.min_y, room.max_z),
            (room.max_x, room.min_y, room.max_z),
            (room.max_x, room.min_y, room.min_z),
        ],
        apertures.get(FACE_Y_MIN),
    )
    _append_face_quads_with_holes(
        vertices,
        faces,
        face_map[FACE_X_MAX],
        [
            (room.max_x, room.min_y, room.min_z),
            (room.max_x, room.min_y, room.max_z),
            (room.max_x, room.max_y, room.max_z),
            (room.max_x, room.max_y, room.min_z),
        ],
        apertures.get(FACE_X_MAX),
    )
    _append_face_quads_with_holes(
        vertices,
        faces,
        face_map[FACE_Y_MAX],
        [
            (room.max_x, room.max_y, room.min_z),
            (room.max_x, room.max_y, room.max_z),
            (room.min_x, room.max_y, room.max_z),
            (room.min_x, room.max_y, room.min_z),
        ],
        apertures.get(FACE_Y_MAX),
    )
    _append_face_quads_with_holes(
        vertices,
        faces,
        face_map[FACE_X_MIN],
        [
            (room.min_x, room.max_y, room.min_z),
            (room.min_x, room.max_y, room.max_z),
            (room.min_x, room.min_y, room.max_z),
            (room.min_x, room.min_y, room.min_z),
        ],
        apertures.get(FACE_X_MIN),
    )
    return face_map


def _append_face_quads_with_holes(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int, int]],
    target_face_indices: list[int],
    outer: list[tuple[float, float, float]],
    apertures: list[dict[str, object]] | None,
) -> None:
    if not apertures:
        target_face_indices.append(_append_face(vertices, faces, outer))
        return

    u_axis = (outer[1][0] - outer[0][0], outer[1][1] - outer[0][1], outer[1][2] - outer[0][2])
    v_axis = (outer[3][0] - outer[0][0], outer[3][1] - outer[0][1], outer[3][2] - outer[0][2])
    u_length = math.dist(outer[0], outer[1])
    v_length = math.dist(outer[0], outer[3])
    if u_length <= 1e-6 or v_length <= 1e-6:
        target_face_indices.append(_append_face(vertices, faces, outer))
        return

    hole_bounds = _normalized_face_hole_bounds(apertures, u_length, v_length)
    if not hole_bounds:
        target_face_indices.append(_append_face(vertices, faces, outer))
        return

    u_coords = sorted({0.0, u_length, *(bound[0] for bound in hole_bounds), *(bound[1] for bound in hole_bounds)})
    v_coords = sorted({0.0, v_length, *(bound[2] for bound in hole_bounds), *(bound[3] for bound in hole_bounds)})
    grid = [
        [
            _point_on_face(outer[0], u_axis, v_axis, u_length, v_length, u_coord, v_coord)
            for u_coord in u_coords
        ]
        for v_coord in v_coords
    ]
    for row in range(len(v_coords) - 1):
        for col in range(len(u_coords) - 1):
            u0 = u_coords[col]
            u1 = u_coords[col + 1]
            v0 = v_coords[row]
            v1 = v_coords[row + 1]
            if u1 - u0 <= 1e-6 or v1 - v0 <= 1e-6:
                continue
            if _cell_is_inside_any_hole((u0 + u1) * 0.5, (v0 + v1) * 0.5, hole_bounds):
                continue
            quad = [
                grid[row][col],
                grid[row][col + 1],
                grid[row + 1][col + 1],
                grid[row + 1][col],
            ]
            target_face_indices.append(_append_face(vertices, faces, quad))


def _normalized_face_hole_bounds(
    apertures: list[dict[str, object]],
    u_length: float,
    v_length: float,
) -> list[tuple[float, float, float, float]]:
    bounds: list[tuple[float, float, float, float]] = []
    max_half_u = u_length * 0.5 - 0.12
    max_half_v = v_length * 0.5 - 0.12
    if max_half_u <= 0.05 or max_half_v <= 0.05:
        return bounds

    for aperture in apertures:
        center_u = float(aperture["u_center"])
        center_v = float(aperture["v_center"])
        half_u = min(float(aperture["half_u"]), max_half_u)
        half_v = min(float(aperture["half_v"]), max_half_v)
        if half_u <= 0.05 or half_v <= 0.05:
            continue

        u0 = _clamp(center_u - half_u, 0.12, u_length - 0.12)
        u1 = _clamp(center_u + half_u, 0.12, u_length - 0.12)
        v0 = _clamp(center_v - half_v, 0.12, v_length - 0.12)
        v1 = _clamp(center_v + half_v, 0.12, v_length - 0.12)
        if u1 - u0 < 0.1 or v1 - v0 < 0.1:
            continue
        bounds.append((u0, u1, v0, v1))
    return bounds


def _cell_is_inside_any_hole(
    center_u: float,
    center_v: float,
    hole_bounds: list[tuple[float, float, float, float]],
) -> bool:
    for u0, u1, v0, v1 in hole_bounds:
        if u0 <= center_u <= u1 and v0 <= center_v <= v1:
            return True
    return False


def _append_face(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int, int]],
    quad: list[tuple[float, float, float]],
) -> int:
    start = len(vertices)
    vertices.extend(quad)
    faces.append((start + 0, start + 1, start + 2, start + 3))
    return len(faces) - 1


def _point_on_face(
    origin: tuple[float, float, float],
    u_axis: tuple[float, float, float],
    v_axis: tuple[float, float, float],
    u_length: float,
    v_length: float,
    u: float,
    v: float,
) -> tuple[float, float, float]:
    u_ratio = u / u_length
    v_ratio = v / v_length
    return (
        origin[0] + u_axis[0] * u_ratio + v_axis[0] * v_ratio,
        origin[1] + u_axis[1] * u_ratio + v_axis[1] * v_ratio,
        origin[2] + u_axis[2] * u_ratio + v_axis[2] * v_ratio,
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def _create_dante_path_curve(bpy, collection, rooms: list[RoomBox], dante_path: list[str]) -> None:
    by_id = {room.id: room for room in rooms}
    path_segments: list[list[RoomBox]] = []
    current_segment: list[RoomBox] = []
    current_structure_id: str | None = None
    for room_id in dante_path:
        room = by_id.get(room_id)
        if room is None:
            continue
        if current_structure_id is None or room.structure_id == current_structure_id:
            current_segment.append(room)
            current_structure_id = room.structure_id
            continue
        if len(current_segment) >= 2:
            path_segments.append(current_segment)
        current_segment = [room]
        current_structure_id = room.structure_id
    if len(current_segment) >= 2:
        path_segments.append(current_segment)

    for segment in path_segments:
        structure_id = segment[0].structure_id
        color = _structure_accent_color(structure_id)
        curve = bpy.data.curves.new(f"Dante_Agent_Path_{segment[0].structure_id}", type="CURVE")
        curve.dimensions = "3D"
        curve.resolution_u = 2
        curve.bevel_depth = 0.07
        spline = curve.splines.new("POLY")
        spline.points.add(len(segment) - 1)
        for index, room in enumerate(segment):
            x, y, z = room.center
            spline.points[index].co = (x, y, z + 0.08, 1)

        obj = bpy.data.objects.new(curve.name, curve)
        curve_material = bpy.data.materials.new(f"Dante_Agent_Path_{structure_id}")
        curve_material.diffuse_color = color
        curve_material.use_nodes = True
        bsdf = curve_material.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = color
            bsdf.inputs["Alpha"].default_value = color[3]
            bsdf.inputs["Emission Color"].default_value = color
            bsdf.inputs["Emission Strength"].default_value = 0.25 if structure_id == STRUCTURE_LOWER else 0.08
        curve.materials.append(curve_material)
        collection.objects.link(obj)


def _create_lights(bpy, collection, rooms: list[RoomBox], config: AbyssConfig) -> None:
    if rooms:
        scene_min_z = min(room.structure_min_z for room in rooms)
        scene_max_z = max(room.structure_max_z for room in rooms)
    else:
        scene_min_z = -config.cube_size
        scene_max_z = config.cube_size if config.include_upper_cube else 0

    bpy.ops.object.light_add(type="AREA", location=(0, 0, scene_max_z + config.module_size * 2))
    top = bpy.context.object
    top.name = "DanteCube_Top_Light"
    top.data.energy = 650
    top.data.size = config.cube_size * 0.8
    _link_to_collection(bpy, top, collection)

    bpy.ops.object.light_add(type="POINT", location=(0, 0, scene_min_z + config.module_size))
    bottom = bpy.context.object
    bottom.name = "DanteCube_Bottom_Glimmer"
    bottom.data.energy = 70
    bottom.data.shadow_soft_size = config.module_size
    _link_to_collection(bpy, bottom, collection)
