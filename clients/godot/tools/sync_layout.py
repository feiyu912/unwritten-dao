"""Copy and verify the UE5 blockout layout for the Godot client.

The deterministic layout JSON is owned by the Unreal client tooling at
``clients/unreal/Content/Layout/mvp_scene.json``. This tool copies it verbatim into
``clients/godot/data/mvp_scene.json`` and fails loudly if the source drifts from the
locked 8-location / 30-NPC seed layout, if an NPC or location ID is duplicated, if
adjacency is asymmetric, or if the recorded world source checksum is malformed.

Standard library only. It never writes to the Unreal directory.

Usage (from the repository root)::

    uv run python clients/godot/tools/sync_layout.py
    uv run python clients/godot/tools/sync_layout.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
GODOT_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[3]
SOURCE_PATH = REPO_ROOT / "clients" / "unreal" / "Content" / "Layout" / "mvp_scene.json"
DEST_PATH = GODOT_ROOT / "layout" / "mvp_scene.json"
MANIFEST_PATH = GODOT_ROOT / "layout" / "mvp_scene.manifest.json"

EXPECTED_LOCATIONS = 8
EXPECTED_NPC_SPAWNS = 30
CHECKSUM_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
LAYOUT_SCHEMA = "unreal-scene-layout.v1"


class SyncError(RuntimeError):
    """The source layout violates a locked expectation."""


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_source(path: Path = SOURCE_PATH) -> tuple[dict[str, Any], bytes]:
    if not path.is_file():
        raise SyncError(f"layout source not found: {path}")
    raw = path.read_bytes()
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SyncError(f"layout source is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise SyncError("layout source must be a JSON object")
    return document, raw


def validate_layout(document: dict[str, Any]) -> dict[str, Any]:
    """Validate locked counts, stable unique IDs, symmetry, and the source checksum."""

    if document.get("schema_version") != LAYOUT_SCHEMA:
        raise SyncError(f"expected schema_version {LAYOUT_SCHEMA!r}")

    source = document.get("source")
    if not isinstance(source, dict):
        raise SyncError("layout source block is missing")
    checksum = source.get("source_checksum")
    if not isinstance(checksum, str) or not CHECKSUM_RE.fullmatch(checksum):
        raise SyncError("source.source_checksum must be sha256:<64 lowercase hex>")

    counts = document.get("counts")
    if not isinstance(counts, dict):
        raise SyncError("layout counts block is missing")

    locations = document.get("locations")
    npc_spawns = document.get("npc_spawns")
    if not isinstance(locations, list) or not isinstance(npc_spawns, list):
        raise SyncError("locations and npc_spawns must be arrays")
    if len(locations) != EXPECTED_LOCATIONS:
        raise SyncError(f"expected {EXPECTED_LOCATIONS} locations, got {len(locations)}")
    if len(npc_spawns) != EXPECTED_NPC_SPAWNS:
        raise SyncError(f"expected {EXPECTED_NPC_SPAWNS} NPC spawns, got {len(npc_spawns)}")
    if counts.get("locations") != len(locations) or counts.get("npc_spawns") != len(npc_spawns):
        raise SyncError("counts block disagrees with the layout arrays")

    location_ids: list[str] = []
    for row in locations:
        if not isinstance(row, dict) or not isinstance(row.get("location_id"), str):
            raise SyncError("every location needs a string location_id")
        location_ids.append(row["location_id"])
        adjacency = row.get("adjacency")
        if not isinstance(adjacency, list) or not all(isinstance(n, str) for n in adjacency):
            raise SyncError(f"{row['location_id']} has an invalid adjacency list")
        if not isinstance(row.get("coordinates_xy_cm"), list) or len(row["coordinates_xy_cm"]) != 2:
            raise SyncError(f"{row['location_id']} has invalid coordinates")
        anchor = row.get("interaction_anchor")
        if not isinstance(anchor, dict) or not anchor.get("anchor_id"):
            raise SyncError(f"{row['location_id']} is missing its interaction anchor")
    if len(set(location_ids)) != EXPECTED_LOCATIONS:
        raise SyncError("duplicate location_id in layout")

    adjacency = {
        row["location_id"]: list(row["adjacency"]) for row in locations if isinstance(row, dict)
    }
    for location_id, neighbours in adjacency.items():
        for neighbour in neighbours:
            if neighbour not in adjacency:
                raise SyncError(f"{location_id} lists unknown neighbour {neighbour}")
            if location_id not in adjacency[neighbour]:
                raise SyncError(f"asymmetric adjacency: {location_id} -> {neighbour}")

    npc_ids: list[str] = []
    for row in npc_spawns:
        if not isinstance(row, dict) or not isinstance(row.get("npc_id"), str):
            raise SyncError("every NPC spawn needs a string npc_id")
        npc_ids.append(row["npc_id"])
        if row.get("location_id") not in adjacency:
            raise SyncError(f"NPC {row['npc_id']} spawns in an unknown location")
        offset = row.get("local_offset_xy_cm")
        if not isinstance(offset, list) or len(offset) != 2:
            raise SyncError(f"NPC {row['npc_id']} has an invalid local offset")
    if len(set(npc_ids)) != EXPECTED_NPC_SPAWNS:
        raise SyncError("duplicate npc_id in layout")

    player = document.get("player_spawn")
    if not isinstance(player, dict) or player.get("npc_id") not in npc_ids:
        raise SyncError("player_spawn.npc_id must be one of the 30 NPC IDs")

    return {
        "schema_version": LAYOUT_SCHEMA,
        "source_path": SOURCE_PATH.relative_to(REPO_ROOT).as_posix(),
        "source_file_sha256": file_sha256(SOURCE_PATH.read_bytes()),
        "world_source_checksum": checksum,
        "world_id": source.get("world_id"),
        "world_seed": source.get("world_seed"),
        "locations": len(location_ids),
        "npc_spawns": len(npc_ids),
        "location_ids": sorted(location_ids),
        "npc_ids_sha256": hashlib.sha256(
            "\n".join(sorted(npc_ids)).encode("utf-8")
        ).hexdigest(),
    }


def manifest_for(document: dict[str, Any], raw: bytes) -> dict[str, Any]:
    summary = validate_layout(document)
    summary["source_file_sha256"] = file_sha256(raw)
    summary["copy_file_sha256"] = file_sha256(raw)
    return summary


def verify_destination(document: dict[str, Any], raw: bytes) -> None:
    manifest = manifest_for(document, raw)
    if not DEST_PATH.is_file():
        raise SyncError(f"copy is missing: {DEST_PATH}")
    if DEST_PATH.read_bytes() != raw:
        raise SyncError("copy is stale; rerun sync_layout.py")
    if MANIFEST_PATH.is_file():
        recorded = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if recorded.get("copy_file_sha256") != manifest["copy_file_sha256"]:
            raise SyncError("manifest checksum does not match the copied layout")
        if recorded.get("world_source_checksum") != manifest["world_source_checksum"]:
            raise SyncError("recorded world source checksum disagrees with the layout")


def sync(check_only: bool = False) -> dict[str, Any]:
    document, raw = load_source()
    manifest = manifest_for(document, raw)

    if check_only:
        verify_destination(document, raw)
        print(f"layout OK: {manifest['locations']} locations, {manifest['npc_spawns']} NPCs")
        print(f"world source checksum: {manifest['world_source_checksum']}")
        return manifest

    if DEST_PATH.is_file() and DEST_PATH.read_bytes() == raw and MANIFEST_PATH.is_file():
        verify_destination(document, raw)
        print(f"layout already current: {DEST_PATH.relative_to(REPO_ROOT)}")
        return manifest

    DEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = DEST_PATH.with_suffix(".json.tmp")
    temp_path.write_bytes(raw)
    if temp_path.read_bytes() != raw:
        temp_path.unlink(missing_ok=True)
        raise SyncError("byte comparison failed while staging the copy")
    temp_path.replace(DEST_PATH)
    if file_sha256(DEST_PATH.read_bytes()) != manifest["source_file_sha256"]:
        raise SyncError("copy checksum differs from the source file checksum")

    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    verify_destination(document, raw)
    print(
        f"copied {SOURCE_PATH.relative_to(REPO_ROOT)} -> {DEST_PATH.relative_to(REPO_ROOT)}"
    )
    print(f"locations: {manifest['locations']}, NPC spawns: {manifest['npc_spawns']}")
    print(f"source file sha256: {manifest['source_file_sha256']}")
    print(f"world source checksum: {manifest['world_source_checksum']}")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="verify the existing copy without writing"
    )
    args = parser.parse_args(argv)
    try:
        sync(check_only=args.check)
    except SyncError as exc:
        print(f"sync_layout: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())