"""Blender blockout generator for the four MVP areas.

**Not run.** Blender is not installed in the authoring environment; this script is a
starting point for the GPU workstation. It creates no files unless executed there with
``--save <path.blend>``; no binaries are committed by this repository change.

Run inside Blender's Scripting workspace or with::

    blender -b --python clients/unreal/tools/blender_blockout.py -- --save /tmp/b.blend

Conventions:
- 1 Blender unit = 1 meter. UE imports at 100x, which matches the centimeter layout JSON.
- X is east, Y is north, Z is up (same as ``mvp_scene.json``).
- Area origins are the interaction anchors from the layout divided by 100.
- The layout JSON remains the placement truth; this file only makes rough geometry.
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy

# Interaction anchors from clients/unreal/Content/Layout/mvp_scene.json, in meters.
AREA_ORIGINS = {
    "Courtyard": (2.5, 2.0),
    "SectGate": (59.0, 12.0),
    "ForestEdge": (132.0, -6.0),
    "SecretRealmEntrance": (299.0, 86.0),
}


def _material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name=name)
    material.diffuse_color = color
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.9
    return material


def _collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
    return collection


def _box(
    name: str,
    size: tuple[float, float, float],
    location: tuple[float, float, float],
    collection: bpy.types.Collection,
    material: bpy.types.Material,
) -> bpy.types.Object:
    """Create one axis-aligned box without relying on operator context."""

    hx, hy, hz = (value / 2.0 for value in size)
    vertices = [
        (-hx, -hy, -hz),
        (hx, -hy, -hz),
        (hx, hy, -hz),
        (-hx, hy, -hz),
        (-hx, -hy, hz),
        (hx, -hy, hz),
        (hx, hy, hz),
        (-hx, hy, hz),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.data.materials.append(material)
    collection.objects.link(obj)
    return obj


def _courtyard(stone: bpy.types.Material, wood: bpy.types.Material) -> None:
    """Town courtyard: ground, low walls, and three market stalls."""

    collection = _collection("Courtyard")
    ox, oy = AREA_ORIGINS["Courtyard"]
    _box("Courtyard_Ground", (20, 20, 0.2), (ox, oy, -0.1), collection, stone)
    _box("Courtyard_WallNorth", (20, 0.5, 2), (ox, oy + 10, 1), collection, stone)
    _box("Courtyard_WallSouth", (20, 0.5, 2), (ox, oy - 10, 1), collection, stone)
    _box("Courtyard_WallEast", (0.5, 20, 2), (ox + 10, oy, 1), collection, stone)

    for index in range(3):
        x = ox - 6 + index * 5
        _box(f"Stall_{index}_Counter", (3, 1.2, 1), (x, oy + 4, 0.5), collection, wood)
        _box(f"Stall_{index}_Roof", (3.4, 1.8, 0.2), (x, oy + 4, 2.4), collection, wood)
        _box(f"Stall_{index}_PostW", (0.2, 0.2, 2.4), (x - 1.5, oy + 4, 1.2), collection, wood)
        _box(f"Stall_{index}_PostE", (0.2, 0.2, 2.4), (x + 1.5, oy + 4, 1.2), collection, wood)


def _sect_gate(stone: bpy.types.Material, wood: bpy.types.Material) -> None:
    """Sect gate: approach, two pillars, lintel, steps, and a hall facade blockout."""

    collection = _collection("SectGate")
    ox, oy = AREA_ORIGINS["SectGate"]
    _box("Gate_Ground", (28, 14, 0.2), (ox, oy, -0.1), collection, stone)
    _box("Gate_PillarNorth", (2, 2, 9), (ox, oy + 4, 4.5), collection, stone)
    _box("Gate_PillarSouth", (2, 2, 9), (ox, oy - 4, 4.5), collection, stone)
    _box("Gate_Lintel", (2.5, 10, 1.5), (ox, oy, 9.75), collection, wood)
    _box("Gate_Step0", (8, 6, 0.3), (ox - 2, oy, 0.15), collection, stone)
    _box("Gate_Step1", (8, 5, 0.3), (ox - 2, oy, 0.45), collection, stone)
    _box("Gate_HallFacade", (10, 16, 7), (ox + 8, oy, 3.5), collection, stone)
    _box("Gate_HallRoof", (12, 18, 0.6), (ox + 8, oy, 7.3), collection, wood)


def _forest_edge(foliage: bpy.types.Material, wood: bpy.types.Material) -> None:
    """Forest edge: ground, a trail, and deterministic simple tree clusters."""

    collection = _collection("ForestEdge")
    ox, oy = AREA_ORIGINS["ForestEdge"]
    _box("Forest_Ground", (30, 22, 0.2), (ox, oy, -0.1), collection, foliage)
    _box("Forest_Trail", (30, 2, 0.05), (ox, oy, 0.02), collection, wood)

    # Fixed offsets deliberately avoid random placement; reruns are identical.
    offsets = [
        (-12, 8, 1.0),
        (-7, 6, 0.8),
        (-2, 9, 1.2),
        (4, 7, 0.9),
        (9, 9, 1.1),
        (12, 5, 0.85),
        (6, -7, 1.0),
        (-4, -8, 0.95),
        (11, -8, 1.15),
    ]
    for index, (dx, dy, scale) in enumerate(offsets):
        x, y = ox + dx, oy + dy
        _box(f"Tree_{index}_Trunk", (0.6 * scale, 0.6 * scale, 4 * scale), (x, y, 2 * scale),
             collection, wood)
        _box(f"Tree_{index}_Canopy", (5 * scale, 5 * scale, 5 * scale),
             (x, y, 6 * scale), collection, foliage)


def _secret_realm_entrance(dark_rock: bpy.types.Material, stone: bpy.types.Material) -> None:
    """Cave mouth: cliff wall, mouth frame, and a dark recess placeholder."""

    collection = _collection("SecretRealmEntrance")
    ox, oy = AREA_ORIGINS["SecretRealmEntrance"]
    _box("Cave_Ground", (20, 20, 0.2), (ox, oy, -0.1), collection, stone)
    _box("Cave_CliffBack", (2, 16, 12), (ox + 8, oy, 6), collection, dark_rock)
    _box("Cave_CliffNorth", (10, 2, 12), (ox + 4, oy + 7, 6), collection, dark_rock)
    _box("Cave_CliffSouth", (10, 2, 12), (ox + 4, oy - 7, 6), collection, dark_rock)
    _box("Cave_MouthLintel", (2, 8, 2), (ox + 2, oy, 7), collection, dark_rock)
    _box("Cave_MouthNorth", (2, 2, 6), (ox + 2, oy + 3, 3), collection, dark_rock)
    _box("Cave_MouthSouth", (2, 2, 6), (ox + 2, oy - 3, 3), collection, dark_rock)
    _box("Cave_Recess", (1, 4, 5), (ox + 6, oy, 2.5), collection, dark_rock)


def main() -> None:
    """Build the four collections in the current scene, optionally saving a .blend."""

    # Keep a neutral scene; delete only objects from a previous run of this script.
    for name in ("Courtyard_", "Stall_", "Gate_", "Forest_", "Tree_", "Cave_"):
        for obj in list(bpy.data.objects):
            if obj.name.startswith(name):
                bpy.data.objects.remove(obj, do_unlink=True)

    stone = _material("Stone_Placeholder", (0.42, 0.40, 0.36, 1.0))
    wood = _material("Wood_Placeholder", (0.25, 0.15, 0.08, 1.0))
    foliage = _material("Foliage_Placeholder", (0.10, 0.20, 0.08, 1.0))
    dark_rock = _material("DarkRock_Placeholder", (0.08, 0.08, 0.10, 1.0))

    _courtyard(stone, wood)
    _sect_gate(stone, wood)
    _forest_edge(foliage, wood)
    _secret_realm_entrance(dark_rock, stone)

    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    print("blockout: created 4 collections (Courtyard, SectGate, ForestEdge, "
          "SecretRealmEntrance)")

    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--save" in argv:
        index = argv.index("--save")
        if index + 1 < len(argv):
            target = Path(argv[index + 1]).expanduser().resolve()
            bpy.ops.wm.save_as_mainfile(filepath=str(target))
            print(f"blockout: saved {target}")


if __name__ == "__main__":
    main()