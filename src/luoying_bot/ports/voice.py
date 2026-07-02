from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class VoicePort(ABC):
    """Abstraction for speech-to-text and text-to-speech services."""

    @abstractmethod
    async def speech_to_text(self, audio: bytes, format: str) -> str:
        """Convert audio bytes to text.

        Args:
            audio: Raw audio bytes.
            format: Audio format (e.g. "wav", "mp3", "webm").

        Returns:
            Recognized text.
        """
        ...

    @abstractmethod
    async def text_to_speech(
        self, text: str, voice_id: str
    ) -> AsyncIterator[bytes]:
        """Convert text to speech audio stream.

        Args:
            text: Text to synthesize.
            voice_id: Voice identifier to use.

        Yields:
            Raw audio bytes (e.g. WAV/MP3 chunks).
        """
        ...

    @abstractmethod
    def available(self) -> bool:
        """Return True when the voice service is configured and operational."""
        ...