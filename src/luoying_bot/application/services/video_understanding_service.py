from __future__ import annotations

import asyncio
import base64
import io
import mimetypes
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from PIL import Image

from luoying_bot.config import settings


@dataclass(slots=True)
class VideoUnderstandingResult:
    text: str
    frame_count: int
    sampled_timestamps: list[float | None]
    model: str


class VideoUnderstandingService:
    def __init__(self, max_video_bytes: int = 32 * 1024 * 1024, max_frames: int = 6, max_decode_frames: int = 360):
        self.max_video_bytes = max(1, int(max_video_bytes))
        self.max_frames = max(1, int(max_frames))
        self.max_decode_frames = max(self.max_frames, int(max_decode_frames))

    async def describe_video(self, video_bytes: bytes, file_name: str, content_type: str = "") -> VideoUnderstandingResult:
        payload = video_bytes or b""
        if not payload:
            raise ValueError("上传内容为空，未收到视频字节")
        if len(payload) > self.max_video_bytes:
            raise ValueError(f"视频过大，当前上限 {self.max_video_bytes // (1024 * 1024)}MB")

        safe_name = unquote((file_name or "").strip()) or "uploaded_video"
        data_urls, timestamps = await asyncio.to_thread(
            self._extract_frame_data_urls,
            payload,
            safe_name,
            content_type,
        )

        frame_count = len(data_urls)
        if frame_count == 0:
            raise ValueError("视频无法解码为可分析帧")

        model_name, api_key, base_url = self._resolve_vision_model_config()
        if not api_key and not settings.use_local_ollama:
            fallback = (
                f"已收到视频《{safe_name}》，抽取到 {frame_count} 帧。"
                "当前未配置视觉模型 API Key，已完成链路校验但无法给出画面语义结论。"
            )
            return VideoUnderstandingResult(
                text=fallback,
                frame_count=frame_count,
                sampled_timestamps=timestamps,
                model=model_name,
            )

        prompt = (
            "你是视频理解助手。以下图片是同一段视频按时间顺序抽取的关键帧。\n"
            "请用中文输出：\n"
            "1) 画面概述\n"
            "2) 主要对象与动作\n"
            "3) 时间变化（从前到后）\n"
            "4) 可见文字（若有）\n"
            "5) 不确定项（若有）\n"
            "要求：客观、简洁、禁止臆测。"
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        content.extend({"type": "image_url", "image_url": {"url": item}} for item in data_urls)

        try:
            model = ChatOpenAI(
                model=model_name,
                api_key=api_key,
                base_url=base_url,
                temperature=0.2,
            )
            response = await model.ainvoke([HumanMessage(content=content)])
            text = self._extract_content_text(getattr(response, "content", ""))
        except Exception as exc:
            raise RuntimeError(f"视觉模型推理失败：{type(exc).__name__}: {exc}") from exc

        if not text:
            text = "视觉模型已返回，但未产出可读文本结果。"

        return VideoUnderstandingResult(
            text=text,
            frame_count=frame_count,
            sampled_timestamps=timestamps,
            model=model_name,
        )

    def _resolve_vision_model_config(self) -> tuple[str, str, str]:
        if settings.use_local_ollama:
            return (
                settings.ollama_image_model,
                settings.ollama_api_key,
                settings.ollama_base_url,
            )
        return (
            getattr(settings, "image_model", "") or settings.openai_model,
            getattr(settings, "image_api_key", "") or settings.openai_api_key,
            getattr(settings, "image_base_url", "") or settings.openai_base_url,
        )

    def _extract_frame_data_urls(
        self,
        video_bytes: bytes,
        file_name: str,
        content_type: str,
    ) -> tuple[list[str], list[float | None]]:
        try:
            import av  # type: ignore
        except Exception as exc:
            raise RuntimeError("未安装或无法导入 PyAV（av），无法抽帧") from exc

        suffix = self._guess_video_suffix(file_name=file_name, content_type=content_type)
        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(video_bytes)
                temp_path = tmp.name

            try:
                container = av.open(temp_path)
                try:
                    stream = next((item for item in container.streams if item.type == "video"), None)
                    if stream is None:
                        raise ValueError("视频中未找到可用的视频轨")

                    targets = self._build_targets(container=container, stream=stream, sample_count=self.max_frames)
                    data_urls: list[str] = []
                    timestamps: list[float | None] = []
                    first_frame_payload: tuple[str, float | None] | None = None
                    frame_index = 0
                    target_index = 0
                    fallback_stride = max(1, self.max_decode_frames // self.max_frames)

                    for frame in container.decode(stream):
                        frame_index += 1
                        if frame_index > self.max_decode_frames:
                            break

                        timestamp = self._frame_timestamp(frame)
                        image = frame.to_image().convert("RGB")
                        encoded = self._image_to_data_url(image)
                        if first_frame_payload is None:
                            first_frame_payload = (encoded, timestamp)

                        take = False
                        if targets and timestamp is not None:
                            if target_index < len(targets) and timestamp >= targets[target_index]:
                                target_index += 1
                                take = True
                        else:
                            if frame_index == 1 or frame_index % fallback_stride == 0:
                                take = True

                        if take:
                            data_urls.append(encoded)
                            timestamps.append(timestamp)

                        if len(data_urls) >= self.max_frames:
                            break

                    if not data_urls and first_frame_payload is not None:
                        data_urls = [first_frame_payload[0]]
                        timestamps = [first_frame_payload[1]]
                    return data_urls, timestamps
                finally:
                    container.close()
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError(f"视频解析失败：{type(exc).__name__}: {exc}") from exc
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except FileNotFoundError:
                    pass

    def _build_targets(self, container: Any, stream: Any, sample_count: int) -> list[float]:
        duration_sec: float | None = None
        if getattr(stream, "duration", None) is not None and getattr(stream, "time_base", None) is not None:
            try:
                duration_sec = float(stream.duration * stream.time_base)
            except Exception:
                duration_sec = None
        if (duration_sec is None or duration_sec <= 0) and getattr(container, "duration", None):
            try:
                duration_sec = float(container.duration) / 1_000_000.0
            except Exception:
                duration_sec = None

        if duration_sec is None or duration_sec <= 0.2:
            return []
        return [duration_sec * (i + 1) / (sample_count + 1) for i in range(sample_count)]

    def _frame_timestamp(self, frame: Any) -> float | None:
        value = getattr(frame, "time", None)
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

    def _guess_video_suffix(self, file_name: str, content_type: str) -> str:
        suffix = Path(file_name).suffix.lower()
        if suffix in {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}:
            return suffix
        guessed = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip().lower())
        if guessed in {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}:
            return guessed
        return ".mp4"

    def _image_to_data_url(self, image: Image.Image) -> str:
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=82)
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"

    def _extract_content_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
            if parts:
                return "\n".join(parts).strip()
        return str(content).strip()
