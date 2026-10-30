"""Replaceable speech providers. No world state or client-facing protocol here.

Endpoints/models are explicit so local compatible services and hosted services
use the same adapter. Credentials remain server-side and are never in errors.
"""

from __future__ import annotations

import io
import json
import os
import wave
from typing import Protocol

import httpx

MAX_AUDIO_BYTES = 12 * 1024 * 1024
MAX_INPUT_AUDIO_BYTES = 6 * 1024 * 1024
MAX_TEXT_LENGTH = 2000


class SpeechError(RuntimeError):
    """Invalid audio or an unusable speech-provider response."""


class AudioTooLarge(SpeechError):
    """Audio exceeds the byte or duration limit."""


class UnsupportedAudio(SpeechError):
    """WAV sample format cannot be played by the client."""


class SpeechTimeout(SpeechError):
    """The configured provider deadline elapsed."""


class SpeechRecognizer(Protocol):
    def transcribe(self, audio: bytes) -> str: ...


class SpeechSynthesizer(Protocol):
    def synthesize(self, text: str) -> bytes: ...


def validate_wav(audio: bytes, *, max_seconds: int = 30) -> None:
    """Accept bounded, complete 16-bit PCM WAV rather than arbitrary uploads."""
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        if audio:
            raise AudioTooLarge("audio exceeds the size limit")
        raise SpeechError("audio is empty")
    try:
        with wave.open(io.BytesIO(audio), "rb") as source:
            channels = source.getnchannels()
            rate = source.getframerate()
            frames = source.getnframes()
            width = source.getsampwidth()
            if (
                source.getcomptype() != "NONE"
                or channels not in (1, 2)
                or width != 2
                or not 8000 <= rate <= 48000
            ):
                raise UnsupportedAudio("unsupported PCM WAV format")
            if frames <= 0:
                raise SpeechError("audio is empty")
            if frames > rate * max_seconds:
                raise AudioTooLarge("audio exceeds the duration limit")
            if len(source.readframes(frames)) != frames * channels * width:
                raise SpeechError("truncated WAV audio")
    except wave.Error as exc:
        if str(exc).startswith("unknown format:"):
            raise UnsupportedAudio("unsupported WAV encoding") from None
        raise SpeechError("invalid PCM WAV audio") from exc
    except (EOFError, OSError) as exc:
        raise SpeechError("invalid PCM WAV audio") from exc


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT_LENGTH:
        raise SpeechError("speech text must contain 1..2000 characters")
    return value.strip()


class _CompatibleSpeech:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not base_url.strip() or not model.strip():
            raise SpeechError("speech provider requires an endpoint and model")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport

    def _client(self) -> httpx.Client:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        return httpx.Client(
            headers=headers,
            timeout=self._timeout,
            transport=self._transport,
            follow_redirects=False,
        )

    @staticmethod
    def _read(response: httpx.Response, *, limit: int) -> bytes:
        if response.status_code != 200:
            raise SpeechError("speech provider returned an unsuccessful response")
        result = bytearray()
        for chunk in response.iter_bytes():
            if len(result) + len(chunk) > limit:
                raise SpeechError("speech provider response exceeds the size limit")
            result.extend(chunk)
        return bytes(result)


class OpenAICompatibleRecognizer(_CompatibleSpeech):
    def transcribe(self, audio: bytes) -> str:
        if len(audio) > MAX_INPUT_AUDIO_BYTES:
            raise AudioTooLarge("recorded audio exceeds the size limit")
        validate_wav(audio)
        try:
            with (
                self._client() as client,
                client.stream(
                    "POST",
                    f"{self.base_url}/audio/transcriptions",
                    data={"model": self.model, "response_format": "json", "language": "zh"},
                    files={"file": ("utterance.wav", audio, "audio/wav")},
                ) as response,
            ):
                raw = self._read(response, limit=64 * 1024)
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise SpeechError("speech provider returned invalid transcription data")
            return _text(result.get("text"))
        except httpx.TimeoutException:
            raise SpeechTimeout("speech transcription timed out") from None
        except (httpx.HTTPError, ValueError, TypeError):
            raise SpeechError("speech transcription failed") from None


class OpenAICompatibleSynthesizer(_CompatibleSpeech):
    def __init__(
        self,
        *,
        voice: str,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout=timeout,
            transport=transport,
        )
        if not voice.strip():
            raise SpeechError("speech synthesis requires an explicit voice")
        self.voice = voice

    def synthesize(self, text: str) -> bytes:
        text = _text(text)
        try:
            with (
                self._client() as client,
                client.stream(
                    "POST",
                    f"{self.base_url}/audio/speech",
                    json={
                        "model": self.model,
                        "voice": self.voice,
                        "input": text,
                        "response_format": "wav",
                    },
                ) as response,
            ):
                audio = self._read(response, limit=MAX_AUDIO_BYTES)
            validate_wav(audio, max_seconds=120)
            return audio
        except httpx.TimeoutException:
            raise SpeechTimeout("speech synthesis timed out") from None
        except httpx.HTTPError:
            raise SpeechError("speech synthesis failed") from None


def build_speech_recognizer() -> SpeechRecognizer:
    return OpenAICompatibleRecognizer(
        base_url=os.environ.get("ASR_BASE_URL", ""),
        model=os.environ.get("ASR_MODEL", ""),
        api_key=os.environ.get("ASR_API_KEY"),
    )


def build_speech_synthesizer() -> SpeechSynthesizer:
    return OpenAICompatibleSynthesizer(
        base_url=os.environ.get("TTS_BASE_URL", ""),
        model=os.environ.get("TTS_MODEL", ""),
        api_key=os.environ.get("TTS_API_KEY"),
        voice=os.environ.get("TTS_VOICE", ""),
    )
