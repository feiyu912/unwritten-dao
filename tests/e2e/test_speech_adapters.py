from __future__ import annotations

import io
import json
import wave
from email.parser import BytesParser
from email.policy import default

import httpx
import pytest
from world_server.speech import (
    MAX_AUDIO_BYTES,
    MAX_INPUT_AUDIO_BYTES,
    OpenAICompatibleRecognizer,
    OpenAICompatibleSynthesizer,
    SpeechError,
    build_speech_recognizer,
    build_speech_synthesizer,
)


def wav(seconds: int = 1, rate: int = 8000, channels: int = 1, width: int = 2) -> bytes:
    result = io.BytesIO()
    with wave.open(result, "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        output.writeframes(b"\0" * seconds * rate * channels * width)
    return result.getvalue()


def recognizer(handler, key=None):
    return OpenAICompatibleRecognizer(
        base_url="http://local/v1/",
        model="asr-test",
        api_key=key,
        transport=httpx.MockTransport(handler),
    )


def synthesizer(handler):
    return OpenAICompatibleSynthesizer(
        base_url="http://local/v1",
        model="tts-test",
        voice="voice-test",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.parametrize("key", [None, "test-only-key"])
def test_transcription_multipart_and_optional_auth(key) -> None:
    audio = wav()

    def handler(request):
        assert request.url.path == "/v1/audio/transcriptions"
        assert request.headers.get("authorization") == (f"Bearer {key}" if key else None)
        raw = b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n"
        message = BytesParser(policy=default).parsebytes(raw + request.content)
        fields = {
            part.get_param("name", header="content-disposition"): part
            for part in message.iter_parts()
        }
        assert fields["model"].get_payload(decode=True) == b"asr-test"
        assert fields["language"].get_payload(decode=True) == b"zh"
        assert fields["response_format"].get_payload(decode=True) == b"json"
        assert fields["file"].get_filename() == "utterance.wav"
        assert fields["file"].get_content_type() == "audio/wav"
        assert fields["file"].get_payload(decode=True) == audio
        return httpx.Response(200, json={"text": " 道友，可愿同行？ "})

    assert recognizer(handler, key).transcribe(audio) == "道友，可愿同行？"


def test_synthesis_json_and_longer_response_wav() -> None:
    audio = wav(31)

    def handler(request):
        assert request.url.path == "/v1/audio/speech"
        assert "authorization" not in request.headers
        assert json.loads(request.content) == {
            "model": "tts-test",
            "voice": "voice-test",
            "input": "请入山门。",
            "response_format": "wav",
        }
        return httpx.Response(200, content=audio)

    assert synthesizer(handler).synthesize(" 请入山门。 ") == audio


def no_request(_request):
    pytest.fail("invalid input reached the provider")


@pytest.mark.parametrize(
    "audio",
    [
        b"",
        b"not WAV",
        wav()[:-10],
        wav(31),
        wav(rate=4000),
        wav(channels=3),
        wav(width=1),
        b"x" * (MAX_INPUT_AUDIO_BYTES + 1),
    ],
    ids=["empty", "not-wav", "truncated", "too-long", "rate", "channels", "width", "size"],
)
def test_invalid_recordings_rejected_before_request(audio) -> None:
    with pytest.raises(SpeechError):
        recognizer(no_request).transcribe(audio)


@pytest.mark.parametrize("text", ["", "  ", "字" * 2001], ids=["empty", "blank", "too-long"])
def test_invalid_text_rejected_before_request(text) -> None:
    with pytest.raises(SpeechError):
        synthesizer(no_request).synthesize(text)


@pytest.mark.parametrize("payload", [b"not json", b"[]", b'{"text":null}', b'{"text":""}'])
def test_bad_transcription_response_is_sanitized(payload) -> None:
    with pytest.raises(SpeechError) as caught:
        recognizer(lambda _: httpx.Response(200, content=payload)).transcribe(wav())
    assert payload.decode() not in str(caught.value)


@pytest.mark.parametrize("status", [302, 401, 429, 500])
def test_remote_error_body_never_escapes(status) -> None:
    for adapter, argument in [
        (recognizer(lambda _: httpx.Response(status, text="SECRET_PROVIDER_BODY")), wav()),
        (synthesizer(lambda _: httpx.Response(status, text="SECRET_PROVIDER_BODY")), "hello"),
    ]:
        with pytest.raises(SpeechError) as caught:
            if isinstance(argument, bytes):
                adapter.transcribe(argument)
            else:
                adapter.synthesize(argument)
        assert "SECRET_PROVIDER_BODY" not in str(caught.value)


class OversizedStream(httpx.SyncByteStream):
    def __init__(self, size):
        self.size = size

    def __iter__(self):
        for _ in range(self.size // 65536 + 1):
            yield b"x" * 65536


def test_streaming_size_caps() -> None:
    with pytest.raises(SpeechError, match="size limit"):
        recognizer(lambda _: httpx.Response(200, stream=OversizedStream(65536))).transcribe(wav())
    with pytest.raises(SpeechError, match="size limit"):
        synthesizer(
            lambda _: httpx.Response(
                200,
                stream=OversizedStream(MAX_AUDIO_BYTES),
            )
        ).synthesize("hello")


@pytest.mark.parametrize(
    "audio",
    [b"fake wav", wav(121), wav()[:-10]],
    ids=["not-wav", "too-long", "truncated"],
)
def test_synthesis_rejects_invalid_output(audio) -> None:
    with pytest.raises(SpeechError):
        synthesizer(lambda _: httpx.Response(200, content=audio)).synthesize("hello")


def test_transport_error_does_not_leak_exception_detail() -> None:
    def handler(_request):
        raise httpx.ConnectError("SECRET_TRANSPORT_DETAIL")

    with pytest.raises(SpeechError) as caught:
        recognizer(handler).transcribe(wav())
    assert "SECRET_TRANSPORT_DETAIL" not in str(caught.value)
    assert caught.value.__suppress_context__


def test_env_config_requires_explicit_endpoints_models_and_voice(monkeypatch) -> None:
    for key in ["ASR_BASE_URL", "ASR_MODEL", "TTS_BASE_URL", "TTS_MODEL", "TTS_VOICE"]:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(SpeechError):
        build_speech_recognizer()
    with pytest.raises(SpeechError):
        build_speech_synthesizer()
    monkeypatch.setenv("ASR_BASE_URL", "http://local/v1")
    with pytest.raises(SpeechError):
        build_speech_recognizer()
    monkeypatch.setenv("ASR_MODEL", "local-asr")
    assert isinstance(build_speech_recognizer(), OpenAICompatibleRecognizer)
    monkeypatch.setenv("TTS_BASE_URL", "http://local/v1")
    monkeypatch.setenv("TTS_MODEL", "local-tts")
    with pytest.raises(SpeechError):
        build_speech_synthesizer()
    monkeypatch.setenv("TTS_VOICE", "local-voice")
    assert isinstance(build_speech_synthesizer(), OpenAICompatibleSynthesizer)
