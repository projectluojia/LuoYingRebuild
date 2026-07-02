import pytest
from luoying_bot.infra.voice.stub import StubVoiceAdapter
from luoying_bot.ports.voice import VoicePort


def test_stub_adapter_implements_voice_port():
    """StubVoiceAdapter satisfies the VoicePort ABC."""
    adapter = StubVoiceAdapter()
    assert isinstance(adapter, VoicePort)


def test_stub_adapter_available_returns_false():
    """Stub reports unavailable by default."""
    adapter = StubVoiceAdapter()
    assert adapter.available() is False


@pytest.mark.asyncio
async def test_stub_adapter_stt_raises_not_implemented():
    """STT raises NotImplementedError on the stub."""
    adapter = StubVoiceAdapter()
    with pytest.raises(NotImplementedError):
        await adapter.speech_to_text(b"fake audio", "webm")


@pytest.mark.asyncio
async def test_stub_adapter_tts_raises_not_implemented():
    """TTS raises NotImplementedError on the stub after yielding one empty chunk."""
    adapter = StubVoiceAdapter()
    gen = adapter.text_to_speech("hello", "voice-1")
    # First yield returns empty chunk (stub satisfies AsyncIterator contract)
    first = await gen.__anext__()
    assert first == b""
    # Second yield hits the error
    with pytest.raises(NotImplementedError):
        await gen.__anext__()
