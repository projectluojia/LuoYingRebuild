from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException

from luoying_bot.ports.voice import VoicePort

if TYPE_CHECKING:
    from luoying_bot.bootstrap import AppContainer


def create_voice_router(
    *,
    container_provider: Callable[[], "AppContainer"],
    current_user_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(prefix="/voice", tags=["voice"])

    def _voice() -> VoicePort:
        return container_provider().services.voice  # type: ignore[attr-defined]

    # GET /voice/config
    @router.get("/config")
    async def voice_config(_user: object = None) -> dict[str, bool]:
        """Return the availability status of voice features."""
        voice = _voice()
        return {
            "stt_enabled": voice.available(),
            "tts_enabled": voice.available(),
        }

    # POST /voice/stt
    @router.post("/stt")
    async def speech_to_text(
        file: bytes | None = None,
        _user: object = None,
    ) -> dict[str, str]:
        """Accept audio bytes and return recognized text."""
        voice = _voice()
        if not voice.available():
            raise HTTPException(
                status_code=503,
                detail="Voice service is not available. Set VOICE_PROVIDER in your environment.",
            )
        if file is None:
            raise HTTPException(status_code=400, detail="No audio file provided.")
        try:
            # In production, detect format from content-type or magic bytes.
            # Here we default to wav for simplicity.
            text = await voice.speech_to_text(audio=file, format="wav")
        except Exception as exc:  # pragma: no cover
            logging.exception("STT failed")
            raise HTTPException(status_code=502, detail=f"STT error: {exc}") from exc
        return {"text": text}

    # POST /voice/tts
    @router.post("/tts")
    async def text_to_speech(
        text: str | None = None,
        voice_id: str | None = None,
        _user: object = None,
    ) -> bytes:
        """Accept text and return audio stream."""
        voice = _voice()
        if not voice.available():
            raise HTTPException(
                status_code=503,
                detail="Voice service is not available. Set VOICE_PROVIDER in your environment.",
            )
        if not text:
            raise HTTPException(status_code=400, detail="No text provided.")
        try:
            chunks: list[bytes] = []
            async for chunk in voice.text_to_speech(text=text, voice_id=voice_id or "default"):
                chunks.append(chunk)
            audio_bytes = b"".join(chunks)
        except Exception as exc:  # pragma: no cover
            logging.exception("TTS failed")
            raise HTTPException(status_code=502, detail=f"TTS error: {exc}") from exc
        return audio_bytes

    return router
