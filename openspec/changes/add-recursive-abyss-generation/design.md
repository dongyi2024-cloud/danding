## Context

The project currently contains only OpenSpec scaffolding and the Dante Cube agent instructions. This change establishes the first executable architectural system: a recursive generator for a cubic memorial space whose internal abyss becomes denser and more oppressive with depth.

The implementation must support two execution contexts:
- Standard Python for data generation, adjacency extraction, and validation.
- Blender Python (`bpy`) for scene construction and visual inspection.

## Goals / Non-Goals

**Goals:**
- Generate a deterministic set of 3D rooms inside an exterior cube using recursive BSP.
- Quantize all spatial output to a 3m architectural module.
- Make lower-depth rooms smaller and more center-biased to express the inverted abyss.
- Extract an adjacency graph suitable for later Virgil/A* pathfinding.
- Build a complete Blender visualization using collections, instancing-friendly mesh creation, depth materials, boundary geometry, lighting, and placeholder topology/path curves.

**Non-Goals:**
- Final A* route optimization is not part of this change.
- Door carving, heavy boolean subtraction, and construction-detail modeling are out of scope.
- Geometry Nodes are not required for v1; they can be introduced later for facade panelization or large repeated surface treatments.

## Decisions

- Use full 3D BSP rather than layered 2.5D or Octree.
  - Rationale: full 3D splitting better matches the Dante Cube concept of rooms compressed through the volume, not just stacked plans.
  - Alternative considered: 2.5D layers would simplify graph generation but reduce spatial intensity; Octree would be modular but too mechanically uniform.

- Represent generated spaces as plain Python dataclasses.
  - Rationale: the generator and tests must run without Blender, while `geometry_utils.py` can consume the same data inside Blender.
  - Alternative considered: building directly with `bpy` during recursion would couple algorithm and visualization and make validation slower.

- Enforce 3m quantization at the generator boundary.
  - Rationale: the project needs architectural scale discipline; every room extent and coordinate must align to a 3m module.
  - Alternative considered: continuous coordinates with final rounding risk invalid overlaps and adjacency gaps.

- Model the abyss with a depth-dependent center bias and footprint shrink.
  - Rationale: lower rooms should feel pulled toward the abyss center and become more compressed.
  - Alternative considered: random BSP alone would create variety but not the required inverted triangular narrative.

- Use Blender collections and reusable cube mesh construction, avoiding boolean operations in the generation loop.
  - Rationale: room counts can grow quickly under recursion; repeated booleans would make iteration slow and fragile.
  - Alternative considered: boolean subtracting rooms from a solid cube would create a stronger mass/void artifact but is too expensive for v1.

## Risks / Trade-offs

- Full 3D BSP can produce disconnected pockets -> mitigate by extracting and validating adjacency immediately after generation.
- Strong center bias can collapse lower levels into too few rooms -> mitigate with configurable minimum room modules and split-depth limits.
- Blender visualization may become visually dense -> mitigate with depth-based material alpha and separate collections that can be hidden independently.
- Without final A* routing, path narrative is incomplete -> mitigate by rendering topology/path placeholders and preserving stable graph interfaces for the next change.
