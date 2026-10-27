#!/usr/bin/env python3
"""Static checks for the Godot slice; no engine required.

Verifies project/scene references, required client functions, API endpoints,
balanced GDScript delimiters, and that the client contains no local authority
logic. This is not a substitute for opening the project in Godot.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROJECT = ROOT / "project.godot"
SCENE = ROOT / "scenes" / "main.tscn"
LAYOUT = ROOT / "layout" / "mvp_scene.json"

REQUIRED = {
    "scripts/world_client.gd": [
        "fetch_snapshot", "fetch_events", "send_command", "send_dialogue",
        "_on_request_completed",
    ],
    "scripts/main.gd": [
        "_take", "_investigate", "_enter_realm", "_claim", "_talk", "_next_day", "_resync",
    ],
    "scripts/npc_view.gd": ["setup", "apply_snapshot"],
}
ENDPOINTS = ["/v1/world/snapshot", "/v1/world/events", "/v1/commands", "/v1/dialogue"]
FORBIDDEN = ["world_core", "apply_command(state", "calculate_damage", "resolve_combat"]


def _scene_nodes(text: str) -> set[str]:
    nodes: set[str] = set()
    for match in re.finditer(r'\[node name="([^"]+)" type="[^"]+" parent="([^"]+)"\]', text):
        name, parent = match.groups()
        nodes.add(name if parent == "." else f"{parent}/{name}")
    return nodes


def _script_paths(text: str) -> list[str]:
    return re.findall(r'\[ext_resource type="Script" path="res://([^"]+)"', text)


def check() -> list[str]:
    problems: list[str] = []
    project = PROJECT.read_text(encoding="utf-8")
    if 'run/main_scene="res://scenes/main.tscn"' not in project:
        problems.append("project.godot does not point at scenes/main.tscn")
    if '"4.7"' not in project:
        problems.append("project.godot does not declare Godot 4.7")
    if not SCENE.is_file():
        return [*problems, "scenes/main.tscn missing"]
    scene = SCENE.read_text(encoding="utf-8")
    nodes = _scene_nodes(scene)
    for script in _script_paths(scene):
        if not (ROOT / script).is_file():
            problems.append(f"scene references missing script {script}")

    main_text = (ROOT / "scripts" / "main.gd").read_text(encoding="utf-8")
    for node_path in sorted(set(re.findall(r"\$([A-Za-z0-9_/]+)", main_text))):
        if node_path not in nodes:
            problems.append(f"main.gd references missing node ${node_path}")

    for relative, functions in REQUIRED.items():
        path = ROOT / relative
        if not path.is_file():
            problems.append(f"missing script {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        for function in functions:
            if f"func {function}" not in text:
                problems.append(f"{relative} missing func {function}")
        for opener, closer in (("{", "}"), ("(", ")"), ("[", "]")):
            if text.count(opener) != text.count(closer):
                problems.append(f"{relative} unbalanced {opener}{closer}")
        for forbidden in FORBIDDEN:
            if forbidden in text:
                problems.append(f"{relative} contains local authority logic: {forbidden}")

    client = (ROOT / "scripts" / "world_client.gd").read_text(encoding="utf-8")
    if "signal resync_required" not in client:
        problems.append("world_client.gd missing signal resync_required")
    for endpoint in ENDPOINTS:
        if endpoint not in client:
            problems.append(f"world_client.gd missing endpoint {endpoint}")

    layout = json.loads(LAYOUT.read_text(encoding="utf-8"))
    if len(layout.get("locations", [])) != 8:
        problems.append("layout must contain 8 locations")
    if len(layout.get("npc_spawns", [])) != 30:
        problems.append("layout must contain 30 NPC spawns")
    return problems


def main() -> int:
    problems = check()
    if problems:
        print("\n".join(f"FAIL: {problem}" for problem in problems))
        return 1
    print("OK: Godot project references, scripts, endpoints, and layout are consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())