from __future__ import annotations

import io
import wave
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from world_server.app import create_app
from world_server.speech import MAX_AUDIO_BYTES, MAX_INPUT_AUDIO_BYTES, SpeechError, SpeechTimeout

from world_server import speech_routes


def wav(seconds=1, rate=8000, width=2, channels=1):
    result = io.BytesIO()
    with wave.open(result, "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        output.writeframes(b"\0" * seconds * rate * channels * width)
    return result.getvalue()


@pytest.fixture
def client():
    # No lifespan context: voice operations must not need database initialization.
    return TestClient(create_app())


def install(monkeypatch, recognize=lambda _: "道友请留步", speak=lambda _: wav()):
    monkeypatch.setattr(
        speech_routes,
        "build_speech_recognizer",
        lambda: SimpleNamespace(
            transcribe=recognize,
        ),
    )
    monkeypatch.setattr(
        speech_routes,
        "build_speech_synthesizer",
        lambda: SimpleNamespace(
            synthesize=speak,
        ),
    )


def test_success_routes_do_not_initialize_or_mutate_world(client, monkeypatch):
    received = []
    audio = wav()
    install(monkeypatch, recognize=lambda data: received.append(data) or " 道友请留步 ")
    response = client.post(
        "/v1/voice/transcriptions",
        content=audio,
        headers={
            "Content-Type": "audio/wav",
        },
    )
    assert response.status_code == 200 and response.json() == {"text": "道友请留步"}
    assert received == [audio]
    response = client.post("/v1/voice/speech", json={"text": "道友请留步"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["cache-control"] == "no-store"
    assert response.content == audio


@pytest.mark.parametrize(
    "kind,status,code",
    [
        ("size", 413, "audio_too_large"),
        ("duration", 413, "audio_too_large"),
        ("type", 415, "unsupported_audio"),
        ("width", 415, "unsupported_audio"),
        ("rate", 415, "unsupported_audio"),
        ("channels", 415, "unsupported_audio"),
        ("malformed", 422, "invalid_audio"),
        ("truncated", 422, "invalid_audio"),
        ("empty", 422, "invalid_audio"),
        ("zero", 422, "invalid_audio"),
    ],
)
def test_invalid_audio_before_provider(client, monkeypatch, kind, status, code):
    def fail():
        pytest.fail("invalid input reached provider construction")

    monkeypatch.setattr(speech_routes, "build_speech_recognizer", fail)
    samples = {
        "size": b"x" * (MAX_INPUT_AUDIO_BYTES + 1),
        "duration": wav(31),
        "type": wav(),
        "width": wav(width=1),
        "rate": wav(rate=4000),
        "channels": wav(channels=3),
        "malformed": b"no wav",
        "truncated": wav()[:-10],
        "empty": b"",
        "zero": wav(0),
    }
    response = client.post(
        "/v1/voice/transcriptions",
        content=samples[kind],
        headers={
            "Content-Type": "audio/mp3" if kind == "type" else "audio/wav",
        },
    )
    assert response.status_code == status
    assert response.json() == {"code": code, "message": code, "details": {}}


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"text": ""},
        {"text": " "},
        {"text": 123},
        {"text": "hello", "model": "injected"},
        {"text": "x" * 2001},
    ],
    ids=["null", "array", "empty", "empty-text", "blank", "number", "extra", "long"],
)
def test_invalid_json_text(client, payload):
    response = client.post("/v1/voice/speech", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_text"


def test_bad_json_and_content_type(client):
    for content, mime in [
        (b"not-json", "application/json"),
        (b"{}", "text/plain"),
        (b"x" * 32769, "application/json"),
    ]:
        response = client.post("/v1/voice/speech", content=content, headers={"Content-Type": mime})
        assert response.status_code == 422
        assert response.json()["code"] == "invalid_text"


def test_non_pcm_wav_is_unsupported(client):
    audio = bytearray(wav())
    audio[20:22] = (3).to_bytes(2, "little")  # IEEE floating point, not PCM.
    response = client.post(
        "/v1/voice/transcriptions",
        content=bytes(audio),
        headers={"Content-Type": "audio/wav"},
    )
    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_audio"


def test_missing_configuration(client, monkeypatch):
    for name in ["ASR_BASE_URL", "ASR_MODEL", "TTS_BASE_URL", "TTS_MODEL", "TTS_VOICE"]:
        monkeypatch.delenv(name, raising=False)
    for response in [
        client.post(
            "/v1/voice/transcriptions", content=wav(), headers={"Content-Type": "audio/wav"}
        ),
        client.post("/v1/voice/speech", json={"text": "hello"}),
    ]:
        assert response.status_code == 503
        assert response.json()["code"] == "speech_not_configured"


@pytest.mark.parametrize("timeout", [False, True])
def test_provider_failure_and_timeout_sanitized(client, monkeypatch, timeout):
    def fail(_):
        raise (SpeechTimeout if timeout else SpeechError)("SECRET_REMOTE_BODY")

    install(monkeypatch, recognize=fail, speak=fail)
    for response in [
        client.post(
            "/v1/voice/transcriptions", content=wav(), headers={"Content-Type": "audio/wav"}
        ),
        client.post("/v1/voice/speech", json={"text": "hello"}),
    ]:
        assert response.status_code == (504 if timeout else 502)
        assert response.json()["code"] == (
            "speech_provider_timeout" if timeout else "speech_provider_failed"
        )
        assert "SECRET_REMOTE_BODY" not in response.text


def test_unusable_provider_output(client, monkeypatch):
    for output in [b"fake wav", wav(121), b"x" * (MAX_AUDIO_BYTES + 1)]:
        install(monkeypatch, speak=lambda _, output=output: output)
        response = client.post("/v1/voice/speech", json={"text": "hello"})
        assert response.status_code == 502
    for output in ["", "x" * 2001, None]:
        install(monkeypatch, recognize=lambda _, output=output: output)
        response = client.post(
            "/v1/voice/transcriptions",
            content=wav(),
            headers={
                "Content-Type": "audio/wav",
            },
        )
        assert response.status_code == 502
