"""Tests for the deterministic UE5 scene layout export.

No database, no Unreal Engine: these tests only compare the exporter against the seed
world from ``world_core`` and verify reproducibility of the JSON document.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest
from export_scene_layout import (
    LAYOUT_PATH,
    SCHEMA_VERSION,
    WORLD_SEED,
    build_layout,
    serialize_layout,
    write_layout,
)

from world_core import create_world, state_checksum


@pytest.fixture(scope="module")
def layout() -> dict[str, Any]:
    return build_layout()


@pytest.fixture(scope="module")
def seed_state() -> Any:
    return create_world(WORLD_SEED)


def test_schema_and_source_checksum(layout: dict[str, Any], seed_state: Any) -> None:
    assert layout["schema_version"] == SCHEMA_VERSION
    source = layout["source"]
    assert source["world_seed"] == WORLD_SEED
    assert source["world_id"] == seed_state.world_id
    assert source["player_id"] == seed_state.player_id
    assert source["tick"] == 0
    assert source["source_checksum"] == state_checksum(seed_state)
    assert source["source_checksum"].startswith("sha256:")
    assert layout["counts"] == {"locations": 8, "npc_spawns": 30, "player_spawns": 1}


def test_eight_stable_locations(layout: dict[str, Any], seed_state: Any) -> None:
    locations = layout["locations"]
    assert len(locations) == 8

    ids = [row["location_id"] for row in locations]
    assert len(set(ids)) == 8
    assert set(ids) == set(seed_state.locations)

    coordinates = {tuple(row["coordinates_xy_cm"]) for row in locations}
    assert len(coordinates) == 8

    for row in locations:
        seed_location = seed_state.locations[row["location_id"]]
        assert row["display_name"] == seed_location.name
        assert row["kind"] == seed_location.kind
        assert row["faction_id"] == seed_location.faction_id
        assert row["aura_multiplier"] == seed_location.aura_multiplier
        assert row["actor_tag"].startswith("LOC_")
        assert row["interaction_anchor"]["anchor_id"]
        assert all(math.isfinite(value) for value in row["coordinates_xy_cm"])


def test_thirty_unique_npc_spawns(layout: dict[str, Any], seed_state: Any) -> None:
    spawns = layout["npc_spawns"]
    assert len(spawns) == 30

    ids = [row["npc_id"] for row in spawns]
    assert len(set(ids)) == 30
    assert set(ids) == set(seed_state.npcs)

    actor_tags = [row["actor_tag"] for row in spawns]
    assert len(set(actor_tags)) == 30

    for row in spawns:
        seed_npc = seed_state.npcs[row["npc_id"]]
        assert row["name"] == seed_npc.name
        assert row["canonical_role"] == seed_npc.canonical_role
        assert row["location_id"] == seed_npc.location_id
        assert len(row["local_offset_xy_cm"]) == 2
        assert all(math.isfinite(value) for value in row["local_offset_xy_cm"])

    player_rows = [row for row in spawns if row["is_player"]]
    assert len(player_rows) == 1
    player = seed_state.npcs[seed_state.player_id]
    assert player_rows[0]["npc_id"] == seed_state.player_id
    assert layout["player_spawn"]["npc_id"] == seed_state.player_id
    assert layout["player_spawn"]["location_id"] == player.location_id


def test_all_npc_locations_exist(layout: dict[str, Any]) -> None:
    location_ids = {row["location_id"] for row in layout["locations"]}
    for row in layout["npc_spawns"]:
        assert row["location_id"] in location_ids


def test_adjacency_is_symmetric_and_matches_seed(
    layout: dict[str, Any], seed_state: Any
) -> None:
    adjacency = {row["location_id"]: row["adjacency"] for row in layout["locations"]}
    for location_id, neighbours in adjacency.items():
        assert neighbours == seed_state.locations[location_id].adjacency
        for neighbour in neighbours:
            assert location_id in adjacency[neighbour]
            assert seed_state.locations[neighbour].location_id == neighbour


def test_location_actor_map_covers_every_location(layout: dict[str, Any]) -> None:
    location_ids = {row["location_id"] for row in layout["locations"]}
    actor_map = layout["location_actor_map"]
    assert set(actor_map) == location_ids
    for entry in actor_map.values():
        assert entry["actor_tag"].startswith("LOC_")
        assert entry["streaming_level"].startswith("/Game/Maps/Streaming/")
        assert entry["streaming_rule"] in {"always_loaded", "distance", "manual"}


def test_document_is_json_serializable(layout: dict[str, Any]) -> None:
    text = serialize_layout(layout)
    assert text.endswith("\n")
    assert json.loads(text) == layout


def test_two_exports_are_byte_identical(tmp_path: Path) -> None:
    first = build_layout()
    second = build_layout()
    assert first == second
    assert first["source"]["source_checksum"] == second["source"]["source_checksum"]
    assert serialize_layout(first) == serialize_layout(second)

    first_path = write_layout(tmp_path / "first.json", first)
    second_path = write_layout(tmp_path / "second.json", second)
    assert first_path.read_bytes() == second_path.read_bytes()


def test_checked_in_layout_matches_generator(layout: dict[str, Any]) -> None:
    assert LAYOUT_PATH.is_file(), f"run the exporter first: {LAYOUT_PATH}"
    on_disk = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
    assert on_disk == layout