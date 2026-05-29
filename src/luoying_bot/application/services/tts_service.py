"""
Volcano Engine TTS service with emotion support and volume-based lip sync data.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx

try:
    from pydub import AudioSegment
    from pydub.utils import make_chunks
    _HAS_PYDUB = True
except ImportError:
    _HAS_PYDUB = False

from luoying_bot.config import settings

logger = logging.getLogger(__name__)

GPT_SOVITS_PROMPTS: dict[str, str] = {
    "gentle": "你好，我是珞樱，来自武汉大学人工智能学院。很高兴在这里陪你一起探索人工智能的世界。",
    "happy": "欢迎来到珞樱的智能空间。今天也要开心地学习，认真地创造新的想法。",
    "thinking": "让我想一想。这个问题可以从目标、约束和实现路径三个角度来分析。",
    "angry": "请注意，这里涉及重要信息。我们需要确认边界条件，再继续执行下一步。",
}

# Voice types that support emotion SSML tags
VOICE_EMOTION_SUPPORT: dict[str, list[str]] = {
    "zh_female_qingxin": ["happy", "sad", "angry", "fearful", "gentle", "neutral"],
    "zh_male_qingrun": ["happy", "sad", "angry", "neutral"],
    "zh_female_tianmei": ["happy", "sad", "gentle", "neutral"],
}

# Emotion → SSML category mapping
EMOTION_TO_SSML: dict[str, str] = {
    "happy": "happy",
    "sad": "sad",
    "angry": "angry",
    "fear": "fearful",
    "surprise": "happy",  # fallback
    "gentle": "gentle",
    "neutral": "neutral",
}


@dataclass(slots=True)
class TTSResult:
    audio_wav_base64: str
    sample_rate: int = 24000
    volumes: list[float] = field(default_factory=list)
    chunk_ms: int = 20
    duration_ms: float = 0.0
    emotion: str = "neutral"
    text: str = ""


class VolcanoTTSService:
    """Volcano Engine TTS with emotion + lip-sync volume extraction."""

    API_URL = "https://openspeech.bytedance.com/api/v1/tts"

    def __init__(
        self,
        app_id: str | None = None,
        access_token: str | None = None,
        voice_type: str = "zh_female_qingxin",
        default_emotion: str = "gentle",
        speech_rate: float = 1.05,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.app_id = app_id or getattr(settings, "tts_app_id", "")
        self.access_token = access_token or getattr(settings, "tts_access_token", "")
        self.voice_type = voice_type or getattr(settings, "tts_voice_type", "zh_female_qingxin")
        self.default_emotion = default_emotion
        self.speech_rate = speech_rate
        self._client = client
        self._owns_client = client is None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), trust_env=False)
        return self._client

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def available(self) -> bool:
        return bool(self.app_id and self.access_token)

    def _build_ssml(self, text: str, emotion: str) -> str:
        """Wrap text in SSML with emotion tag if supported by the voice."""
        clean = text.strip()
        if not clean:
            return clean
        supported = VOICE_EMOTION_SUPPORT.get(self.voice_type, [])
        ssml_emotion = EMOTION_TO_SSML.get(emotion, "neutral")
        if ssml_emotion not in supported:
            ssml_emotion = "neutral"
        if ssml_emotion == "neutral":
            return f"<speak>{self._escape_xml(clean)}</speak>"
        return (
            f"<speak>"
            f'<emotion category="{ssml_emotion}">'
            f"{self._escape_xml(clean)}"
            f"</emotion>"
            f"</speak>"
        )

    @staticmethod
    def _escape_xml(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @staticmethod
    def _compute_volumes(audio: AudioSegment, chunk_ms: int = 20) -> list[float]:
        """Compute normalized RMS volumes per chunk for lip-sync."""
        chunks = make_chunks(audio, chunk_ms)
        rms_values = [chunk.rms for chunk in chunks]
        if not rms_values or max(rms_values) == 0:
            return [0.0] * len(rms_values)
        max_val = max(rms_values)
        return [round(v / max_val, 4) for v in rms_values]

    async def synthesize(self, text: str, emotion: str = "") -> TTSResult:
        """Generate TTS audio + volume data for a single sentence.

        Returns a TTSResult with base64 WAV, volumes[], and metadata.
        """
        if not self.available:
            return TTSResult(
                audio_wav_base64="",
                emotion=emotion,
                text=text,
            )

        emo = emotion or self.default_emotion
        ssml_text = self._build_ssml(text, emo)

        payload = {
            "app": {
                "appid": self.app_id,
                "token": self.access_token,
                "cluster": "volcano_tts",
            },
            "user": {"uid": "luoying"},
            "audio": {
                "voice_type": self.voice_type,
                "encoding": "wav",
                "speech_rate": self.speech_rate,
                "emotion": emo if emo != "neutral" else "",
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": ssml_text,
                "text_type": "ssml" if emo != "neutral" else "plain",
                "operation": "query",
            },
        }

        try:
            resp = await self.client.post(
                self.API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            audio_base64 = data.get("audio", {}).get("data", "")
        except Exception as exc:
            logger.error("TTS synthesis failed: %s", exc)
            return TTSResult(
                audio_wav_base64="",
                emotion=emo,
                text=text,
            )

        if not audio_base64:
            return TTSResult(audio_wav_base64="", emotion=emo, text=text)

        if not _HAS_PYDUB:
            return TTSResult(audio_wav_base64=audio_base64, emotion=emo, text=text)

        # Decode, compute volumes, re-encode as WAV (may need format conversion)
        try:
            raw_bytes = base64.b64decode(audio_base64)
            audio = AudioSegment.from_file(BytesIO(raw_bytes), format="wav")
            # Ensure 24kHz mono for frontend
            if audio.frame_rate != 24000:
                audio = audio.set_frame_rate(24000)
            if audio.channels > 1:
                audio = audio.set_channels(1)
            duration_ms = len(audio)
            volumes = self._compute_volumes(audio)
            wav_bytes = audio.export(format="wav").read()
            wav_b64 = base64.b64encode(wav_bytes).decode("utf-8")
        except Exception as exc:
            logger.error("Audio processing failed: %s", exc)
            # Fallback: return raw audio without volumes
            return TTSResult(
                audio_wav_base64=audio_base64,
                emotion=emo,
                text=text,
            )

        return TTSResult(
            audio_wav_base64=wav_b64,
            volumes=volumes,
            duration_ms=duration_ms,
            emotion=emo,
            text=text,
        )

    async def synthesize_sentences(
        self,
        sentences: list[tuple[str, str]],  # [(text, emotion), ...]
    ) -> list[TTSResult]:
        """Synthesize multiple sentences in parallel if possible."""
        if not sentences:
            return []
        # Process sequentially to keep audio order, but could parallelize per sentence
        tasks = [
            self.synthesize(text, emotion)
            for text, emotion in sentences
        ]
        return await asyncio.gather(*tasks)


class GPTSoVITSTTSService:
    """GPT-SoVITS HTTP API adapter.

    The local GPT-SoVITS server should be started separately, for example:
    python api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml
    """

    def __init__(
        self,
        api_url: str = "http://127.0.0.1:9880",
        ref_audio_path: str = "./data/voice/luoying/gentle.wav",
        prompt_text: str = "",
        prompt_lang: str = "zh",
        text_lang: str = "zh",
        speed_factor: float = 1.0,
        streaming_mode: int = 0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.ref_audio_path = str(Path(ref_audio_path).resolve())
        self.prompt_text = prompt_text
        self.prompt_lang = prompt_lang
        self.text_lang = text_lang
        self.speed_factor = speed_factor
        self.streaming_mode = streaming_mode
        self._client = client
        self._owns_client = client is None
        self._warmed_up = False

    async def _warmup(self) -> None:
        """GPT-SoVITS v2 first call is silent on CPU; warm up with a short request."""
        if self._warmed_up:
            return
        self._warmed_up = True
        try:
            payload = {
                "text": "嗯",
                "text_lang": self.text_lang,
                "ref_audio_path": self.ref_audio_path,
                "prompt_text": self.prompt_text,
                "prompt_lang": self.prompt_lang,
                "text_split_method": "cut5",
                "batch_size": 1,
                "media_type": "wav",
                "speed_factor": self.speed_factor,
                "streaming_mode": 0,
            }
            await self.client.post(f"{self.api_url}/tts", json=payload)
            logger.info("GPT-SoVITS warmup complete")
        except Exception as exc:
            logger.warning("GPT-SoVITS warmup failed: %s", exc)

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0), trust_env=False)
        return self._client

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def available(self) -> bool:
        return bool(self.api_url and Path(self.ref_audio_path).exists())

    def _reference_for_emotion(self, emotion: str) -> tuple[str, str]:
        base = Path(self.ref_audio_path)
        mood = "serious" if emotion == "angry" else emotion
        candidate = base.with_name(f"{mood}.wav")
        if candidate.exists():
            prompt_key = "angry" if mood == "serious" else mood
            return str(candidate.resolve()), GPT_SOVITS_PROMPTS.get(prompt_key, self.prompt_text)
        return self.ref_audio_path, self.prompt_text

    @staticmethod
    def _compute_volumes_from_raw(raw_data: bytes, sample_width: int = 2, chunk_ms: int = 20, frame_rate: int = 24000) -> list[float]:
        import struct, math
        samples_per_chunk = int(frame_rate * chunk_ms / 1000)
        bytes_per_chunk = samples_per_chunk * sample_width
        rms_values = []
        for i in range(0, len(raw_data) - bytes_per_chunk + 1, bytes_per_chunk):
            chunk = raw_data[i:i + bytes_per_chunk]
            n = len(chunk) // sample_width
            if n == 0:
                rms_values.append(0.0)
                continue
            samples = struct.unpack(f'<{n}h', chunk)
            rms = math.sqrt(sum(s * s for s in samples) / n)
            rms_values.append(rms)
        if not rms_values or max(rms_values) == 0:
            return [0.0] * len(rms_values)
        max_val = max(rms_values)
        return [round(v / max_val, 4) for v in rms_values]

    async def synthesize(self, text: str, emotion: str = "") -> TTSResult:
        clean = text.strip()
        emo = emotion or getattr(settings, "tts_default_emotion", "gentle")
        if not clean or not self.available:
            return TTSResult(audio_wav_base64="", emotion=emo, text=text)

        await self._warmup()

        ref_audio_path, prompt_text = self._reference_for_emotion(emo)
        payload = {
            "text": clean,
            "text_lang": self.text_lang,
            "ref_audio_path": ref_audio_path,
            "prompt_text": prompt_text,
            "prompt_lang": self.prompt_lang,
            "text_split_method": "cut5",
            "batch_size": 1,
            "media_type": "wav",
            "speed_factor": self.speed_factor,
            "streaming_mode": self.streaming_mode,
        }

        try:
            resp = await self.client.post(f"{self.api_url}/tts", json=payload)
            resp.raise_for_status()
            wav_bytes = resp.content
            # Parse WAV for volumes and metadata (bypass pydub — it corrupts audio on Windows)
            try:
                import wave as wave_mod
                with BytesIO(wav_bytes) as buf:
                    with wave_mod.open(buf, "rb") as wf:
                        raw = wf.readframes(wf.getnframes())
                        sr = wf.getframerate()
                        duration_ms = int(wf.getnframes() / sr * 1000)
                        volumes = self._compute_volumes_from_raw(raw, wf.getsampwidth(), 20, sr)
            except Exception:
                volumes = []
                duration_ms = 0
                sr = 24000
            wav_b64 = base64.b64encode(wav_bytes).decode("utf-8")
            return TTSResult(
                audio_wav_base64=wav_b64,
                sample_rate=sr,
                volumes=volumes,
                duration_ms=duration_ms,
                emotion=emo,
                text=clean,
            )
        except Exception as exc:
            detail = ""
            response = getattr(exc, "response", None)
            if response is not None:
                detail = getattr(response, "text", "")[:300]
            logger.error("GPT-SoVITS synthesis failed: %s %s", exc, detail)
            return TTSResult(audio_wav_base64="", emotion=emo, text=clean)

    async def synthesize_sentences(
        self,
        sentences: list[tuple[str, str]],
    ) -> list[TTSResult]:
        results: list[TTSResult] = []
        for text, emotion in sentences:
            results.append(await self.synthesize(text, emotion))
        return results


def create_tts_service() -> VolcanoTTSService | GPTSoVITSTTSService:
    provider = getattr(settings, "tts_provider", "volcano").strip().lower()
    if provider in {"gpt_sovits", "gpt-sovits", "sovits"}:
        return GPTSoVITSTTSService(
            api_url=settings.gpt_sovits_api_url,
            ref_audio_path=settings.gpt_sovits_ref_audio_path,
            prompt_text=settings.gpt_sovits_prompt_text,
            prompt_lang=settings.gpt_sovits_prompt_lang,
            text_lang=settings.gpt_sovits_text_lang,
            speed_factor=settings.gpt_sovits_speed_factor,
            streaming_mode=settings.gpt_sovits_streaming_mode,
        )
    return VolcanoTTSService(
        voice_type=settings.tts_voice_type,
        default_emotion=settings.tts_default_emotion,
    )
