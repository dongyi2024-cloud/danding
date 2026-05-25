## ADDED Requirements

### Requirement: Room semantic classification
The system SHALL assign exactly one architectural `room_type` to every generated RoomBox using deterministic metrics derived from room geometry, depth, graph connectivity, Dante Path membership, and configuration.

#### Scenario: Every room receives one semantic record
- **WHEN** room classification runs with generated rooms, an adjacency graph, a Dante Path, and an AbyssConfig
- **THEN** the output contains exactly one RoomSemantic for every input room id

#### Scenario: Path endpoints receive narrative types
- **WHEN** the Dante Path contains at least two rooms
- **THEN** the first path room is classified as `entrance` and the last path room is classified as `abyss_edge`

#### Scenario: Classification is diverse enough to read spatially
- **WHEN** classification runs with the default Dante Cube configuration
- **THEN** the output contains at least three distinct `room_type` values

### Requirement: Room semantic metrics
The system SHALL compute and expose room metrics including `depth_band`, `normalized_down`, `radial_distance`, `volume`, `compression`, `darkness`, `chaos`, `rituality`, and `is_on_dante_path`.

#### Scenario: Metrics remain bounded where required
- **WHEN** semantic metrics are computed for any room inside the cube
- **THEN** `normalized_down`, `compression`, `darkness`, `chaos`, and `rituality` are each within the inclusive range 0.0 to 1.0

#### Scenario: Path membership is represented
- **WHEN** a room id appears in the Dante Path
- **THEN** its RoomSemantic has `is_on_dante_path` set to true

### Requirement: Opening generation from adjacency
The system SHALL generate Opening records from the adjacency graph so each graph edge has at most one canonical opening connecting the two rooms.

#### Scenario: Graph edges map to openings
- **WHEN** openings are generated from rooms, graph, semantics, Dante Path, and configuration
- **THEN** every generated Opening references two existing adjacent room ids

#### Scenario: Duplicate openings are not produced
- **WHEN** an undirected graph edge appears as `A-B`
- **THEN** no more than one Opening exists for that unordered room pair

### Requirement: Opening type and orientation
The system SHALL classify openings with legal `opening_type` and `orientation` values and distinguish horizontal, upward, and downward spatial connections.

#### Scenario: Opening values are legal
- **WHEN** openings are generated
- **THEN** every `opening_type` is one of `door`, `crack`, `ladder`, `drop_shaft`, `stair_hint`, `ritual_gate`, or `blocked`
- **THEN** every `orientation` is one of `x_pos`, `x_neg`, `y_pos`, `y_neg`, `z_up`, or `z_down`

#### Scenario: Dante Path openings are marked
- **WHEN** two consecutive Dante Path rooms are adjacent
- **THEN** their Opening exists and has `is_on_dante_path` set to true

#### Scenario: Path opening types express ritual descent
- **WHEN** a generated Opening connects two consecutive Dante Path rooms
- **THEN** a horizontal path connection is classified as `ritual_gate`, a downward path connection is classified as `drop_shaft` or `stair_hint`, and an upward path connection is classified as `ladder`

### Requirement: Opening marker geometry data
The system SHALL compute approximate marker `center`, `size`, and `difficulty` values for every Opening without performing boolean wall cuts.

#### Scenario: Opening markers have valid dimensions
- **WHEN** an Opening is generated
- **THEN** its `center` contains three numeric coordinates, its `size` contains three positive numeric dimensions, and its `difficulty` is within the inclusive range 0.0 to 1.0

#### Scenario: Boolean cuts are not required
- **WHEN** opening visualization is built in Blender
- **THEN** the system uses marker objects or equivalent lightweight visual placeholders instead of per-opening boolean subtraction

### Requirement: Blender semantic visualization
The system SHALL make room types and openings legible in Blender while preserving the existing collection-based scene organization.

#### Scenario: Opening collection is created
- **WHEN** the Blender scene builder runs
- **THEN** it creates a `DanteCube_Openings` collection containing visual markers for generated openings

#### Scenario: Dante Path openings are visually emphasized
- **WHEN** opening markers are created for Dante Path openings
- **THEN** those markers are visually distinct from non-path openings through material, emission color, scale, or naming

#### Scenario: Room semantic data is inspectable
- **WHEN** room geometry is created in Blender
- **THEN** room semantic information is available through material assignment, object or mesh attributes, or deterministic naming that allows room types to be inspected

### Requirement: Standard Python semantic validation
The system SHALL validate room semantics and openings without importing Blender.

#### Scenario: Semantic validation catches missing room records
- **WHEN** semantic validation runs
- **THEN** it reports an error if any generated room has no RoomSemantic record

#### Scenario: Opening validation catches missing path openings
- **WHEN** opening validation runs
- **THEN** it reports an error if any adjacent consecutive Dante Path pair has no Opening marked as a Dante Path opening

#### Scenario: Smoke check reports semantic counts
- **WHEN** the command-line smoke check runs
- **THEN** it prints room count, edge count, component count, room type distribution, opening count, path opening count, and error count
