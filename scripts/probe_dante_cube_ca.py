"""Blender probe: verify Dante Cube CA point cloud generation and import paths.

Run inside Blender:
exec(open("/home/administrator/danding/scripts/probe_dante_cube_ca.py").read())
"""

from pathlib import Path
import sys
import traceback


PROJECT_ROOT = Path("/home/administrator/danding")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _print_header(title: str) -> None:
    print("")
    print("=" * 72)
    print(title)
    print("=" * 72)


def main() -> None:
    _print_header("DANTE CUBE CA PROBE")
    print(f"project_root={PROJECT_ROOT}")
    print(f"project_root_exists={PROJECT_ROOT.exists()}")
    print(f"sys.path[0]={sys.path[0] if sys.path else '<empty>'}")

    try:
        import bpy

        from dante_cube import cellular_automata, generators, geometry_utils, pathfinding
        from dante_cube.generators import AbyssConfig, generate_abyss_rooms
        from dante_cube.pathfinding import build_adjacency_graph
        from dante_cube.geometry_utils import build_scene
        from dante_cube.cellular_automata import generate_ca_survivor_points, should_collapse_room

        _print_header("IMPORTED MODULES")
        print(f"generators_file={generators.__file__}")
        print(f"geometry_utils_file={geometry_utils.__file__}")
        print(f"cellular_automata_file={cellular_automata.__file__}")
        print(f"pathfinding_file={pathfinding.__file__}")

        cfg = AbyssConfig()
        _print_header("CONFIG")
        for name in (
            "cube_size",
            "module_size",
            "skin_thickness",
            "max_depth",
            "lower_extra_depth",
            "ca_grid_resolution",
            "ca_iterations",
            "ca_trigger_depth_ratio",
            "ca_base_survival_rate",
            "ca_center_decay",
            "seed",
        ):
            print(f"{name}={getattr(cfg, name, '<MISSING>')}")

        rooms = generate_abyss_rooms(cfg)
        ca_rooms = [room for room in rooms if should_collapse_room(room, cfg)]
        point_counts = [len(generate_ca_survivor_points(room, cfg)) for room in ca_rooms]
        graph = build_adjacency_graph(rooms, cfg.module_size)

        _print_header("DATA LAYER")
        print(f"rooms={len(rooms)}")
        print(f"ca_rooms={len(ca_rooms)}")
        print(f"ca_points_total={sum(point_counts)}")
        print(f"ca_points_min={min(point_counts) if point_counts else 0}")
        print(f"ca_points_max={max(point_counts) if point_counts else 0}")
        print(f"ca_room_ids={[room.id for room in ca_rooms[:8]]}")

        build_scene(rooms, graph, cfg)

        _print_header("SCENE OBJECTS")
        object_names = sorted(obj.name for obj in bpy.data.objects)
        for name in object_names:
            if name.startswith("DanteCube"):
                obj = bpy.data.objects[name]
                data = getattr(obj, "data", None)
                vertex_count = len(data.vertices) if data is not None and hasattr(data, "vertices") else "-"
                polygon_count = len(data.polygons) if data is not None and hasattr(data, "polygons") else "-"
                collections = [collection.name for collection in obj.users_collection]
                print(
                    f"name={name} type={obj.type} vertices={vertex_count} "
                    f"polygons={polygon_count} hidden={obj.hide_viewport} collections={collections}"
                )

        ca_obj = bpy.data.objects.get("DanteCube_CA_Survivor_Points")
        _print_header("CA OBJECT CHECK")
        if ca_obj is None:
            print("ERROR: DanteCube_CA_Survivor_Points was not created.")
        else:
            attrs = list(ca_obj.data.attributes.keys())
            groups = [group.name for group in ca_obj.vertex_groups]
            print("OK: DanteCube_CA_Survivor_Points exists.")
            print(f"vertices={len(ca_obj.data.vertices)}")
            print(f"edges={len(ca_obj.data.edges)}")
            print(f"polygons={len(ca_obj.data.polygons)}")
            print(f"attributes={attrs}")
            print(f"vertex_groups={groups}")
            print(f"location={tuple(round(v, 3) for v in ca_obj.location)}")
            print(f"dimensions={tuple(round(v, 3) for v in ca_obj.dimensions)}")

        _print_header("PROBE DONE")

    except Exception:
        _print_header("PROBE FAILED")
        traceback.print_exc()


if __name__ == "__main__" or __name__ == "<run_path>":
    main()
else:
    main()
