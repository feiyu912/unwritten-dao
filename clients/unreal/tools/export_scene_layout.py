"""Export a deterministic UE5 blockout layout from the seed world.

Builds the authoritative seed world with ``world_core.create_world(42)`` and writes
``clients/unreal/Content/Layout/mvp_scene.json``. The file is developer tooling for the
Unreal editor: it carries stable IDs, 2D blockout coordinates, NPC spawn offsets, and a
location -> actor tag / streaming suggestion table. It is not world state and the client
must never treat it as such.

Only the Python standard library and ``world_core`` are used. Coordinates and local NPC
offsets are pure functions of stable IDs, so the JSON is byte-identical across platforms
and repeated runs.

Usage (from the repository root)::

    uv run python -m clients.unreal.tools.export_scene_layout
    uv run python clients/unreal/tools/export_scene_layout.py --output /tmp/mvp_scene.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from world_core.models import WorldState

from world_core import (
    LOC_ANCIENT_CAVE,
    LOC_BLACK_MARKET,
    LOC_BLACKWOOD_FOREST,
    LOC_CHIXIAO_OUTPOST,
    LOC_MISTY_VALLEY,
    LOC_RUINED_TEMPLE,
    LOC_STONE_TOWN,
    LOC_XUANYUE_SECT,
    create_world,
    state_checksum,
)

SCHEMA_VERSION = "unreal-scene-layout.v1"
WORLD_SEED = 42
LAYOUT_PATH = Path(__file__).resolve().parents[1] / "Content" / "Layout" / "mvp_scene.json"

# Canonical output order; the seed world's dict order is not a contract.
LOCATION_ORDER: tuple[str, ...] = (
    LOC_STONE_TOWN,
    LOC_XUANYUE_SECT,
    LOC_BLACKWOOD_FOREST,
    LOC_RUINED_TEMPLE,
    LOC_MISTY_VALLEY,
    LOC_ANCIENT_CAVE,
    LOC_CHIXIAO_OUTPOST,
    LOC_BLACK_MARKET,
)


@dataclass(frozen=True)
class LocationLayout:
    """Hand-authored blockout placement for one authoritative location."""

    xy_cm: tuple[int, int]
    interaction_anchor: str
    anchor_offset_cm: tuple[int, int]
    scene_area: str
    actor_tag: str
    streaming_level: str
    streaming_rule: str


# The eight locations use the stable IDs and display names from ``world_core.worldgen``.
# Only the blockout numbers, anchor names, and Unreal asset paths are authored here.
LOCATION_LAYOUT: dict[str, LocationLayout] = {
    LOC_STONE_TOWN: LocationLayout(
        xy_cm=(0, 0),
        interaction_anchor="town_courtyard",
        anchor_offset_cm=(250, 200),
        scene_area="courtyard",
        actor_tag="LOC_StoneTown",
        streaming_level="/Game/Maps/Streaming/L_StoneTown",
        streaming_rule="always_loaded",
    ),
    LOC_XUANYUE_SECT: LocationLayout(
        xy_cm=(7000, 1200),
        interaction_anchor="sect_gate",
        anchor_offset_cm=(-1100, 0),
        scene_area="sect_gate",
        actor_tag="LOC_XuanyueSect",
        streaming_level="/Game/Maps/Streaming/L_XuanyueSect",
        streaming_rule="distance",
    ),
    LOC_BLACKWOOD_FOREST: LocationLayout(
        xy_cm=(14500, -800),
        interaction_anchor="forest_edge",
        anchor_offset_cm=(-1300, 200),
        scene_area="forest_edge",
        actor_tag="LOC_BlackwoodForest",
        streaming_level="/Game/Maps/Streaming/L_BlackwoodForest",
        streaming_rule="distance",
    ),
    LOC_RUINED_TEMPLE: LocationLayout(
        xy_cm=(20500, 3500),
        interaction_anchor="temple_courtyard",
        anchor_offset_cm=(0, 0),
        scene_area="supporting",
        actor_tag="LOC_RuinedTemple",
        streaming_level="/Game/Maps/Streaming/L_RuinedTemple",
        streaming_rule="distance",
    ),
    LOC_MISTY_VALLEY: LocationLayout(
        xy_cm=(26500, 5800),
        interaction_anchor="valley_trail",
        anchor_offset_cm=(-1200, 0),
        scene_area="supporting",
        actor_tag="LOC_MistyValley",
        streaming_level="/Game/Maps/Streaming/L_MistyValley",
        streaming_rule="distance",
    ),
    LOC_ANCIENT_CAVE: LocationLayout(
        xy_cm=(30800, 8600),
        interaction_anchor="cave_mouth",
        anchor_offset_cm=(-900, 0),
        scene_area="secret_realm_entrance",
        actor_tag="LOC_AncientCave",
        streaming_level="/Game/Maps/Streaming/L_AncientCave",
        streaming_rule="manual",
    ),
    LOC_CHIXIAO_OUTPOST: LocationLayout(
        xy_cm=(17000, -6500),
        interaction_anchor="outpost_gate",
        anchor_offset_cm=(0, 900),
        scene_area="supporting",
        actor_tag="LOC_ChixiaoOutpost",
        streaming_level="/Game/Maps/Streaming/L_ChixiaoOutpost",
        streaming_rule="manual",
    ),
    LOC_BLACK_MARKET: LocationLayout(
        xy_cm=(-3500, -4200),
        interaction_anchor="market_alley",
        anchor_offset_cm=(0, 0),
        scene_area="supporting",
        actor_tag="LOC_BlackMarket",
        streaming_level="/Game/Maps/Streaming/L_BlackMarket",
        streaming_rule="manual",
    ),
}

# Stable per-NPC scatter radius around the location marker, in centimeters.
NPC_SCATTER_MIN_CM = 140.0
NPC_SCATTER_MAX_CM = 400.0


def _npc_local_offset(npc_id: str) -> list[float]:
    """Deterministic local offset derived only from the stable NPC UUID.

    ``hash()`` is intentionally avoided: it is salted per process. BLAKE2b over the UUID
    gives the same angle and radius on every platform.
    """

    digest = hashlib.blake2b(npc_id.encode("utf-8"), digest_size=8).digest()
    angle = int.from_bytes(digest[:4], "big") / 2**32 * math.tau
    span = NPC_SCATTER_MAX_CM - NPC_SCATTER_MIN_CM
    radius = NPC_SCATTER_MIN_CM + int.from_bytes(digest[4:], "big") / 2**32 * span
    return [round(radius * math.cos(angle), 1), round(radius * math.sin(angle), 1)]


def _npc_actor_tag(npc_id: str) -> str:
    """Stable actor tag from the UUID; the authoritative lookup key remains ``npc_id``."""

    return "NPC_" + npc_id.replace("-", "")[:12].upper()


def _location_order(location_id: str) -> int:
    return LOCATION_ORDER.index(location_id)


def _validate(state: WorldState, document: dict[str, Any]) -> None:
    """Fail loudly if the seed world or placement tables drift apart."""

    locations = document["locations"]
    npc_spawns = document["npc_spawns"]

    if len(locations) != 8:
        raise ValueError(f"expected 8 locations, got {len(locations)}")
    if len(npc_spawns) != 30:
        raise ValueError(f"expected 30 NPC spawn records, got {len(npc_spawns)}")

    location_ids = [row["location_id"] for row in locations]
    if len(set(location_ids)) != len(location_ids):
        raise ValueError("duplicate location_id in layout")
    if set(location_ids) != set(state.locations):
        raise ValueError("layout location IDs do not match the seed world")

    npc_ids = [row["npc_id"] for row in npc_spawns]
    if len(set(npc_ids)) != len(npc_ids):
        raise ValueError("duplicate npc_id in layout")
    if set(npc_ids) != set(state.npcs):
        raise ValueError("layout NPC IDs do not match the seed world")

    actor_tags = [row["actor_tag"] for row in npc_spawns]
    if len(set(actor_tags)) != len(actor_tags):
        raise ValueError("duplicate NPC actor tag in layout")

    location_map = document["location_actor_map"]
    if set(location_map) != set(location_ids):
        raise ValueError("location_actor_map must cover every location exactly once")

    for row in locations:
        location_id = row["location_id"]
        for neighbour in row["adjacency"]:
            if neighbour not in state.locations:
                raise ValueError(f"{location_id} lists unknown neighbour {neighbour}")
            if location_id not in state.locations[neighbour].adjacency:
                raise ValueError(f"asymmetric adjacency: {location_id} -> {neighbour}")
        anchor = row["interaction_anchor"]
        if not anchor["anchor_id"] or len(anchor["coordinates_xy_cm"]) != 2:
            raise ValueError(f"{location_id} has an incomplete interaction anchor")

    for row in npc_spawns:
        if row["location_id"] not in state.locations:
            raise ValueError(f"NPC {row['npc_id']} spawns in unknown location")
        if len(row["local_offset_xy_cm"]) != 2:
            raise ValueError(f"NPC {row['npc_id']} has an invalid local offset")


def build_layout(state: WorldState | None = None) -> dict[str, Any]:
    """Return the complete layout document for the seed world."""

    state = create_world(WORLD_SEED) if state is None else state
    if state.world_seed != WORLD_SEED:
        raise ValueError(f"layout requires seed {WORLD_SEED}, got {state.world_seed}")
    if set(state.locations) != set(LOCATION_ORDER):
        raise ValueError("seed world locations differ from the stable layout table")

    locations: list[dict[str, Any]] = []
    location_actor_map: dict[str, dict[str, Any]] = {}

    for location_id in LOCATION_ORDER:
        location = state.locations[location_id]
        placement = LOCATION_LAYOUT[location_id]
        x, y = placement.xy_cm
        anchor_dx, anchor_dy = placement.anchor_offset_cm

        adjacent = sorted(location.adjacency, key=_location_order)
        locations.append(
            {
                "location_id": location_id,
                "display_name": location.name,
                "kind": location.kind,
                "faction_id": location.faction_id,
                "aura_multiplier": location.aura_multiplier,
                "coordinates_xy_cm": [x, y],
                "adjacency": adjacent,
                "interaction_anchor": {
                    "anchor_id": placement.interaction_anchor,
                    "local_offset_xy_cm": [anchor_dx, anchor_dy],
                    "coordinates_xy_cm": [x + anchor_dx, y + anchor_dy],
                },
                "scene_area": placement.scene_area,
                "actor_tag": placement.actor_tag,
            }
        )
        location_actor_map[location_id] = {
            "actor_tag": placement.actor_tag,
            "streaming_level": placement.streaming_level,
            "streaming_rule": placement.streaming_rule,
        }

    def spawn_order(key: str) -> tuple[int, str]:
        return (_location_order(state.npcs[key].location_id), key)

    npc_spawns: list[dict[str, Any]] = []
    for npc_id in sorted(state.npcs, key=spawn_order):
        npc = state.npcs[npc_id]
        placement = LOCATION_LAYOUT[npc.location_id]
        local_x, local_y = _npc_local_offset(npc.npc_id)
        base_x, base_y = placement.xy_cm
        npc_spawns.append(
            {
                "npc_id": npc.npc_id,
                "name": npc.name,
                "canonical_role": npc.canonical_role,
                "location_id": npc.location_id,
                "local_offset_xy_cm": [local_x, local_y],
                "coordinates_xy_cm": [round(base_x + local_x, 1), round(base_y + local_y, 1)],
                "actor_tag": _npc_actor_tag(npc.npc_id),
                "is_player": npc.npc_id == state.player_id,
            }
        )

    player = state.npcs[state.player_id]
    player_row = next(row for row in npc_spawns if row["npc_id"] == state.player_id)
    player_spawn = {
        "npc_id": player.npc_id,
        "name": player.name,
        "location_id": player.location_id,
        "local_offset_xy_cm": player_row["local_offset_xy_cm"],
        "coordinates_xy_cm": player_row["coordinates_xy_cm"],
        "actor_tag": player_row["actor_tag"],
    }

    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generator": "clients/unreal/tools/export_scene_layout.py",
        "source": {
            "world_id": state.world_id,
            "world_seed": state.world_seed,
            "player_id": state.player_id,
            "tick": state.tick,
            "state_version": state.state_version,
            "sim_version": state.sim_version,
            "ruleset_version": state.ruleset_version,
            "source_checksum": state_checksum(state),
        },
        "counts": {
            "locations": len(locations),
            "npc_spawns": len(npc_spawns),
            "player_spawns": 1,
        },
        "coordinate_system": {
            "units": "centimeters",
            "plane": "XY",
            "x_axis": "east",
            "y_axis": "north",
            "z_axis": "up",
        },
        "unreal": {
            "npc_actor_class": "/Script/UnwrittenDao.NpcViewActor",
            "location_marker_actor_class": "/Script/Engine.TargetPoint",
        },
        "locations": locations,
        "npc_spawns": npc_spawns,
        "player_spawn": player_spawn,
        "location_actor_map": location_actor_map,
    }

    _validate(state, document)
    return document


def serialize_layout(document: dict[str, Any]) -> str:
    """Canonical UTF-8 JSON text with a trailing newline."""

    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def write_layout(path: Path = LAYOUT_PATH, document: dict[str, Any] | None = None) -> Path:
    """Write the layout document and return its path."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = serialize_layout(build_layout() if document is None else document)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=LAYOUT_PATH,
        help=f"output path (default: {LAYOUT_PATH})",
    )
    args = parser.parse_args(argv)

    document = build_layout()
    path = write_layout(args.output, document)
    source = document["source"]
    print(f"wrote {path}")
    print(
        f"locations={document['counts']['locations']} "
        f"npc_spawns={document['counts']['npc_spawns']} "
        f"seed={source['world_seed']} checksum={source['source_checksum']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())