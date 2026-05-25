## Context

The current Dante Cube codebase already separates data generation, topology/pathfinding, validation, and Blender scene construction. `RoomBox` carries geometric bounds, dimensions, center, volume, and recursion depth; `build_adjacency_graph()` converts spatial contact into an undirected graph; `find_dante_path()` produces the Virgil-guided descent path; `build_scene()` visualizes rooms, exterior skin, path curves, and lighting in Blender.

This change adds architectural meaning after generation and pathfinding. It must preserve the existing recursive abyss algorithm and A* path contract while adding a semantic layer that can run in standard Python and a visualization layer that only imports `bpy` inside Blender-specific functions.

## Goals / Non-Goals

**Goals:**
- Classify every generated room into exactly one architectural room type.
- Compute deterministic metrics that explain the classification: depth band, normalized descent, radial distance, volume, compression, darkness, chaos, rituality, and path membership.
- Convert every adjacency edge into at most one Opening record with type, orientation, approximate marker center/size, path membership, and difficulty.
- Ensure Dante Path consecutive edges produce openings marked as primary narrative circulation.
- Add validation that runs without Blender and reports actionable errors.
- Add Blender opening markers and room semantic attributes/material grouping without heavy boolean wall cuts.

**Non-Goals:**
- Do not change recursive BSP generation, abyss tapering, or room quantization.
- Do not change the A* pathfinding cost model except for consuming its resulting path.
- Do not model real doors, stairs, ladders, ramps, furniture, or boolean-cut wall holes.
- Do not require Geometry Nodes for this stage; simple repeated facade or marker effects can move there later.

## Decisions

- Add `room_semantics.py` as a pure Python semantic layer.
  - Rationale: classification belongs after geometry/topology/path are known, and validation must run without Blender.
  - Alternative considered: storing mutable fields directly on `RoomBox`; rejected because `RoomBox` is frozen geometry data and should stay stable.

- Represent classifications with string constants and a frozen `RoomSemantic` dataclass.
  - Rationale: string constants are easy to export, validate, print in smoke tests, and use as Blender custom attributes or material keys.
  - Alternative considered: Python `Enum`; useful, but less convenient for Blender attribute serialization and existing simple-module style.

- Use deterministic rule priority for v1 classification.
  - Rationale: design review needs repeatable type distribution; randomness would make parameter tuning hard.
  - Alternative considered: weighted stochastic classification; defer until the designer can evaluate stable baseline distributions.

- Add `openings.py` as a pure Python adjacency interpreter.
  - Rationale: graph edges are topological facts, but openings are architectural readings of those edges.
  - Alternative considered: deriving opening markers directly in `geometry_utils.py`; rejected because non-Blender validation and future export workflows need the same opening data.

- Generate one canonical Opening per undirected graph edge.
  - Rationale: prevents duplicate marker objects and makes edge/opening validation straightforward.
  - Alternative considered: directional openings for each side of the edge; unnecessary until doors have room-specific swing, threshold, or narrative asymmetry.

- Infer orientation from dominant center delta and shared/near-contact axis.
  - Rationale: existing adjacency includes face contact or one-module near contact; center delta is robust enough for marker orientation and horizontal/vertical classification.
  - Alternative considered: exact face-overlap solving for all axes first; more precise, but not needed until real cut geometry is introduced.

- Visualize openings as lightweight marker objects in `DanteCube_Openings`.
  - Rationale: markers communicate circulation logic without boolean cost or fragile mesh surgery.
  - Alternative considered: cutting actual holes in room meshes; explicitly out of scope and risky for dense recursive rooms.

## Risks / Trade-offs

- Classification may feel too mechanical -> expose small helper functions and readable thresholds so the designer can tune depth, volume, radial, and chaos parameters later.
- Some generated graphs may not include all Dante Path consecutive pairs if pathfinding returns fallback single-node segments -> validation should only require openings for actual consecutive path pairs.
- Orientation inferred from centers can be ambiguous for equal deltas -> use deterministic axis precedence and validate legal orientation rather than promising construction-grade door placement.
- Opening markers can visually clutter dense scenes -> make Dante Path openings visually strong and non-path openings subdued or optionally hidden by collection/material settings.
- Blender custom attributes can vary across Blender versions -> keep material/collection marker visualization as the primary acceptance path and treat mesh attributes as additive metadata.

## Migration Plan

1. Add pure Python modules for semantics and openings.
2. Add semantic/opening validation and wire it into the standard smoke check.
3. Export new APIs from `dante_cube/__init__.py`.
4. Update `build_scene()` to call classification/opening generation and create the opening collection.
5. Preserve existing script entry points; rollback is removing the new calls and modules without changing generation/pathfinding.
