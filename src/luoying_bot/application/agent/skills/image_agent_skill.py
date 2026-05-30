from __future__ import annotations

import base64
import mimetypes
import os
import logging
import re
from typing import Any, Optional
from urllib.parse import unquote, urlparse

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from luoying_bot.application.agent.skill_base import BaseSkill, SkillRequest, SkillResult
from luoying_bot.config import settings
from luoying_bot.domain.context import Platform

logger = logging.getLogger(__name__)

class ImageAgentSkill(BaseSkill):
    name = "image_agent"
    platform = [Platform.QQ, Platform.WEB, Platform.CLI]
    description = (
        "图片识别子agent。用于处理用户消息中的一张或多张图片。"
        "支持：图片描述、OCR文字提取、截图界面识别、多图比较、找差异、按序号分析指定图片、综合回答。"
        "只处理图片视觉任务；不要用它处理 PDF、Word、Excel、PPT、CSV、Markdown、代码或普通上传文件，这些应优先调用 file_workspace_agent。"
        "\n"
        "适用场景："
        "当用户消息包含图片，或用户在问“这图是什么”“图里写了什么”“帮我看这几张图”"
        "“比较这几张图”“哪张图有问题”“提取图中文字”时优先调用。"
        "\n"
        "payload 字段说明："
        "\n"
        "1. instruction: str，可选。"
        "表示本次图片任务的自然语言指令。"
        "可以根据用户的要求进一步添加重点分析，比如 “分析这张图片，重点看XXX内容”"
        "如果不传，则默认按“请识别并分析这些图片”处理。"
        "\n"
        "2. image_indexes: list[int] | int，可选。"
        "表示只分析当前消息中的第几张图片，序号从 1 开始。"
        "例如：[1] 表示只分析第一张图，[1,3] 表示只分析第1和第3张图。"
        "如果不传，则默认分析当前消息中的全部图片。"
        "\n"
        "3. file_names: list[str] | str，可选。"
        "表示按图片 file_name 精确指定要分析的图片。"
        "适合外部已经拿到了某几张图片 file_name 的情况。"
        "如果同时传了 image_indexes 和 file_names，则先取当前消息图片，再同时按两者过滤。"
        "\n"
        "CLI 下 instruction 可以直接包含本地图片路径或 file:// 本地 URL。"
    )

    _IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")
    _QUOTED_IMAGE_PATH_RE = re.compile(
        r"""["'“”‘’]([^"'“”‘’]+?\.(?:png|jpe?g|webp|bmp|gif|tiff?))["'“”‘’]""",
        re.IGNORECASE,
    )
    _UNQUOTED_IMAGE_PATH_RE = re.compile(
        r"""(?:file://[^\r\n"'<>]+?\.(?:png|jpe?g|webp|bmp|gif|tiff?)|[A-Za-z]:[\\/][^\r\n"'<>]+?\.(?:png|jpe?g|webp|bmp|gif|tiff?)|(?:\.{1,2}[\\/]|/)[^\r\n"'<>]+?\.(?:png|jpe?g|webp|bmp|gif|tiff?))""",
        re.IGNORECASE,
    )

    async def run(self, req: SkillRequest) -> SkillResult:


        instruction = (req.payload.get("instruction") or req.message.get_plain_text() or "").strip()
        transport = self.services.transport

        if not instruction:
            instruction = "请识别并分析这些图片"
        debug_counts = {
            "collect_images": 0,
            "list_current_images": 0,
            "describe_images": 0,
            "answer_about_images": 0,
            "vision_infer": 0,
            "summarize": 0,
        }

        async def debug_track(text: str) -> None:
            try:
                await transport.send_track(req.context, f"[图片调试] {text}", kind="image_debug")
            except Exception:
                logger.debug("发送 image debug track 失败", exc_info=True)

        requested_indexes = self._normalize_indexes(req.payload.get("image_indexes"))
        requested_file_names = self._normalize_file_names(req.payload.get("file_names"))

        images = self._collect_images(req)
        local_path_text = "\n".join(
            text
            for text in (
                instruction,
                req.message.get_plain_text(),
                req.message.to_llm_text(),
            )
            if text
        )
        images.extend(self._collect_instruction_images(local_path_text, start_index=len(images) + 1))
        images = self._dedupe_images(images)
        

        logger.debug("图片子 Agent 收集到图片：%s", images)
        debug_counts["collect_images"] += 1
        await debug_track(
            f"收集图片 #{debug_counts['collect_images']}：共 {len(images)} 张"
        )

        if requested_file_names:
            file_name_set = set(requested_file_names)
            images = [img for img in images if img["file_name"] in file_name_set]
        if requested_indexes:
            index_set = set(requested_indexes)
            images = [img for img in images if img["index"] in index_set]
        if requested_file_names or requested_indexes:
            await debug_track(
                f"筛选图片：剩余 {len(images)} 张，序号={requested_indexes or '全部'}，文件名={requested_file_names or '全部'}"
            )
            
        if not images:
            return SkillResult(text="当前消息里没有找到可分析的图片")

        await debug_track(f"准备图片：选中 {len(images)} 张")
        ready_images = await self._ensure_local_paths(req, images)
        await debug_track(f"准备图片：可读取 {len(ready_images)} 张")
        if not ready_images:
            return SkillResult(text="图片读取失败，无法获取本地路径")

        analyses: list[str] = []
        for img in ready_images:
            debug_counts["vision_infer"] += 1
            await debug_track(
                f"视觉识别 #{debug_counts['vision_infer']}：图片序号={img['index']}，模式=直接分析"
            )
            answer = await self._vision_infer(
                image_path=img["local_path"],
                prompt=self._build_question_prompt(instruction, img["index"], len(ready_images)),
            )
            analyses.append(f"【第{img['index']}张图片分析】\n{answer}")

        if len(analyses) == 1:
            final_text = analyses[0]
        else:
            debug_counts["summarize"] += 1
            await debug_track(
                f"综合总结 #{debug_counts['summarize']}：图片数={len(analyses)}"
            )
            final = await self._summarize_texts(
                instruction=(
                    f"用户问题：{instruction}\n"
                    "下面是多张图片的逐张分析结果。"
                    "请综合这些结果，直接回答用户问题。"
                    "如果问题涉及比较、筛选、排序、找差异、找共同点，请明确指出对应图片序号。"
                    "如果证据不足，请明确说不确定。"
                ),
                texts=analyses,
            )
            final_text = "\n\n".join(analyses + [f"【综合结论】\n{final}"])

        return SkillResult(
            text=final_text,
            data={
                "ok": True,
                "instruction": instruction,
                "image_count": len(ready_images),
                "image_files": [img["file_name"] for img in ready_images],
            },
        )

    def _collect_images(self, req: SkillRequest) -> list[dict[str, Any]]:
        images: list[dict[str, Any]] = []
        idx = 1

        def collect_from_message(msg, source: str) -> None:
            nonlocal idx
            if not msg:
                return
            for seg in msg.segments:
                if seg.type != "image":
                    continue
                file_name = str(seg.data.get("file") or "").strip()
                if not file_name:
                    continue
                images.append(
                    {
                        "index": idx,
                        "file_name": file_name,
                        "local_path": None,
                        "source": source,  # current / reply
                    }
                )
                idx += 1

        collect_from_message(req.message, "current")
        collect_from_message(getattr(req.message, "reply_message", None), "reply")

        logger.debug("当前消息图片列表：%s", images)
        return images

    def _dedupe_images(self, images: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for img in images:
            key = str(img.get("local_path") or img.get("file_name") or "")
            if key and os.path.isabs(key):
                key = os.path.normcase(os.path.abspath(key))
            if key in seen:
                continue
            seen.add(key)
            copied = dict(img)
            copied["index"] = len(result) + 1
            result.append(copied)
        return result

    def _collect_instruction_images(self, instruction: str, start_index: int) -> list[dict[str, Any]]:
        paths = self._extract_local_image_paths(instruction)
        images: list[dict[str, Any]] = []
        for offset, path in enumerate(paths):
            images.append(
                {
                    "index": start_index + offset,
                    "file_name": path,
                    "local_path": path,
                    "source": "instruction",
                }
            )
        if images:
            logger.debug("从 instruction 提取到本地图片：%s", images)
        return images

    def _extract_local_image_paths(self, text: str) -> list[str]:
        if not text:
            return []

        candidates: list[str] = []
        candidates.extend(match.group(1) for match in self._QUOTED_IMAGE_PATH_RE.finditer(text))
        candidates.extend(match.group(0) for match in self._UNQUOTED_IMAGE_PATH_RE.finditer(text))

        paths: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            path = self._normalize_local_image_path(candidate)
            if not path:
                continue
            key = os.path.normcase(os.path.abspath(path))
            if key in seen:
                continue
            seen.add(key)
            paths.append(path)
        return paths

    def _normalize_local_image_path(self, raw_path: str) -> str | None:
        path = str(raw_path or "").strip().strip("\"'“”‘’")
        path = path.rstrip(".,;:，。；：)]}）】")
        if not path:
            return None

        if path.lower().startswith("file:"):
            parsed = urlparse(path)
            if parsed.scheme.lower() != "file":
                return None
            file_path = unquote(parsed.path or "")
            if parsed.netloc:
                file_path = f"//{parsed.netloc}{file_path}"
            if re.match(r"^/[A-Za-z]:[\\/]", file_path):
                file_path = file_path[1:]
            path = file_path

        if not path.lower().endswith(self._IMAGE_EXTENSIONS):
            return None

        full_path = path if os.path.isabs(path) else os.path.abspath(path)
        if not os.path.isfile(full_path):
            logger.debug("instruction 中的图片路径不存在或不是文件：%s", full_path)
            return None
        return full_path
        
    def _normalize_indexes(self, value: Any) -> list[int]:
        if value is None:
            return []
        if isinstance(value, int):
            return [value] if value > 0 else []
        if isinstance(value, list):
            result: list[int] = []
            for item in value:
                try:
                    num = int(item)
                    if num > 0:
                        result.append(num)
                except Exception:
                    pass
            return result
        return []

    def _normalize_file_names(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            v = value.strip()
            return [v] if v else []
        if isinstance(value, list):
            result: list[str] = []
            for item in value:
                s = str(item).strip()
                if s:
                    result.append(s)
            return result
        return []

    def _pick_images(
        self,
        images: list[dict[str, Any]],
        image_indexes: Optional[list[int]],
    ) -> list[dict[str, Any]]:
        if not image_indexes:
            return images[:]
        index_set = set(image_indexes)
        return [img for img in images if img["index"] in index_set]

    async def _ensure_local_paths(
        self,
        req: SkillRequest,
        selected: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        ready: list[dict[str, Any]] = []
        for img in selected:
            if img.get("local_path") and os.path.exists(img["local_path"]):
                ready.append(img)
                continue

            local_path = await self._resolve_image_path(req, img["file_name"])
            if not local_path:
                continue

            copied = dict(img)
            copied["local_path"] = local_path
            ready.append(copied)
        logger.debug("图片本地路径准备结果：%s", ready)
        return ready

    async def _resolve_image_path(self, req: SkillRequest, file_name: str) -> Optional[str]:
        if not file_name:
            return None

        if os.path.isabs(file_name) and os.path.exists(file_name):
            return file_name
        logger.debug("准备通过 transport 下载图片：%s", file_name)
        transport = self.services.transport
        try:
            local_path = await transport.download_image(file_name)
            logger.debug("transport 下载图片返回：%s", local_path)
            if local_path and os.path.exists(local_path):
                logger.debug("图片本地路径存在：%s", local_path)
                return local_path
        except Exception:
            logger.exception("通过 transport 下载图片失败")

        return None

    async def _vision_infer(self, image_path: str, prompt: str) -> str:
        logger.debug("开始图片视觉推理，image_path=%s", image_path)
        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = "image/jpeg"

        try:
            with open(image_path, "rb") as f:
                base64_image = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            return f"读取图片信息失败: {e}"

        image_data_url = f"data:{mime_type};base64,{base64_image}"

        try:
            model = ChatOpenAI(
                model=getattr(settings, "image_model", "") or settings.openai_model,
                api_key=getattr(settings, "image_api_key", "") or settings.openai_api_key,
                base_url=getattr(settings, "image_base_url", "") or settings.openai_base_url,
                temperature=0.2,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )

            message = [
                HumanMessage(
                    content=[
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ]
                )
            ]

            response = await model.ainvoke(message)
            return self._extract_content_text(response.content)
        except Exception as e:
            return f"生成图片分析失败: {e}"

    async def _summarize_texts(self, instruction: str, texts: list[str]) -> str:
        logger.debug("开始多图综合总结，instruction=%s", instruction)
        try:
            model = ChatOpenAI(
                model=getattr(settings, "image_model", "") or settings.openai_model,
                api_key=getattr(settings, "image_api_key", "") or settings.openai_api_key,
                base_url=getattr(settings, "image_base_url", "") or settings.openai_base_url,
                temperature=0.2,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )

            prompt = instruction + "\n\n" + "\n\n".join(texts)
            response = await model.ainvoke(prompt)
            return self._extract_content_text(response.content)
        except Exception as e:
            return f"多图综合总结失败: {e}"

    def _build_description_prompt(self, focus: str) -> str:
        logger.debug("构建图片描述 prompt，focus=%s", focus)
        extra = f"\n额外关注点：{focus}" if focus else ""
        return f"""你是一个专业的图片描述助手，请对用户提供的图片进行全面、细致、结构化描述。

要求：
1. 客观中立，只描述看到的内容，不要臆测未知信息
2. 先整体，再局部
3. 如果图片中有文字、界面、报错、按钮、标题，请尽量准确提取
4. 如果看不清，请明确说不确定
5. 输出尽量清晰有条理{extra}

请开始描述这张图片。"""

    def _build_question_prompt(self, question: str, image_index: int, total: int) -> str:
        logger.debug(
            "构建图片问答 prompt，question=%s image_index=%s total=%s",
            question,
            image_index,
            total,
        )
        return f"""请基于这张图片回答问题。

上下文：
- 这是一组图片中的第 {image_index} 张
- 本次共需分析 {total} 张图片

要求：
1. 只依据图片中可观察到的内容回答
2. 如果图片里有文字，尽量准确提取
3. 如果看不清就说不确定
4. 回答时注意这张图可能会被用于后续多图比较

用户问题：
{question}
"""

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

    def _extract_final_text(self, state: dict[str, Any]) -> str:
        messages = state.get("messages") or []
        for msg in reversed(messages):
            content = getattr(msg, "content", None)
            text = self._extract_content_text(content)
            if text:
                return text

            if isinstance(msg, dict):
                raw = msg.get("content")
                text = self._extract_content_text(raw)
                if text:
                    return text

        return ""
