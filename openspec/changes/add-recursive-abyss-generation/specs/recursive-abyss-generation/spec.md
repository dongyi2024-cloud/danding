## ADDED Requirements

### Requirement: Modular 3D room generation
The system SHALL generate room boxes inside a cubic Dante Cube boundary using recursive 3D BSP, and every room coordinate and dimension MUST align to the configured 3m architectural module.

#### Scenario: Rooms are module aligned
- **WHEN** the generator runs with the default configuration
- **THEN** every room minimum coordinate, maximum coordinate, and dimension is divisible by 3m

#### Scenario: Rooms remain inside the exterior cube
- **WHEN** the generator produces room boxes
- **THEN** every room box is fully contained within the configured exterior cube boundary

### Requirement: Abyss compression by depth
The system SHALL make recursion depth spatially meaningful by producing smaller and more center-biased rooms at lower depths of the cube.

#### Scenario: Lower rooms are more compressed
- **WHEN** generated rooms are grouped by depth band
- **THEN** lower depth bands have an average room volume less than or equal to upper depth bands, allowing deterministic ties from module quantization

#### Scenario: Lower rooms are center biased
- **WHEN** generated rooms are grouped by depth band
- **THEN** lower depth bands have average horizontal center distance from the cube center less than or equal to upper depth bands

### Requirement: Adjacency graph extraction
The system SHALL extract an adjacency graph from generated rooms so later pathfinding can traverse room-to-room connectivity.

#### Scenario: Graph covers every room
- **WHEN** the adjacency graph is built from generated rooms
- **THEN** every generated room has one graph node

#### Scenario: Adjacent rooms share a valid contact
- **WHEN** two rooms are connected by an adjacency edge
- **THEN** the rooms share a face-aligned contact or configurable near-contact within one 3m module

### Requirement: Blender scene construction
The system SHALL construct a Blender scene visualization from generated room data using Metric units, organized collections, and no heavy boolean operations in the per-room construction loop.

#### Scenario: Scene collections are created
- **WHEN** the Blender builder runs
- **THEN** it creates separate collections for rooms, abyss boundary, path/topology visualization, and lights

#### Scenario: Depth is visually legible
- **WHEN** rooms are rendered in Blender
- **THEN** room materials and lighting vary by depth so lower rooms appear darker or more compressed than upper rooms

### Requirement: Standard Python validation
The system SHALL provide validation that can run without Blender to verify module alignment, bounds containment, depth compression, and graph coverage.

#### Scenario: Validation runs outside Blender
- **WHEN** validation is executed with standard Python
- **THEN** it checks generated room data and adjacency data without importing `bpy`
