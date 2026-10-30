"""Actual Godot HTTP transport with synthetic PCM and localhost media stubs.

This does not measure recognition quality, real microphone capture or TTS quality.
Set GODOT_BIN to a console executable to enable it when Godot is not on PATH.
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import shutil
import subprocess
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROJECT = ROOT / "clients" / "godot"


def _wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\0\0" * 8000)
    return buffer.getvalue()


def test_godot_voice_http_roundtrip_and_cancelled_response() -> None:
    godot = os.environ.get("GODOT_BIN") or shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot not installed; set GODOT_BIN to enable the media transport test")
    requests: list[tuple[str, str, str, bytes]] = []
    audio = _wav()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            requests.append((self.command, self.path, self.headers.get("Content-Type", ""), body))
            if self.path == "/v1/voice/transcriptions":
                output = json.dumps({"text": "道友，可否借我护符？"}).encode("utf-8")
                mime = "application/json"
            elif self.path == "/v1/voice/speech":
                output, mime = audio, "audio/wav"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)

        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    environment = dict(os.environ)
    environment["UNWRITTEN_DAO_VOICE_TEST_URL"] = f"http://127.0.0.1:{server.server_port}"
    try:
        imported = subprocess.run(
            [godot, "--headless", "--path", str(PROJECT), "--editor", "--import", "--quit"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=45,
            env=environment,
        )
        assert imported.returncode == 0, imported.stdout + imported.stderr
        assert "SCRIPT ERROR" not in imported.stdout + imported.stderr
        result = subprocess.run(
            [godot, "--headless", "--path", str(PROJECT), "--script", "res://tests/voice_http.gd"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            env=environment,
        )
        output = result.stdout + result.stderr
        assert result.returncode == 0, output
        assert "VOICE HTTP roundtrip passed" in output, output
        assert "SCRIPT ERROR" not in output, output
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    assert [request[:3] for request in requests] == [
        ("POST", "/v1/voice/transcriptions", "audio/wav"),
        ("POST", "/v1/voice/speech", "application/json"),
    ]
    assert requests[0][3][:4] == b"RIFF"
    with wave.open(io.BytesIO(requests[0][3]), "rb") as submitted:
        assert submitted.getnchannels() == 1
        assert submitted.getsampwidth() == 2
        assert submitted.getframerate() == 16000
        assert submitted.getnframes() == 8000
    assert json.loads(requests[1][3]) == {"text": "我愿将护符赠你。"}
