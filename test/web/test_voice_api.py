import pytest
from httpx import AsyncClient, ASGITransport
from luoying_bot.infra.http.api import app


@pytest.fixture(autouse=True)
async def lifespan_fixture():
    """Manually enter the app lifespan so container is available in tests."""
    async with app.router.lifespan_context(app):
        yield


@pytest.mark.asyncio
async def test_voice_config_returns_stub_values():
    """Stub adapter reports both STT and TTS as disabled."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/voice/config")
    assert response.status_code == 200
    data = response.json()
    assert data["stt_enabled"] is False
    assert data["tts_enabled"] is False


@pytest.mark.asyncio
async def test_stt_returns_503_when_unavailable():
    """STT endpoint returns 503 when the voice adapter is unavailable."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/voice/stt", content=b"fake audio")
    assert response.status_code == 503
    assert "not available" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_tts_returns_503_when_unavailable():
    """TTS endpoint returns 503 when the voice adapter is unavailable."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/voice/tts",
            json={"text": "Hello"},
        )
    assert response.status_code == 503
    assert "not available" in response.json()["detail"].lower()
