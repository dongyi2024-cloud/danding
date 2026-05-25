# PRD：Dante Cube 房间类型分类与开口逻辑优化

## 1. 项目背景

当前 Dante Cube 已完成基础的递归空间生成、邻接图构建、Dante Agent 寻路、外部立方体表皮与 Blender 可视化。现有系统中，RoomBox 主要承担几何盒体职责，包含房间边界、中心点、尺寸、递归深度等信息。

下一阶段优化目标是将 RoomBox 从单纯几何体升级为具有建筑语义的空间单元。系统需要先根据房间位置、深度、体量、中心距离、路径关系等因素为房间赋予 type 分类，再基于房间之间的邻接关系和 Dante Agent 路径生成开口逻辑。

本 PRD 聚焦两个能力：

1. 房间 type 分类系统。
2. 房间之间的开口逻辑系统。

本阶段暂不实现复杂室内构件、真实楼梯建模、布尔开洞和高级 Geometry Nodes 效果。

---

## 2. 当前系统基础

当前项目已有以下能力：

1. `generate_abyss_rooms(config)` 生成递归切分后的 RoomBox 列表。
2. `RoomBox` 已包含房间 ID、边界、尺寸、体积、中心点和递归深度。
3. `build_adjacency_graph(rooms, module_size)` 根据面接触或一模数近接关系生成房间邻接图。
4. `find_dante_path(rooms, graph, config)` 根据 A* 生成 Dante Agent 从顶部到底部的路径。
5. `build_scene(rooms, graph, config)` 在 Blender 中生成外部表皮、房间合并 Mesh、路径曲线与基础材质。
6. 现有系统已经支持对路径房间的地面和通行墙面进行红色标记。

---

## 3. 本阶段目标

### 3.1 产品目标

在现有递归空间生成基础上，引入房间级语义系统，使每个房间不只是一个几何盒体，而是具有明确建筑角色和通行逻辑的空间单元。

### 3.2 算法目标

系统应自动完成：

1. 为每个 RoomBox 计算空间指标。
2. 根据指标为房间分配 type。
3. 判断 Dante Path 上的主路径房间与非路径房间。
4. 根据邻接图生成房间之间的 Opening 数据。
5. 根据开口类型区分水平通行、下行通行、上行通行、路径通行、非路径通行。
6. 在 Blender 中对不同 type 和 opening 进行基础可视化。

### 3.3 表达目标

优化后，观众应能看出：

1. 顶部空间更像入口、纪念厅、观望空间。
2. 中层空间更像过渡、回廊、压缩路径。
3. 底层空间更像忏悔室、坍塌室、深渊边界空间。
4. Dante Agent 的主路径具有明确通行痕迹。
5. 非路径空间存在旁支、封闭、迷失或不可达感。

---

## 4. 范围说明

### 4.1 本阶段包含

1. 新增房间语义分类模块。
2. 新增 opening 数据结构。
3. 新增 opening 生成逻辑。
4. 在 Blender 可视化中表达房间 type 和 opening。
5. 补充无 Blender 验证逻辑。

### 4.2 本阶段不包含

1. 不做真实布尔开洞。
2. 不做完整楼梯、坡道、梯子实体建模。
3. 不做复杂室内家具或构件系统。
4. 不做 Geometry Nodes 的最终风格化效果。
5. 不改变现有递归空间生成主算法。
6. 不改变现有 A* 路径基本逻辑。

---

## 5. 用户故事

### User Story 1：房间具有可解释角色

作为设计者，我希望每个房间都能自动获得一个 type，使我可以解释它在深渊空间中的叙事功能，而不是只看到一堆抽象盒体。

验收标准：

- 每个房间都有且只有一个 room_type。
- room_type 能通过房间深度、尺寸、中心距离、是否在 Dante Path 上推导。
- 输出结果可被验证脚本统计。

### User Story 2：路径房间与非路径房间可区分

