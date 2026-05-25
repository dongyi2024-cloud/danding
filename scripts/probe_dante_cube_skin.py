"""Blender probe: verify Dante Cube exterior skin settings and import paths.

Run inside Blender:
exec(open("/home/administrator/danding/scripts/probe_dante_cube_skin.py").read())
"""

from pathlib import Path
import sys
import traceback


PROJECT_ROOT = Path("/home/administrator/danding")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _header(title: str) -> None:
    print("")
    print("=" * 72)
    print(title)
    print("=" * 72)


def main() -> None:
    try:
        import bpy

        from dante_cube import generators, geometry_utils
        from dante_cube.generators import AbyssConfig, generate_abyss_rooms
        from dante_cube.geometry_utils import build_scene
        from dante_cube.pathfinding import build_adjacency_graph

        _header("DANTE CUBE SKIN PROBE")
        print(f"project_root={PROJECT_ROOT}")
        print(f"sys.path[0]={sys.path[0] if sys.path else '<empty>'}")
        print(f"generators_file={generators.__file__}")
        print(f"geometry_utils_file={geometry_utils.__file__}")

        cfg = AbyssConfig()
        print(f"config_skin_thickness={cfg.skin_thickness}")

        rooms = generate_abyss_rooms(cfg)
        graph = build_adjacency_graph(rooms, cfg.module_size)
        build_scene(rooms, graph, cfg)

        skin = bpy.data.objects.get("DanteCube_Exterior_Skin_Mesh")
        _header("SCENE SKIN CHECK")
        if skin is None:
            print("ERROR: DanteCube_Exterior_Skin_Mesh not found")
            return

        material = skin.data.materials[0] if skin.data.materials else None
        alpha = material.diffuse_color[3] if material is not None else "<NO MATERIAL>"
        blend = material.blend_method if material is not None else "<NO MATERIAL>"

        print(f"skin_name={skin.name}")
        print(f"skin_dimensions={tuple(round(v, 3) for v in skin.dimensions)}")
        print(f"skin_vertices={len(skin.data.vertices)}")
        print(f"skin_polygons={len(skin.data.polygons)}")
        print(f"material={material.name if material else '<NO MATERIAL>'}")
        print(f"material_alpha={alpha}")
        print(f"material_blend_method={blend}")
        print(f"collections={[collection.name for collection in skin.users_collection]}")

        _header("EXPECTED")
        print("Expected current skin thickness: 0.1m")
        print("Expected exterior dimensions: about 36.2m x 36.2m x 36.2m")
        print("Expected material alpha: 0.1")

    except Exception:
        _header("SKIN PROBE FAILED")
        traceback.print_exc()


main()
