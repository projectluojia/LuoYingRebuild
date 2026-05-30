from __future__ import annotations

import logging

from typing import Any

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.runnables import RunnableConfig

from luoying_bot.application.agent.skill_base import BaseSkill,SkillRequest,SkillResult
from luoying_bot.config import settings
from luoying_bot.constants import FILE_WORKSPACE_AGENT_SYSTEM_PROMPT
from luoying_bot.domain.context import Platform

logger = logging.getLogger(__name__)

class FileWorkspaceAgentSkill(BaseSkill):
    name = "file_workspace_agent"
    platform = [Platform.QQ, Platform.WEB, Platform.CLI]
    description = (
        "本地文件与脚本工作区处理首选技能。"
        "当用户上传了文件、提到 upload/、工作区、文件树、读取/总结/分析/转换文件、PDF、Word、Excel、PPT、CSV、TXT、Markdown、代码文件，"
        "或要求创建、查看、覆盖、删除、运行脚本时，优先调用此技能。"
        "它可以读取常见文档中的文本、展示工作区树、写任意语言源码、运行 Python 脚本。"
        "不要用 web_search 读取用户上传文件或工作区文件；不要用 image_agent 处理非图片文档。"
        "payload 可传 instruction，若为空则默认使用用户原消息。"
    )

    async def run(self, req: SkillRequest) -> SkillResult:
        script_service = self.services.script_workspace_service
        transport = self.services.transport

        user_id = str(req.context.user.user_id)
        instruction = (req.payload.get("instruction") or req.message.get_plain_text() or "").strip()
        if not instruction:
            logger.warning("文件工作区 Agent 任务内容为空")
            return SkillResult(text="没有收到文件或工作区任务内容")
        logger.info("文件工作区 Agent 开始处理任务：%s", instruction)
        debug_counts = {
            "create_script": 0,
            "overwrite_script": 0,
            "delete_script": 0,
            "read_script": 0,
            "run_python_script": 0,
            "tree": 0,
            "send_script_result": 0,
            "upload_written_script": 0,
        }

        async def debug_track(text: str) -> None:
            try:
                await transport.send_track(req.context, f"[工作区调试] {text}", kind="workspace_debug")
            except Exception:
                logger.debug("发送 workspace debug track 失败", exc_info=True)

        async def upload_written_script(file_path: str, result_text: str) -> str:
            debug_counts["upload_written_script"] += 1
            await debug_track(
                f"自动发送写入文件 #{debug_counts['upload_written_script']}：路径={file_path}"
            )
            try:
                send_result = await script_service.send_script_to_transport(
                    user_id=user_id,
                    file_path=file_path,
                    context=req.context,
                    transport=transport,
                )
            except Exception as e:
                return f"{result_text}\n\n文件自动发送异常：{type(e).__name__}: {e}"
            if not send_result.ok:
                return f"{result_text}\n\n文件自动发送失败：{send_result.text}"
            return f"{result_text}\n{send_result.text}"

        checkpointer=InMemorySaver()
        config:RunnableConfig = {
            "configurable": {
                "thread_id":req.context.thread_id
            }
        }


        @tool
        async def tree() -> str:
            """以树形结构展示当前用户工作区中的全部文件和文件夹。
            无需参数
            返回类似 Windows tree 的工作区目录结构。需要查看有哪些文件时优先使用这个工具。
            """
            debug_counts["tree"] += 1
            await debug_track(
                f"查看工作区树 #{debug_counts['tree']}"
            )
            logger.debug("文件工作区 Agent 调用 tree")
            result = script_service.tree(user_id)
            return result.text

        @tool
        async def read_script(file_path: str) -> str:
            """读取指定文件的文本内容。
            支持普通文本、代码、PDF、Word、Excel、PPT 等常见文件；对二进制或复杂文档会尽量提取可读文本，读取失败会返回失败原因。
            需要一个参数：
            file_path: str，当前工作区下要读取的相对路径，例如 hello.py 或 upload/work.pdf。
            返回文件中提取到的文本内容。
            """
            debug_counts["read_script"] += 1
            await debug_track(
                f"读取脚本 #{debug_counts['read_script']}：路径={file_path}"
            )
            logger.debug("文件工作区 Agent 调用 read_script，file_path=%s", file_path)
            result = script_service.read_script(user_id, file_path)
            return result.text

        @tool
        async def create_script(file_path: str, content: str) -> str:
            """创建新脚本文件；若已存在则不会覆盖。
            需要两个参数
            file_path:str 是当前工作区下要创建的脚本的相对路径，
            content:str 是要写入的内容
            返回脚本创建情况
            """
            debug_counts["create_script"] += 1
            await debug_track(
                f"创建脚本 #{debug_counts['create_script']}：路径={file_path}"
            )
            logger.debug("文件工作区 Agent 调用 create_script，file_path=%s", file_path)
            result = script_service.write_script(user_id, file_path, content, overwrite=False)
            if not result.ok:
                return result.text
            return await upload_written_script(file_path, result.text)

        @tool
        async def overwrite_script(file_path: str, content: str) -> str:
            """覆盖写入脚本文件；文件存在时会直接替换原内容。
            需要两个参数
            file_path:str 是当前工作区下要覆写的脚本的相对路径，
            content:str 是要覆写的内容
            返回覆写情况
            """
            debug_counts["overwrite_script"] += 1
            await debug_track(
                f"覆盖脚本 #{debug_counts['overwrite_script']}：路径={file_path}"
            )
            logger.debug("文件工作区 Agent 调用 overwrite_script，file_path=%s", file_path)
            result = script_service.write_script(user_id, file_path, content, overwrite=True)
            if not result.ok:
                return result.text
            return await upload_written_script(file_path, result.text)

        @tool
        async def delete_script(file_path: str) -> str:
            """删除指定脚本文件。
            需要一个参数
            file_path:str 是当前工作区下要删除的脚本的相对路径
            返回删除的情况
            """
            debug_counts["delete_script"] += 1
            await debug_track(
                f"删除脚本 #{debug_counts['delete_script']}：路径={file_path}"
            )
            logger.debug("文件工作区 Agent 调用 delete_script，file_path=%s", file_path)
            result = script_service.delete_script(user_id, file_path)
            return result.text

        @tool
        async def run_python_script(file_path: str, canshu: str = "") -> str:
            """
            运行指定 Python 脚本
            有一个必填参数
            file_path:str 是当前工作区下要运行的脚本的相对路径
            一个可选参数
            canshu:str 代表命令行参数
            只能运行 .py 文件
            返回运行情况；并自动把 stdout/stderr 发送到当前会话
            """
            debug_counts["run_python_script"] += 1
            await debug_track(
                f"运行脚本 #{debug_counts['run_python_script']}：路径={file_path}，参数={canshu or '无'}"
            )
            logger.debug("文件工作区 Agent 调用 run_python_script，file_path=%s", file_path)
            result = await script_service.run_python_script(user_id, file_path, args=canshu)
            if result.data.get("type") == "script_result":
                try:
                    debug_counts["send_script_result"] += 1
                    await debug_track(
                        f"自动发送运行输出 #{debug_counts['send_script_result']}：路径={file_path}"
                    )
                    await transport.send_script_result(req.context, result.data)
                except Exception as e:
                    return f"{result.text}\n\n运行输出发送异常：{type(e).__name__}: {e}"

            return result.text

        tools = [
            tree,
            read_script,
            create_script,
            overwrite_script,
            delete_script,
            run_python_script,
        ]

        model = ChatOpenAI(
            model=settings.coding_model,
            api_key=settings.coding_api_key,
            base_url=settings.coding_base_url,
            temperature=0.2,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )

        agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=FILE_WORKSPACE_AGENT_SYSTEM_PROMPT,
            checkpointer=checkpointer
        )

        try:
            state: dict[str, Any] = await agent.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": instruction,
                        }
                    ]
                },
                config=config,
            )
        except Exception as e:
            logger.exception("文件工作区 Agent 执行失败")
            return SkillResult(text=f"文件工作区 agent 执行失败：{type(e).__name__}: {e}")

        final_text = self._extract_final_text(state)
        logger.info("文件工作区 Agent 完成处理")
        return SkillResult(
            text=final_text or "文件工作区任务已处理，但没有拿到明确文本结果",
            data={"ok": True, "instruction": instruction},
        )
    
    def _extract_final_text(self, state: dict[str, Any]) -> str:
        messages = state.get("messages") or []
        for msg in reversed(messages):
            content = getattr(msg, "content", None)
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(msg, dict):
                raw = msg.get("content")
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
        return ""
