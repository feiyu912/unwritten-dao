"""Headless in-memory mock of the Unwritten Dao world server.

Serves the small slice of the /v1 API that the UE5 client needs for local
integration work: health, snapshot, event polling, and command submission.
Stdlib only; no database. Not a source of world truth for anything real.

Usage:
    python mock_world_server.py [host] [port]
"""

from __future__ import annotations

import json
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

SNAPSHOT_SCHEMA_VERSION = "world-snapshot.v1"
EVENT_SCHEMA_VERSION = "world-event.v1"
COMMAND_SCHEMA_VERSION = "world-command.v1"
SIM_VERSION = "0.1.0"
RULESET_VERSION = "1.0.0"
WORLD_SEED = 42
ZERO_CHECKSUM = "sha256:" + "0" * 64
MAX_EVENTS = 200


class WorldMock:
    """In-memory world state with contract-compatible JSON responses."""

    def __init__(self) -> None:
        self.world_id = str(uuid.uuid4())
        self.tick = 0
        self.state_version = 1
        self.last_event_id = 0
        self.npcs = [
            {"npc_id": str(uuid.uuid4()), "name": "Elder Yun", "hp": 100, "dead": False},
            {"npc_id": str(uuid.uuid4()), "name": "Sect Disciple Lan", "hp": 80, "dead": False},
        ]
        self.events: list[dict[str, Any]] = []
        self.commands: dict[str, dict[str, Any]] = {}

    # -- reads -------------------------------------------------------------

    def health(self) -> tuple[int, dict[str, Any]]:
        return 200, {"status": "ok", "world_loaded": True}

    def snapshot(self) -> tuple[int, dict[str, Any]]:
        body = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "world_id": self.world_id,
            "tick": self.tick,
            "last_event_id": self.last_event_id,
            "state_version": self.state_version,
            "world_seed": WORLD_SEED,
            "sim_version": SIM_VERSION,
            "ruleset_version": RULESET_VERSION,
            "checksum": ZERO_CHECKSUM,
            "state": {},
        }
        return 200, body

    def list_events(self, after: int, limit: int) -> tuple[int, dict[str, Any]]:
        selected = [
            event
            for event in sorted(self.events, key=lambda e: e["event_id"])
            if event["event_id"] > after
        ][: max(1, min(limit, MAX_EVENTS))]
        return 200, {"events": selected}

    # -- writes ------------------------------------------------------------

    def submit_command(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        idempotency_key = payload.get("idempotency_key")
        if idempotency_key in self.commands:
            return 200, self.commands[idempotency_key]

        if not isinstance(payload.get("world_id"), str) or not payload["world_id"]:
            return 400, {"code": "invalid_command", "message": "world_id must be a string"}
        if payload.get("schema_version") != COMMAND_SCHEMA_VERSION:
            return 400, {
                "code": "invalid_command",
                "message": f"schema_version must be {COMMAND_SCHEMA_VERSION}",
            }
        if not isinstance(payload.get("idempotency_key"), str) or not payload["idempotency_key"]:
            return 400, {"code": "invalid_command", "message": "idempotency_key must be a string"}

        expected = payload.get("expected_state_version")
        if expected != self.state_version:
            return 409, {
                "code": "stale_state_version",
                "message": "expected_state_version does not match current state",
                "current_state_version": self.state_version,
            }

        body = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
        ticks = body.get("ticks") if payload.get("type") == "advance_time" else 1
        if not isinstance(ticks, int) or ticks < 1:
            ticks = 1
        self.tick += ticks
        self.state_version += 1
        event = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "event_id": self.last_event_id + 1,
            "type": "WORLD_ADVANCED" if payload.get("type") == "advance_time" else "NPC_MOVED",
            "tick": self.tick,
            "world_id": self.world_id,
            "payload": {"ticks": ticks, "command_type": payload.get("type")},
        }
        self.last_event_id = event["event_id"]
        self.events.append(event)
        response = {
            "accepted": True,
            "state_version": self.state_version,
            "events": [event],
        }
        self.commands[payload["idempotency_key"]] = response
        return 200, response


def make_handler(mock: WorldMock) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/v1/health":
                self._send(*mock.health())
            elif parsed.path == "/v1/world/snapshot":
                self._send(*mock.snapshot())
            elif parsed.path == "/v1/world/events":
                query = parse_qs(parsed.query)
                after = int(query.get("after", ["0"])[0])
                limit = int(query.get("limit", [str(MAX_EVENTS)])[0])
                self._send(*mock.list_events(after, limit))
            else:
                self._send(404, {"code": "not_found", "message": f"no route for {parsed.path}"})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/v1/commands":
                self._send(404, {"code": "not_found", "message": f"no route for {parsed.path}"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                self._send(400, {"code": "invalid_json", "message": "body is not valid JSON"})
                return
            if not isinstance(payload, dict):
                self._send(400, {"code": "invalid_command", "message": "body must be an object"})
                return
            self._send(*mock.submit_command(payload))

        def log_message(self, format: str, *args: Any) -> None:  # silence per-request logs
            pass

    return Handler


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(WorldMock()))
    print(f"mock world server listening on http://{host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    run(host, port)
