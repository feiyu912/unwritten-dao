"""Tests for the headless mock world server (stdlib + pytest only)."""

from __future__ import annotations

import json
import threading
import uuid
from http.server import ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from mock_world_server import WorldMock, make_handler


@pytest.fixture()
def base_url() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(WorldMock()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _get_json(url: str) -> tuple[int, Any]:
    with urlopen(url, timeout=5) as response:
        return response.status, json.loads(response.read())


def _post_json(url: str, body: dict[str, Any]) -> tuple[int, Any]:
    request = Request(url, data=json.dumps(body).encode(), method="POST")
    request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _post_command(base_url: str, cmd: dict[str, Any]) -> tuple[int, Any]:
    return _post_json(f"{base_url}/v1/commands", cmd)


def _command(key: str, expected_version: int, cmd_type: str = "advance_time") -> dict[str, Any]:
    return {
        "schema_version": "world-command.v1",
        "world_id": "any",
        "idempotency_key": key,
        "expected_state_version": expected_version,
        "type": cmd_type,
        "arguments": {"ticks": 3} if cmd_type == "advance_time" else {},
    }


def test_health_and_snapshot_shape(base_url: str) -> None:
    status, health = _get_json(f"{base_url}/v1/health")
    assert status == 200
    assert health == {"status": "ok", "world_loaded": True}

    status, snap = _get_json(f"{base_url}/v1/world/snapshot")
    assert status == 200
    assert snap["schema_version"] == "world-snapshot.v1"
    assert uuid.UUID(snap["world_id"]).version >= 1
    assert snap["world_seed"] == 42
    assert snap["sim_version"] == "0.1.0"
    assert snap["ruleset_version"] == "1.0.0"
    assert snap["checksum"] == "sha256:" + "0" * 64
    assert snap["state"] == {}
    assert isinstance(snap["tick"], int)
    assert isinstance(snap["state_version"], int)
    assert isinstance(snap["last_event_id"], int)


def test_accepted_command_advances_version_and_emits_one_event(base_url: str) -> None:
    _, snap = _get_json(f"{base_url}/v1/world/snapshot")
    version = snap["state_version"]

    status, result = _post_command(base_url, _command("k1", version))
    assert status == 200
    assert result["accepted"] is True
    assert result["state_version"] == version + 1
    assert len(result["events"]) == 1

    _, snap2 = _get_json(f"{base_url}/v1/world/snapshot")
    assert snap2["state_version"] == version + 1
    assert snap2["tick"] == snap["tick"] + 3  # advance_time with ticks=3

    status, listing = _get_json(f"{base_url}/v1/world/events?after=0")
    assert status == 200
    assert len(listing["events"]) == 1
    assert listing["events"][0]["event_id"] == snap2["last_event_id"]
    assert listing["events"][0]["type"] == "WORLD_ADVANCED"


def test_duplicate_idempotency_key_returns_identical_response(base_url: str) -> None:
    _, snap = _get_json(f"{base_url}/v1/world/snapshot")

    status1, first = _post_command(base_url, _command("dup", snap["state_version"]))
    status2, second = _post_command(base_url, _command("dup", snap["state_version"]))
    assert status1 == status2 == 200
    assert first == second
    assert first["state_version"] == snap["state_version"] + 1

    _, listing = _get_json(f"{base_url}/v1/world/events?after=0")
    assert len(listing["events"]) == 1  # no new event on replay

    _, snap2 = _get_json(f"{base_url}/v1/world/snapshot")
    assert snap2["state_version"] == snap["state_version"] + 1


def test_stale_expected_state_version_returns_409(base_url: str) -> None:
    _, snap = _get_json(f"{base_url}/v1/world/snapshot")

    stale = _command("stale", snap["state_version"] + 5)
    status, error = _post_command(base_url, stale)
    assert status == 409
    assert error["code"] == "stale_state_version"
