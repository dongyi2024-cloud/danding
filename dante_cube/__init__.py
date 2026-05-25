"""Dante Cube recursive spatial generator."""

from .cellular_automata import SurvivorPoint, generate_ca_survivor_points, should_collapse_room
from .generators import AbyssConfig, RoomBox, RoomCharacter, RoomLineage, generate_abyss_rooms
from .openings import (
    LEGAL_OPENING_TYPES,
    LEGAL_ORIENTATIONS,
    Opening,
    generate_openings,
)
from .pathfinding import DantePathMetrics, build_adjacency_graph, find_dante_path, measure_dante_path
from .room_semantics import LEGAL_ROOM_TYPES, RoomSemantic, classify_rooms
from .stairs import LEGAL_STAIR_KINDS, StairFlight, generate_stairs

__all__ = [
    "AbyssConfig",
    "DantePathMetrics",
    "LEGAL_OPENING_TYPES",
    "LEGAL_ORIENTATIONS",
    "LEGAL_ROOM_TYPES",
    "LEGAL_STAIR_KINDS",
    "Opening",
    "RoomBox",
    "RoomCharacter",
    "RoomLineage",
    "RoomSemantic",
    "StairFlight",
    "SurvivorPoint",
    "build_adjacency_graph",
    "classify_rooms",
    "find_dante_path",
    "generate_ca_survivor_points",
    "generate_abyss_rooms",
    "generate_openings",
    "generate_stairs",
    "measure_dante_path",
    "should_collapse_room",
]
