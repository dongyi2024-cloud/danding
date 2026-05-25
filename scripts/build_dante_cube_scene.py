"""Blender entry point: run inside Blender Python to build the Dante Cube scene."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dante_cube.generators import AbyssConfig, generate_abyss_rooms
from dante_cube.geometry_utils import build_scene
from dante_cube.pathfinding import build_adjacency_graph


def main() -> None:
    config = AbyssConfig()
    rooms = generate_abyss_rooms(config)
    graph = build_adjacency_graph(rooms, config.module_size)
    build_scene(rooms, graph, config)


if __name__ == "__main__":
    main()
