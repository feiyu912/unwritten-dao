"""Transient bounded voice transport; never accesses a world database."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from world_server.speech import (
    MAX_AUDIO_BYTES,
    MAX_INPUT_AUDIO_BYTES,
    MAX_TEXT_LENGTH,
    AudioTooLarge,
    SpeechError,
    SpeechTimeout,
    UnsupportedAudio,
    build_speech_recognizer,
    build_speech_synthesizer,
    validate_wav,
)

router = APIRouter(prefix="/v1/voice")


class _InputError(Exception):
    def __init__(self, status: int, code: str) -> None:
        self.status = status
        self.code = code


def _error(status: int, code: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "message": code, "details": {}})


async def _body(request: Request, limit: int, code: str) -> bytes:
    result = bytearray()
    try:
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                if len(result) + len(chunk) > limit:
                    raise _InputError(413 if code == "audio_too_large" else 422, code)
                result.extend(chunk)
    except (TimeoutError, ClientDisconnect) as exc:
        raise _InputError(422, "invalid_audio" if code == "audio_too_large" else code) from exc
    return bytes(result)


def _media(request: Request) -> str:
    return request.headers.get("content-type", "").split(";", 1)[0].strip().lower()


@router.post("/transcriptions")
async def transcribe(request: Request) -> Response:
    if _media(request) != "audio/wav":
        return _error(415, "unsupported_audio")
    try:
        audio = await _body(request, MAX_INPUT_AUDIO_BYTES, "audio_too_large")
        validate_wav(audio)
    except _InputError as exc:
        return _error(exc.status, exc.code)
    except AudioTooLarge:
        return _error(413, "audio_too_large")
    except UnsupportedAudio:
        return _error(415, "unsupported_audio")
    except SpeechError:
        return _error(422, "invalid_audio")
    try:
        provider = build_speech_recognizer()
    except SpeechError:
        return _error(503, "speech_not_configured")
    try:
        text = await asyncio.wait_for(run_in_threadpool(provider.transcribe, audio), timeout=35)
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
            raise SpeechError("invalid transcription")
        return JSONResponse({"text": text.strip()})
    except (SpeechTimeout, TimeoutError):
        return _error(504, "speech_provider_timeout")
    except SpeechError:
        return _error(502, "speech_provider_failed")


@router.post("/speech")
async def synthesize(request: Request) -> Response:
    if _media(request) != "application/json":
        return _error(422, "invalid_text")
    try:
        raw = await _body(request, 32 * 1024, "invalid_text")
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) != {"text"}:
            raise ValueError("invalid shape")
        text = payload["text"]
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
            raise ValueError("invalid text")
    except _InputError as exc:
        return _error(exc.status, exc.code)
    except (ValueError, TypeError):
        return _error(422, "invalid_text")
    try:
        provider = build_speech_synthesizer()
    except SpeechError:
        return _error(503, "speech_not_configured")
    try:
        audio = await asyncio.wait_for(run_in_threadpool(provider.synthesize, text.strip()), 35)
        if not isinstance(audio, bytes) or len(audio) > MAX_AUDIO_BYTES:
            raise SpeechError("invalid synthesis")
        validate_wav(audio, max_seconds=120)
        return Response(audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})
    except (SpeechTimeout, TimeoutError):
        return _error(504, "speech_provider_timeout")
    except SpeechError:
        return _error(502, "speech_provider_failed")
