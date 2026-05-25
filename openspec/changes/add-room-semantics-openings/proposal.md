## Why

The Dante Cube already generates recursive rooms, topology, and a guided path, but each RoomBox is still mostly geometric data. The next architectural step is to turn rooms into semantic spatial units so depth, compression, path membership, and adjacency can read as entrance, descent, penitence, ruin, and abyss-edge conditions.

## What Changes

- Add deterministic room semantic classification for every generated RoomBox.
- Add room-level metrics such as normalized depth, radial distance, compression, darkness, chaos, rituality, and Dante Path membership.
- Add Opening records for graph edges so adjacency becomes interpretable as doors, cracks, ritual gates, ladders, drop shafts, stair hints, or blocked passages.
- Mark Dante Path rooms and consecutive Dante Path openings as primary narrative circulation.
- Add Blender visualization hooks for room types and opening markers without introducing boolean wall cuts.
- Add non-Blender validation for semantics, openings, and path-opening consistency.
- Export the new semantic and opening APIs from the package.

## Capabilities

### New Capabilities
- `room-semantics-openings`: Classifies generated Dante Cube rooms by architectural role, derives opening records from adjacency, validates the semantic graph, and visualizes room/opening logic in Blender.

### Modified Capabilities

None.

## Impact

- New modules: `dante_cube/room_semantics.py`, `dante_cube/openings.py`, and likely `dante_cube/semantic_validation.py`.
- Updates to `dante_cube/geometry_utils.py` to classify rooms, generate openings, create `DanteCube_Openings`, and attach semantic attributes or materials.
- Updates to `dante_cube/validate_generation.py` and package exports in `dante_cube/__init__.py`.
- No change to the recursive abyss generation algorithm or A* pathfinding contract.
- No new external dependency; Blender-specific visualization remains behind existing Blender execution paths.