作为设计者，我希望 Dante Agent 经过的房间被识别为主叙事空间，而没有经过的房间成为旁支、迷失或封闭空间。

验收标准：

- 每个房间包含 `is_on_dante_path` 标记。
- Dante Path 上的房间优先被分类为 path 相关类型。
- 非路径房间不会被误标为主路径空间。

### User Story 3：房间之间存在明确开口关系

作为设计者，我希望相邻房间之间不只是 graph edge，而是可以被解释为门洞、裂缝、竖井、梯子或封闭关系。

验收标准：

- 每条邻接边都能生成一个 Opening 记录。
- Opening 包含 from_room、to_room、opening_type、orientation、is_on_dante_path 等字段。
- Dante Path 上的 opening 被标记为主路径开口。

### User Story 4：Blender 中能看出分类与开口

作为观看者，我希望在 Blender 场景中能直观看出不同房间类型和通行关系。

验收标准：

- 不同 room_type 至少通过材质、透明度、描边或命名区分。
- Dante Path opening 至少通过红色发光线、墙面标记或小型开口占位符表达。
- 非路径 opening 可以用暗色、弱光或细线表达。

---

## 6. 数据结构设计

### 6.1 新增文件

建议新增：

```text
dante_cube/room_semantics.py
dante_cube/openings.py
```

可选新增：

```text
dante_cube/semantic_validation.py
```

---

## 7. Room Type 分类系统

### 7.1 RoomSemantic 数据结构

新增数据类：

```python
@dataclass(frozen=True)
class RoomSemantic:
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
    is_on_dante_path: bool
```

### 7.2 room_type 枚举

建议第一版包含以下类型：

```python
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
```

### 7.3 分类规则

分类应基于以下因素：

1. `normalized_down`：房间向下深度，范围 0 到 1。
2. `depth_band`：深度带编号。
3. `volume`：房间体积。
4. `compression`：压缩感。
5. `radial_distance`：距离中心轴的水平距离。
6. `is_on_dante_path`：是否位于主路径。
7. `chaos`：混沌/腐蚀强度。

### 7.4 第一版分类逻辑

优先级从上到下：

1. 如果房间是 Dante Path 第一个房间：`entrance`。
2. 如果房间是 Dante Path 最后一个房间：`abyss_edge`。
3. 如果 `normalized_down < 0.22` 且体量较大：`memorial_hall`。
4. 如果 `normalized_down < 0.28` 且靠近中心：`overlook`。
5. 如果房间在 Dante Path 上，且存在明显向下连接：`descent_chamber`。
6. 如果房间在 Dante Path 上，且体量狭小：`compression`。
7. 如果 `normalized_down > 0.72` 且 chaos 较高：`ruin_chamber`。
8. 如果 `normalized_down > 0.62` 且体量较小：`penitence_cell`。
9. 如果房间不在 Dante Path 上，且连接数较低：`lost_room`。
10. 如果房间不在 Dante Path 上，且靠近外围：`side_void`。
11. 其他情况：`transition`。

### 7.5 空间指标计算

建议公式：

```python
normalized_down = clamp(-room.center.z / config.cube_size, 0, 1)
radial_distance = sqrt(x*x + y*y)
volume_ratio = room.volume / (config.cube_size ** 3)
compression = clamp(1.0 - volume_ratio * scale_factor, 0, 1)
darkness = smoothstep(normalized_down)
chaos = existing_chaos_factor or smoothstep(normalized_down)
rituality = 1.0 if is_on_dante_path else clamp(1.0 - radial_distance / max_radius, 0, 1) * 0.35
```

具体数值可以在实现中调参。

---

## 8. Opening 开口逻辑系统

### 8.1 Opening 数据结构

新增数据类：

```python
@dataclass(frozen=True)
class Opening:
    id: str
    from_room_id: str
    to_room_id: str
    opening_type: str
    orientation: str
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    is_on_dante_path: bool
    difficulty: float
```

### 8.2 opening_type 枚举

建议第一版包含：

