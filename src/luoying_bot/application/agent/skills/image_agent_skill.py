from __future__ import annotations

import base64
import mimetypes
import os
from typing import Any, Optional

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

from luoying_bot.application.agent.skill_base import BaseSkill, SkillRequest, SkillResult
from luoying_bot.config import settings
from luoying_bot.constants import IMAGE_AGENT_SYSTEM_PROMPT

class ImageAgentSkill(BaseSkill):
    name = "image_agent"
    description = (
        "图片识别子agent。用于处理用户消息中的一张或多张图片。"
        "支持：图片描述、OCR文字提取、截图界面识别、多图比较、找差异、按序号分析指定图片、综合回答。"
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
    )

    async def run(self, req: SkillRequest) -> SkillResult:


        instruction = (req.payload.get("instruction") or req.message.get_plain_text() or "").strip()

        if not instruction:
            instruction = "请识别并分析这些图片"

        requested_indexes = self._normalize_indexes(req.payload.get("image_indexes"))
        requested_file_names = self._normalize_file_names(req.payload.get("file_names"))

        images = self._collect_images(req)
        

        print("collect_images:", images)

        if requested_file_names:
            file_name_set = set(requested_file_names)
            images = [img for img in images if img["file_name"] in file_name_set]
        if requested_indexes:
            index_set = set(requested_indexes)
            images = [img for img in images if img["index"] in index_set]
            
        if not images:
            return SkillResult(text="当前消息里没有找到可分析的图片")
        checkpointer = InMemorySaver()
        config: RunnableConfig = {
            "configurable": {
                "thread_id": f"{req.context.thread_id}:image"
            }
        }
        
        @tool
        async def list_current_images() -> str:
            
            """
            列出当前消息中可用的图片。
            无参数。
            返回每张图片的序号与 file_name。
            """
            print("list工具")
            if not images:
                return "当前消息中没有图片"
            lines = ["当前可用图片如下（包括当前消息，以及被回复的那条消息中的图片）："]
            for img in images:
                lines.append(f"{img['index']}. file_name={img['file_name']}")
            return "\n".join(lines)

        @tool
        async def describe_images(
            image_indexes: list[int] | None = None,
            focus: str = "",
        ) -> str:
            
            """
            描述当前消息中的一张或多张图片。

            参数:
            - image_indexes: 要分析的图片序号列表，例如 [1]、[1,2]；不传则默认分析全部图片
            - focus: 可选，描述重点，例如“重点看报错信息”“重点看人物动作”“重点看图中文字” 假如没有要求请不要传参

            返回:
            - 对指定图片的逐张描述
           
            """
            print("describe工具")
            selected = self._pick_images(images, image_indexes)
            if not selected:
                return "没有匹配到要描述的图片序号"

            selected = await self._ensure_local_paths(req, selected)
            if not selected:
                return "图片读取失败，无法获取本地路径"

            parts: list[str] = []
            for img in selected:
                desc = await self._vision_infer(
                    image_path=img["local_path"],
                    prompt=self._build_description_prompt(focus),
                )
                parts.append(f"【第{img['index']}张图片】\n{desc}")
            """
            if len(selected) >= 2:
                summary = await self._summarize_texts(
                    instruction=(
                        "请基于下面这些逐张图片描述，给出一个整体总结。"
                        "如果存在共同点、差异点、先后关系、内容递进，也请指出。"
                    ),
                    texts=parts,
                )
                parts.append(f"【多图整体总结】\n{summary}")
            """
            return "\n\n".join(parts)

        @tool
        async def answer_about_images(
            question: str,
            image_indexes: list[int] | None = None,
        ) -> str:
            
            """
            回答关于当前消息中一张或多张图片的问题。

            参数:
            - question: 用户关于图片的具体问题，例如“这两张图有什么区别”“哪张图有报错”“提取这三张图中的文字”
            - image_indexes: 要分析的图片序号列表，例如 [1,2]；不传则默认分析全部图片

            返回:
            - 对每张图的分析
            - 如果有多张图，再给出综合结论
            """
            print("answer工具")
            selected = self._pick_images(images, image_indexes)
            if not selected:
                return "没有匹配到要分析的图片序号"

            selected = await self._ensure_local_paths(req, selected)
            if not selected:
                return "图片读取失败，无法获取本地路径"

            analyses: list[str] = []
            for img in selected:
                answer = await self._vision_infer(
                    image_path=img["local_path"],
                    prompt=self._build_question_prompt(question, img["index"], len(selected)),
                )
                analyses.append(f"【第{img['index']}张图片分析】\n{answer}")

            if len(selected) == 1:
                return analyses[0]

            final = await self._summarize_texts(
                instruction=(
                    f"用户问题：{question}\n"
                    "下面是多张图片的逐张分析结果。"
                    "请综合这些结果，直接回答用户问题。"
                    "如果问题涉及比较、筛选、排序、找差异、找共同点，请明确指出对应图片序号。"
                    "如果证据不足，请明确说不确定。"
                ),
                texts=analyses,
            )

            return "\n\n".join(analyses + [f"【综合结论】\n{final}"])

        print(111)

        tools = [
            list_current_images,
            describe_images,
            answer_about_images,
        ]

        model = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0.6,
        )

        agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=IMAGE_AGENT_SYSTEM_PROMPT,
            checkpointer=checkpointer,
        )

        try:
            image_list_text = "\n".join(
                f"{img['index']}. file_name={img['file_name']}，来源={img.get('source', 'unknown')}"
                for img in images
            )
            state: dict[str, Any] = await agent.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"用户请求：{instruction}\n"
                                f"当前可用图片共 {len(images)} 张。\n"
                                "图片来源可能有两种：\n"
                                "- current：当前这条消息里的图片\n"
                                "- reply：用户回复的那条消息里的图片\n"
                                f"图片列表如下：\n{image_list_text}\n"
                                "请根据用户问题判断要分析哪张图。"
                                "如果用户是在问他回复的那张图，通常优先关注来源为 reply 的图片。"
                                "请根据需要自行决定是否先列出图片，再分析其中一张、几张或全部图片，最后给出最终答案。"
                            ),
                        }
                    ]
                },
                config=config,
            )
        except Exception as e:
            print(e)
            return SkillResult(text=f"图片子agent执行失败：{type(e).__name__}: {e}")

        final_text = self._extract_final_text(state)

        return SkillResult(
            text=final_text or "图片任务已处理，但没有拿到明确文本结果",
            data={
                "ok": True,
                "instruction": instruction,
                "image_count": len(images),
                "image_files": [img["file_name"] for img in images],
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

        print(images)
        return images
    """
    def _collect_images(self, req: SkillRequest) -> list[dict[str, Any]]:
        images: list[dict[str, Any]] = []
        idx = 1

        def collect_from_message(msg,source:str)->None:



        for seg in req.message.segments:
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
                }
            )
            idx += 1
        print(images)
        return images
    """
        
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
        print("ensure_local_paths result:", ready)
        return ready

    async def _resolve_image_path(self, req: SkillRequest, file_name: str) -> Optional[str]:
        if not file_name:
            return None

        if os.path.isabs(file_name) and os.path.exists(file_name):
            return file_name
        print(f"download_image input: {file_name}")
        transport = self.services["transport"]
        try:
            local_path = await transport.download_image(file_name)
            print(f"download_image output: {local_path}")
            if local_path and os.path.exists(local_path):
                print(f"exists: {os.path.exists(local_path)}")
                return local_path
        except Exception:
            pass

        return None

    async def _vision_infer(self, image_path: str, prompt: str) -> str:
        print(f"_vision_infer image_path:{image_path}")
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
        print(f"_summarize_texts {instruction}")
        try:
            model = ChatOpenAI(
                model=getattr(settings, "image_model", "") or settings.openai_model,
                api_key=getattr(settings, "image_api_key", "") or settings.openai_api_key,
                base_url=getattr(settings, "image_base_url", "") or settings.openai_base_url,
                temperature=0.2,
            )

            prompt = instruction + "\n\n" + "\n\n".join(texts)
            response = await model.ainvoke(prompt)
            return self._extract_content_text(response.content)
        except Exception as e:
            return f"多图综合总结失败: {e}"

    def _build_description_prompt(self, focus: str) -> str:
        print(f"_build_description_prompt focus:{focus} ")
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
        print(f"_build_question_prompt question:{question} image_index:{image_index} total:{total}")
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