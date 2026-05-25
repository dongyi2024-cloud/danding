## Why

Dante Cube needs a deterministic spatial generator before pathfinding or visual refinement can be meaningful. The core architectural narrative depends on recursive compression: depth must translate into denser, narrower, more oppressive rooms inside a cubic monument.

## What Changes

- Add a recursive 3D BSP space generator for the inner abyss.
- Quantize all generated room coordinates and dimensions to a 3m architectural module.
- Constrain generated rooms inside an exterior cube while tightening the valid footprint toward the center at lower depths to create an inverted triangular abyss.
- Extract an adjacency graph from generated rooms for later Virgil/A* pathfinding.
- Add a Blender scene builder that visualizes the exterior cube, rooms, abyss depth, light falloff, and a placeholder topology/path layer.
- Add validation utilities so generated spaces can be checked outside Blender before visual construction.

## Capabilities

### New Capabilities
- `recursive-abyss-generation`: Generates modular recursive rooms, validates abyss constraints, extracts room adjacency, and builds a Blender visualization for the Dante Cube.

### Modified Capabilities

None.

## Impact

- New Python modules for generation, topology, and Blender construction.
- New script entry point for producing a Dante Cube scene in Blender.
- New OpenSpec capability describing expected generator behavior and validation requirements.
- No external runtime dependencies beyond Blender Python for scene construction; data-layer validation must run in standard Python.
