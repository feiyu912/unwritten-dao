from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
GODOT = ROOT / "clients" / "godot"


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, script, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_layout_sync_is_clean() -> None:
    result = _run("clients/godot/tools/sync_layout.py", "--check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_static_gdscript_checks() -> None:
    result = _run("clients/godot/tools/check_gdscript.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_project_and_scene_files_exist() -> None:
    assert (GODOT / "project.godot").is_file()
    scene = (GODOT / "scenes" / "main.tscn").read_text(encoding="utf-8")
    for script in ("scripts/main.gd", "scripts/world_client.gd"):
        assert (GODOT / script).is_file()
        assert script in scene or script.endswith("world_client.gd")
    assert (GODOT / "scripts" / "npc_view.gd").is_file()


def test_layout_invariants() -> None:
    layout = json.loads((GODOT / "layout" / "mvp_scene.json").read_text(encoding="utf-8"))
    assert len(layout["locations"]) == 8
    assert len(layout["npc_spawns"]) == 30
    npc_ids = [spawn["npc_id"] for spawn in layout["npc_spawns"]]
    assert len(set(npc_ids)) == 30
    locations = {location["location_id"]: location for location in layout["locations"]}
    for location in locations.values():
        for adjacent in location["adjacency"]:
            assert adjacent in locations
            assert location["location_id"] in locations[adjacent]["adjacency"]
    assert layout["player_spawn"]["npc_id"] in set(npc_ids)
    assert layout["source"]["source_checksum"].startswith("sha256:")
