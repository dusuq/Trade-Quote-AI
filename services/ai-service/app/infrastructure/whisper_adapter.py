"""OpenAI Whisper speech-to-text adapter.

The only place the OpenAI SDK is imported.
"""

from __future__ import annotations

from typing import Any

import openai

from app.domain.errors import TranscriptionError
from app.domain.models import TranscriptionResult

# Whisper infers the container from the filename extension, so the upload
# needs a plausible one for the MIME type it was given.
_EXTENSION_BY_MIME = {
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "mp4",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "video/mp4": "mp4",
    "video/webm": "webm",
}


class WhisperTranscriptionService:
    """Implements `TranscriptionService` using the OpenAI audio API."""

    def __init__(self, api_key: str, model: str, client: Any | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client

    def _require_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise TranscriptionError(
                "OPENAI_API_KEY is not configured; voice input is unavailable"
            )
        self._client = openai.OpenAI(api_key=self._api_key)
        return self._client

    def transcribe(self, audio_bytes: bytes, mime_type: str) -> TranscriptionResult:
        client = self._require_client()
        extension = _EXTENSION_BY_MIME.get(mime_type, "webm")

        try:
            response = client.audio.transcriptions.create(
                model=self._model,
                file=(f"recording.{extension}", audio_bytes, mime_type),
                response_format="verbose_json",
            )
        except Exception as exc:
            raise TranscriptionError(f"transcription failed: {exc}") from exc

        return TranscriptionResult(
            text=str(getattr(response, "text", "") or ""),
            language=str(getattr(response, "language", "") or "unknown"),
            duration_seconds=float(getattr(response, "duration", 0.0) or 0.0),
            model_id=self._model,
        )