```python
OPENING_DOOR = "door"
OPENING_CRACK = "crack"
OPENING_LADDER = "ladder"
OPENING_DROP_SHAFT = "drop_shaft"
OPENING_STAIR_HINT = "stair_hint"
OPENING_RITUAL_GATE = "ritual_gate"
OPENING_BLOCKED = "blocked"
```

### 8.3 orientation 枚举

```python
ORIENTATION_X_POS = "x_pos"
ORIENTATION_X_NEG = "x_neg"
ORIENTATION_Y_POS = "y_pos"
ORIENTATION_Y_NEG = "y_neg"
ORIENTATION_Z_UP = "z_up"
ORIENTATION_Z_DOWN = "z_down"
```

### 8.4 Opening 生成输入

```python
generate_openings(
    rooms: list[RoomBox],
    graph: AdjacencyGraph,
    semantics: dict[str, RoomSemantic],
    dante_path: list[str],
    config: AbyssConfig,
) -> list[Opening]
```

### 8.5 Opening 判断逻辑

对于 graph 中每条无向边，只生成一条 Opening。

步骤：

1. 判断两个房间的相对方向。
2. 判断是否属于 Dante Path 上的连续边。
3. 判断是水平连接还是垂直连接。
4. 根据路径关系和深度决定 opening_type。
5. 计算 opening center 与 size。

### 8.6 类型规则

#### 8.6.1 Dante Path 上的连接

如果两个房间是 Dante Path 中连续房间：

- 水平连接：`ritual_gate`
- 向下连接：`drop_shaft` 或 `stair_hint`
- 向上连接：`ladder`

这些 opening 应被标记为 `is_on_dante_path=True`。

#### 8.6.2 非路径水平连接

- 上层：`door`
- 中层：`crack`
- 底层：`blocked` 或 `crack`

#### 8.6.3 非路径垂直连接

- 向下：`drop_shaft`
- 向上：`ladder`
- 深层非路径：更高概率 `blocked`

### 8.7 Opening 尺寸规则

第一版不做真实布尔开洞，只生成可视化占位体。

建议：

- `door`：宽 1.2m，高 2.2m，厚 0.08m。
- `ritual_gate`：宽 1.8m，高 2.8m，厚 0.08m。
- `crack`：宽 0.3m，高 2.8m，厚 0.04m。
- `ladder`：窄竖向红色线框或条形体。
- `drop_shaft`：地面或顶面的红色矩形洞口占位符。
- `blocked`：深色封闭标记，不表示可通行。

---

## 9. Blender 可视化要求

### 9.1 房间 type 可视化

第一版建议使用以下策略：

1. 仍然保留房间合并 Mesh。
2. 为 Mesh 增加 face 属性：
   - `room_type_index`
   - `compression`
   - `darkness`
   - `rituality`
3. 路径房间继续使用红色地面/墙面标记。
4. 不同 room_type 可以先通过材质槽进行粗分组，而不需要每个房间单独对象化。

### 9.2 Opening 可视化

第一版建议单独创建 Opening 占位对象，放入新 collection：

```text
DanteCube_Openings
```

不同 opening_type 使用不同表达：

1. `ritual_gate`：红色发光矩形框。
2. `door`：暗灰色矩形框。
3. `crack`：细长竖向裂缝。
4. `ladder`：竖向短线阵列。
5. `drop_shaft`：地面红色矩形框。
6. `blocked`：黑色半透明封闭片。

---

## 10. 验证要求

### 10.1 Room Type 验证

新增验证函数：

```python
validate_room_semantics(rooms, semantics, dante_path, config)
```

必须检查：

1. 每个 room 都有 semantic。
2. 没有 semantic 指向不存在的 room。
3. `room_type` 属于合法枚举。
4. Dante Path 第一个房间为 `entrance`。
5. Dante Path 最后一个房间为 `abyss_edge`。
6. 至少存在 3 种以上 room_type。

### 10.2 Opening 验证

新增验证函数：

