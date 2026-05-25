# Dante Cube Progress

## Current State

- Created OpenSpec change `add-recursive-abyss-generation`.
- Implemented recursive 3D BSP space generation in `dante_cube/generators.py`.
- Set the default architectural module to 3m through `AbyssConfig.module_size`.
- Added inverted abyss compression: lower rooms receive additional recursion and are constrained toward the cube center.
- Added adjacency graph extraction in `dante_cube/pathfinding.py`.
- Added Virgil pathfinding in `dante_cube/pathfinding.py`: A* descent with center pull, downward reward, and staged waypoints.
- Added standard Python validation and smoke check in `dante_cube/validation.py` and `dante_cube/validate_generation.py`.
- Added Blender scene construction in `dante_cube/geometry_utils.py`.
- Added Blender entry point `scripts/build_dante_cube_scene.py`.
- Replaced the exterior wire boundary with six outward-facing skin panels controlled by `AbyssConfig.skin_thickness`.
- Merged generated room boxes into one Blender mesh object and stored a face-domain `chaos_factor` attribute for Geometry Nodes erosion.
- Added a 3D Cellular Automata collapse layer for deep/max-depth rooms, outputting `DanteCube_CA_Survivor_Points` with `is_survivor` and `voxel_size` point attributes.
- Added room semantics, path-aware openings, and non-Blender semantic validation.
- Exposed Virgil path atmosphere as config parameters so descent behavior can be tuned without rewriting A*.
- Added `dante_cube/stairs.py` to derive path-aware stair flights from room entry/exit openings.
- Updated stair flights to use a fixed pitch and wall-hugging spiral centerline instead of direct room-center interpolation.
- Updated Blender opening visualization so every room now receives apertures on all four side walls, while eligible floor/ceiling passages are still carved from explicit openings.
- Replaced the local aperture topology with an orthogonal rectangular cut pattern to avoid diagonal corner edges.
- Aperture sizing now uses one explicit pressure-to-scale mapping range, with lower-pressure rooms producing smaller wall openings and higher-pressure rooms producing larger ones.
- Added recursive `RoomLineage` tracking and lineage-derived `aperture_budget`, so wall apertures now read split history and per-wall recursive exposure instead of relying only on post-hoc geometric proximity.
- Added split-axis-aware aperture shaping: recency-weighted `x/y/z` lineage now skews wall openings toward different height/width ratios, so apertures preserve visible traces of the recursive cut directions.
- Added `DanteCube_Stairs` Blender collection with lightweight stair/ladder markers hosted inside path rooms.
- Added `DanteCube_RoomCells` so every room is also emitted as an individually selectable/editable Blender object, while the merged room mesh is preserved and hidden by default.
- Reworked room-to-room circulation so every adjacency opening now becomes a traversable geometric passage instead of falling back to `blocked`/`crack` dead edges.
- Updated wall/floor/ceiling aperture meshing to support multiple openings on the same face, so dense neighbor clusters no longer collapse to a single surviving hole.
- Removed the old fallback side-wall apertures that were not backed by adjacency, keeping circulation geometry aligned with the actual room graph.

## Verification

- `openspec validate add-recursive-abyss-generation` passes.
- `python3 -m dante_cube.validate_generation` passes with the default config:
  - rooms: 31
  - edges: 180
  - connected components: 1
  - Dante path rooms: 6
  - Dante path descent: 27m
  - stair flights: 4
  - module size: 3m
- Room-to-room circulation coverage now matches the topology:
  - traversable openings with geometry: 180 / 180 graph edges
  - per-room geometric aperture specs: 360 / 360 expected two-sided openings
- `blender -b --factory-startup --python scripts/build_dante_cube_scene.py --python-exit-code 1` passes.

