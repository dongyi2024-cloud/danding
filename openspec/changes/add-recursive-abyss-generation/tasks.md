## 1. Data Model and Generator

- [x] 1.1 Create the Python module structure for generator, pathfinding, Blender geometry, and validation entry points.
- [x] 1.2 Implement `RoomBox` and `AbyssConfig` dataclasses with 3m module defaults and deterministic seed support.
- [x] 1.3 Implement recursive 3D BSP room generation with depth-dependent split count, minimum module size, and bounds containment.
- [x] 1.4 Add inverted abyss constraints so lower rooms shrink toward the cube center while preserving module alignment.

## 2. Topology and Validation

- [x] 2.1 Implement adjacency graph extraction from generated room boxes using face-aligned or one-module near-contact rules.
- [x] 2.2 Implement standard Python validation for module alignment, cube containment, depth compression, center bias, and graph coverage.
- [x] 2.3 Add a command-line smoke check that runs generation, graph extraction, and validation without importing `bpy`.

## 3. Blender Visualization

- [x] 3.1 Implement Blender scene setup with Metric units and Dante Cube collections.
- [x] 3.2 Implement room and exterior cube visualization using reusable mesh data and collection organization.
- [x] 3.3 Implement depth-based materials, lower-depth light falloff, and abyss/topology/path placeholder curves.
- [x] 3.4 Add a Blender script entry point that builds the full v1 scene from default configuration.

## 4. Verification and Documentation

- [x] 4.1 Run OpenSpec validation for `add-recursive-abyss-generation`.
- [x] 4.2 Run the standard Python smoke check and confirm all validation checks pass.
- [x] 4.3 Document current progress in `doc/progress.md`, including implemented modules, default 3m module, and next A* pathfinding step.
