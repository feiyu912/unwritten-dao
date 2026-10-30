"""Actual Godot scheduler HTTP -> real policies -> core commands -> replay.

The HTTP service is an in-memory harness; PostgreSQL and real model quality are
outside this test. Set GODOT_BIN to enable it when Godot is not on PATH.
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

import pytest
from world_server.agent_policy import policy_for

from agent_runtime import build_observation
from world_core import (
    CommandRejected,
    WorldCommand,
    apply_command,
    create_world,
    restore_snapshot,
    snapshot,
    state_checksum,
    validate_state,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROJECT = ROOT / "clients" / "godot"


def test_godot_agent_day_http_and_deterministic_replay(monkeypatch, tmp_path) -> None:
    godot = os.environ.get("GODOT_BIN") or shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot not installed; set GODOT_BIN to enable scheduler HTTP test")
    monkeypatch.setenv("AGENT_PROVIDER", "utility")
    state = create_world(42)
    initial = snapshot(state)
    lock = threading.Lock()
    commands: list[WorldCommand] = []
    decisions: list[str] = []
    decision_bodies: list[bytes] = []
    event_types: list[str] = []
    errors: list[str] = []
    snapshot_versions: list[int] = []

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status: int, data: Any) -> None:
            output = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)

        def do_GET(self) -> None:
            with lock:
                if self.path != "/v1/world/snapshot":
                    errors.append("unexpected GET " + self.path)
                    self.respond(404, {"code": "not_found"})
                    return
                snapshot_versions.append(state.state_version)
                self.respond(200, snapshot(state))

        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            with lock:
                try:
                    if self.path.startswith("/v1/agents/") and self.path.endswith("/decision"):
                        npc_id = self.path.split("/")[3]
                        npc = state.npcs[npc_id]
                        if not npc.alive or npc.active_action is not None:
                            self.respond(409, {"code": "actor_busy"})
                            return
                        decisions.append(npc_id)
                        decision_bodies.append(body)
                        proposal = policy_for(npc).policy.decide(build_observation(state, npc_id))
                        self.respond(200, proposal.model_dump(mode="json"))
                    elif self.path == "/v1/commands":
                        command = WorldCommand.model_validate_json(body)
                        result = apply_command(state, command)
                        commands.append(command)
                        event_types.extend(event.type for event in result.events)
                        self.respond(200, result.model_dump(mode="json"))
                    else:
                        errors.append("unexpected POST " + self.path)
                        self.respond(404, {"code": "not_found"})
                except CommandRejected as exc:
                    errors.append(exc.code)
                    status = 409 if exc.code == "stale_state_version" else 422
                    self.respond(status, {"code": exc.code, "message": exc.message})
                except Exception as exc:
                    errors.append(type(exc).__name__)
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
            timeout=45,
            env=environment,
        )
        assert imported.returncode == 0, imported.stdout + imported.stderr
        assert "SCRIPT ERROR" not in imported.stdout + imported.stderr
        result = subprocess.run(
            [
                godot,
                "--headless",
                "--path",
                str(PROJECT),
                "--script",
                "res://tests/agent_day_http.gd",
                "--log-file",
                str(tmp_path / "day.log"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            env=environment,
        )
        output = result.stdout + result.stderr
        assert result.returncode == 0, output + repr(errors)
        assert "AGENT HTTP day passed tick=1" in output, output
        assert f"checksum={state_checksum(state)}" in output, output
        assert "SCRIPT ERROR" not in output, output
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    assert not errors
    assert state.tick == 1
    assert decisions == sorted(set(decisions))
    assert state.player_id not in decisions
    assert decision_bodies and all(body == b"" for body in decision_bodies)
    assert commands and commands[-1].type == "advance_time"
    assert commands[-1].source == "system" and commands[-1].actor_id is None
    assert [command.actor_id for command in commands[:-1]] == decisions
    assert all(command.source == "agent" for command in commands[:-1])
    assert snapshot_versions == list(range(len(commands) + 1))
    assert event_types and any(command.type != "wait" for command in commands[:-1])
    assert validate_state(state) == []
    replay = restore_snapshot(initial)
    for command in commands:
        apply_command(replay, command)
    assert state_checksum(replay) == state_checksum(state)
