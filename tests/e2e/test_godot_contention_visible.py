"""A staged three-NPC contention whose consequences the Godot client can see.

Honesty boundary: the world is staged (map hand-off, positions and one guard
goal) exactly like ``test_contention_encounter.py``; this test proves the
*client visibility* half - real Godot transport -> real Python policies/core ->
authoritative events read back by the client. It is not evidence that the same
encounter is reachable from the shipped seed, and it does not claim rendering,
PostgreSQL or live-model verification.

The HTTP service is an in-memory harness; the Godot binary is optional
(``GODOT_BIN`` or ``godot``/``godot4`` on PATH).
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from world_core.ruleset import RULESET
from world_server.agent_policy import policy_for

from agent_runtime import build_observation
from world_core import (
    ITEM_MAP_FRAGMENT,
    LOC_ANCIENT_CAVE,
    LOC_BLACKWOOD_FOREST,
    LOC_MISTY_VALLEY,
    LOC_RUINED_TEMPLE,
    PLAYER_ID,
    PROTAGONIST_ID,
    REALM_ANCIENT_CAVE,
    Goal,
    WorldCommand,
    WorldEvent,
    apply_command,
    create_world,
    make_command,
    npc_id,
    snapshot,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROJECT = ROOT / "clients" / "godot"
RIVAL_ID = npc_id("pei_lie")
ALCHEMIST_ID = npc_id("su_zhi")


def _submit(state, actor_id: str | None, command_type: str, arguments: dict) -> None:
    apply_command(state, make_command(state, actor_id, command_type, arguments, source="test"))


def _stage(state) -> None:
    """Same deterministic staging as the headless contention fixture."""
    protagonist = state.npcs[PROTAGONIST_ID]
    for target in (LOC_BLACKWOOD_FOREST, LOC_RUINED_TEMPLE):
        _submit(state, protagonist.npc_id, "move", {"to_location_id": target})
    _submit(
        state,
        protagonist.npc_id,
        "transfer_item",
        {
            "item_id": ITEM_MAP_FRAGMENT,
            "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
            "to": {"kind": "npc", "id": protagonist.npc_id},
        },
    )
    _submit(state, protagonist.npc_id, "move", {"to_location_id": LOC_MISTY_VALLEY})
    _submit(
        state,
        protagonist.npc_id,
        "investigate",
        {"target_location_id": LOC_MISTY_VALLEY, "focus": "secret_realm"},
    )
    _submit(state, protagonist.npc_id, "enter_secret_realm", {"realm_id": REALM_ANCIENT_CAVE})

    protagonist.stage = RULESET.max_stage(1)
    protagonist.qi = RULESET.cap_qi(1)
    for npc in (state.npcs[RIVAL_ID], state.npcs[ALCHEMIST_ID]):
        npc.location_id = LOC_ANCIENT_CAVE
        if LOC_ANCIENT_CAVE not in npc.known_locations:
            npc.known_locations.append(LOC_ANCIENT_CAVE)
    state.npcs[ALCHEMIST_ID].goals.append(
        Goal(
            goal_id="goal_encounter_guard_disciple",
            kind="defeat_rival",
            priority=0.9,
            params={"target": RIVAL_ID},
            created_tick=state.tick,
        )
    )


def _godot_binary() -> str | None:
    return os.environ.get("GODOT_BIN") or shutil.which("godot") or shutil.which("godot4")


def test_godot_client_sees_the_contention_events(tmp_path: pathlib.Path) -> None:
    godot = _godot_binary()
    if not godot:
        pytest.skip("Godot not installed; set GODOT_BIN to enable the client visibility test")

    monkeypatch_provider = os.environ.get("AGENT_PROVIDER")
    os.environ["AGENT_PROVIDER"] = "utility"
    state = create_world(42)
    _stage(state)
    lock = threading.Lock()
    events: list[WorldEvent] = []
    errors: list[str] = []
    decision_count = 0

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status: int, data: Any) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            with lock:
                if parsed.path == "/v1/world/snapshot":
                    self.respond(200, snapshot(state))
                    return
                if parsed.path == "/v1/world/events":
                    query = parse_qs(parsed.query)
                    after = int(query.get("after", ["0"])[0])
                    limit = int(query.get("limit", ["200"])[0])
                    rows = [
                        event.model_dump(mode="json")
                        for event in events
                        if event.event_id > after
                    ][:limit]
                    self.respond(
                        200,
                        {
                            "events": rows,
                            "last_event_id": rows[-1]["event_id"] if rows else after,
                        },
                    )
                    return
                errors.append("unexpected GET " + self.path)
                self.respond(404, {"code": "not_found"})

        def do_POST(self) -> None:
            nonlocal decision_count
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            with lock:
                try:
                    if self.path.startswith("/v1/agents/") and self.path.endswith("/decision"):
                        npc_id_value = self.path.split("/")[3]
                        npc = state.npcs[npc_id_value]
                        if not npc.alive or npc.active_action is not None:
                            self.respond(409, {"code": "actor_busy"})
                            return
                        decision_count += 1
                        proposal = policy_for(npc).policy.decide(
                            build_observation(state, npc_id_value)
                        )
                        self.respond(200, proposal.model_dump(mode="json"))
                        return
                    if self.path == "/v1/commands":
                        command = WorldCommand.model_validate_json(body)
                        result = apply_command(state, command)
                        events.extend(result.events)
                        self.respond(200, result.model_dump(mode="json"))
                        return
                    errors.append("unexpected POST " + self.path)
                    self.respond(404, {"code": "not_found"})
                except Exception as exc:
                    errors.append(type(exc).__name__ + ": " + str(exc))
                    self.respond(500, {"code": "harness_failure"})

        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    environment = dict(os.environ)
    environment["UNWRITTEN_DAO_AGENT_TEST_URL"] = f"http://127.0.0.1:{server.server_port}"
    try:
        imported = subprocess.run(
            [
                godot,
                "--headless",
                "--path",
                str(PROJECT),
                "--editor",
                "--import",
                "--quit",
                "--log-file",
                str(tmp_path / "import.log"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            env=environment,
        )
        assert imported.returncode == 0, imported.stdout + imported.stderr
        result = subprocess.run(
            [
                godot,
                "--headless",
                "--path",
                str(PROJECT),
                "--script",
                "res://tests/contention_visible.gd",
                "--log-file",
                str(tmp_path / "run.log"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            env=environment,
        )
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        if monkeypatch_provider is None:
            os.environ.pop("AGENT_PROVIDER", None)
        else:
            os.environ["AGENT_PROVIDER"] = monkeypatch_provider

    output = result.stdout + result.stderr
    assert not errors, errors
    assert result.returncode == 0, output
    assert "CONTENTION SEEN" in output, output
    assert f"tick={state.tick}" in output
    assert "OPPORTUNITY_CLAIMED" in output and "COMBAT_RESOLVED" in output
    assert decision_count > 0
    visible = {event.type for event in events}
    assert {"OPPORTUNITY_CLAIMED", "COMBAT_RESOLVED"} <= visible
    assert all(PLAYER_ID not in event.actor_ids for event in events)
