from __future__ import annotations

from collections.abc import AsyncIterator

from luoying_bot.ports.voice import VoicePort


class StubVoiceAdapter(VoicePort):
    """Voice adapter that is always unavailable.

    Use this as the default when no voice service is configured.
    """

    async def speech_to_text(self, audio: bytes, format: str) -> str:
        raise NotImplementedError("STT is not available — configure a voice provider to enable it.")

    async def text_to_speech(self, text: str, voice_id: str) -> AsyncIterator[bytes]:
        yield b""  # pragma: no cover
        raise NotImplementedError("TTS is not available — configure a voice provider to enable it.")

    def available(self) -> bool:
        return False