```python
validate_openings(rooms, graph, openings, dante_path, config)
```

必须检查：

1. 每条 graph edge 最多对应一个 opening。
2. 每个 opening 的 from/to room 都存在。
3. `opening_type` 合法。
4. `orientation` 合法。
5. Dante Path 连续边必须存在 opening。
6. Dante Path 连续边的 opening 必须 `is_on_dante_path=True`。

### 10.3 命令行烟测输出

更新 `validate_generation.py`，输出：

```text
rooms=31
edges=180
components=1
room_types=...
openings=...
path_openings=...
errors=0
```

---

## 11. 建议开发任务拆解

### Task 1：新增 room_semantics.py

实现：

1. `RoomSemantic` 数据类。
2. room_type 常量。
3. `classify_rooms(rooms, graph, dante_path, config)`。
4. 空间指标计算函数。

验收：

- 所有房间均能获得 RoomSemantic。
- Dante Path 首尾房间分类正确。
- 输出至少 3 种 room_type。

### Task 2：新增 openings.py

实现：

1. `Opening` 数据类。
2. opening_type 常量。
3. orientation 常量。
4. `generate_openings(...)`。
5. 开口方向判断。
6. 开口中心点与尺寸估算。

验收：

- graph edge 能生成 opening。
- Dante Path 连续边 opening 正确标记。
- 水平、竖向连接可区分。

### Task 3：接入 build_scene

修改 `geometry_utils.py`：

1. 调用 `classify_rooms()`。
2. 调用 `generate_openings()`。
3. 新增 `DanteCube_Openings` collection。
4. 创建 opening 占位对象。
5. 为房间 Mesh 写入 semantic 相关属性。

验收：

- Blender 中出现 Opening collection。
- Dante Path opening 可见。
- 房间 type 可通过属性或材质检查。

### Task 4：更新 validation

修改或新增验证文件：

1. `semantic_validation.py`。
2. 更新 `validate_generation.py` 输出。

验收：

- 不依赖 Blender 即可检查 semantics 和 openings。
- 错误信息清晰可定位。

### Task 5：更新 __init__.py

导出：

```python
RoomSemantic
Opening
classify_rooms
generate_openings
```

验收：

- 外部脚本可以从 `dante_cube` 直接导入新增能力。

---

## 12. 成功指标

本阶段完成后，应满足：

1. 默认配置下，所有房间都有 room_type。
2. 默认配置下，至少生成 3 种 room_type。
3. 默认配置下，所有 Dante Path 连续边都有 opening。
4. Opening 数量与 graph edge 数量关系可解释。
5. Blender 场景中能看到房间分类差异与路径开口标记。
6. 无 Blender 验证脚本可以通过。

---

## 13. 风险与规避

### 风险 1：房间分类过于机械

规避：先用规则分类，不引入复杂随机；保留参数入口，后续可调。

### 风险 2：开口对象太多导致视觉混乱

规避：第一版只强显示 Dante Path openings，非路径 opening 可以降低透明度或默认隐藏。

### 风险 3：真实布尔开洞引起几何错误

规避：本阶段不做布尔，只做 opening marker，占位表达通行逻辑。

### 风险 4：分类结果不符合设计叙事

规避：提供统计输出，允许设计者根据 room_type 分布调参。

---

## 14. 推荐实现顺序

1. 先实现 `room_semantics.py`。
2. 再实现 `openings.py`。
3. 先跑无 Blender 验证。
4. 再接入 Blender 可视化。
5. 最后优化材质与占位对象表现。

---

## 15. 本阶段完成后的下一步

本阶段完成后，下一阶段可以继续做：

1. 房间内部构件生成。
2. 路径房间的楼梯、坡道、梯子实体化。
3. 非路径房间的封闭/迷失空间表达。
4. 基于 room_type 的材质系统。
5. 基于 chaos_factor 的 Geometry Nodes 腐蚀效果。
6. 论文中“文学意象到空间语义再到几何生成”的方法论整理。

