from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from world_server.app import create_app
from world_server.models import MemoryEpisodeRow
from world_server.repository import (
    apply_command,
    bootstrap,
    list_decisions,
    load_state,
)

from world_core import (
    ITEM_MAP_FRAGMENT,
    LOC_BLACKWOOD_FOREST,
    LOC_MISTY_VALLEY,
    LOC_RUINED_TEMPLE,
    PROTAGONIST_ID,
    make_command,
)

pytestmark = pytest.mark.integration


class _StubHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path.endswith("/chat/completions"):
            content = json.dumps(
                {
                    "intent": "start_cultivation",
                    "arguments": {"days": 5},
                    "valid_for_ticks": 7,
                    "rationale_short": "stub provider decision",
                    "confidence": 0.6,
                }
            )
            payload: dict[str, Any] = {
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}]
            }
        elif self.path.endswith("/embeddings"):
            inputs = body.get("input", [])
            payload = {
                "data": [
                    {
                        "index": index,
                        "embedding": [1.0 if dim == 0 else 0.0 for dim in range(768)],
                    }
                    for index in range(len(inputs))
                ]
            }
        else:
            self.send_response(404)
            self.end_headers()
            return
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture()
def stub_provider() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_decision_uses_openai_provider_over_http(
    session: Any, stub_provider: str, monkeypatch: Any
) -> None:
    monkeypatch.setenv("AGENT_PROVIDER", "openai")
    monkeypatch.setenv("LLM_BASE_URL", stub_provider)
    monkeypatch.setenv("LLM_MODEL", "stub-model")
    monkeypatch.setenv("LLM_API_KEY", "stub-key")

    with TestClient(create_app()) as client:
        response = client.post(f"/v1/agents/{PROTAGONIST_ID}/decision")
        assert response.status_code == 200, response.text
        proposal = response.json()
        assert proposal["intent"] == "start_cultivation"
        assert proposal["arguments"] == {"days": 5}

    rows = list_decisions(session, npc_id=PROTAGONIST_ID, accepted_only=True)
    assert rows
    assert rows[-1].provider == "OpenAICompatibleProvider"
    assert "stub provider decision" in (rows[-1].raw_response or "")


def test_embedding_provider_writes_and_queries_pgvector(
    session: Any, stub_provider: str, monkeypatch: Any
) -> None:
    from world_server.memory_store import retrieve_memories

    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_BASE_URL", stub_provider)
    monkeypatch.setenv("EMBEDDING_MODEL", "stub-embed")

    state = bootstrap(session, seed=42)
    actor = state.npcs[PROTAGONIST_ID]
    steps = [
        ("move", {"to_location_id": LOC_BLACKWOOD_FOREST}),
        ("move", {"to_location_id": LOC_RUINED_TEMPLE}),
        (
            "transfer_item",
            {
                "item_id": ITEM_MAP_FRAGMENT,
                "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
                "to": {"kind": "npc", "id": actor.npc_id},
            },
        ),
        ("move", {"to_location_id": LOC_MISTY_VALLEY}),
        ("investigate", {"target_location_id": LOC_MISTY_VALLEY, "focus": "secret_realm"}),
    ]
    for intent, arguments in steps:
        current = load_state(session)
        apply_command(
            session,
            make_command(current, actor.npc_id, intent, arguments, source="test"),  # type: ignore[arg-type]
        )

    rows = (
        session.execute(select(MemoryEpisodeRow).where(MemoryEpisodeRow.npc_id == actor.npc_id))
        .scalars()
        .all()
    )
    embedded = [row for row in rows if row.embedding is not None]
    assert embedded
    assert len(embedded[0].embedding) == 768

    current = load_state(session)
    recalled = retrieve_memories(session, current, actor.npc_id)
    assert recalled
