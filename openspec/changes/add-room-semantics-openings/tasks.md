## 1. Room Semantics

- [x] 1.1 Create `dante_cube/room_semantics.py` with `RoomSemantic`, room type constants, legal type set, and metric helpers.
- [x] 1.2 Implement `classify_rooms(rooms, graph, dante_path, config)` so every room receives exactly one deterministic semantic record keyed by room id.
- [x] 1.3 Implement rule priority for `entrance`, `abyss_edge`, upper memorial/overlook rooms, path descent/compression rooms, deep ruin/penitence rooms, side/lost rooms, and fallback `transition`.
- [x] 1.4 Add focused tests or smoke assertions that path endpoints are classified correctly and default output contains at least three room types.

## 2. Opening Logic

- [x] 2.1 Create `dante_cube/openings.py` with `Opening`, opening type constants, orientation constants, legal value sets, and canonical edge helpers.
- [x] 2.2 Implement `generate_openings(rooms, graph, semantics, dante_path, config)` to produce at most one Opening per undirected graph edge.
- [x] 2.3 Implement orientation, horizontal/upward/downward classification, path-edge detection, opening type rules, marker center/size estimation, and bounded difficulty.
- [x] 2.4 Add focused tests or smoke assertions that consecutive adjacent Dante Path pairs have path openings with legal type/orientation values.

## 3. Validation

- [x] 3.1 Create `dante_cube/semantic_validation.py` with `validate_room_semantics(...)` and `validate_openings(...)` that run without importing `bpy`.
- [x] 3.2 Validate missing/extra semantics, legal room types, path endpoint types, type diversity, duplicate openings, legal opening values, room references, and missing path openings.
- [x] 3.3 Update `dante_cube/validate_generation.py` to classify rooms, generate openings, run semantic/opening validation, and print room type distribution, opening count, path opening count, and error count.

## 4. Blender Integration

- [x] 4.1 Update `dante_cube/geometry_utils.py` to compute `dante_path`, semantics, and openings once inside `build_scene()`.
- [x] 4.2 Add `DanteCube_Openings` collection and create lightweight marker objects for `ritual_gate`, `door`, `crack`, `ladder`, `drop_shaft`, `stair_hint`, and `blocked`.
- [x] 4.3 Make Dante Path openings visually stronger than non-path openings through material, emission/color, scale, or naming.
- [x] 4.4 Attach room semantic data to the room mesh through material assignment, custom attributes, or deterministic naming while preserving the existing merged-room mesh path.

## 5. Package Exports and Verification

- [x] 5.1 Update `dante_cube/__init__.py` to export `RoomSemantic`, `Opening`, `classify_rooms`, `generate_openings`, and primary constants or legal value sets.
- [x] 5.2 Run the standard Python smoke check and confirm it reports semantic/opening counts with zero validation errors.
- [x] 5.3 Run or document the Blender scene build path and confirm `DanteCube_Openings` appears with visible path opening markers.
- [x] 5.4 Review implementation against the OpenSpec requirement scenarios before marking the change ready to archive.
