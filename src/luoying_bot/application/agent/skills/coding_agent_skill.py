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
from luoying_bot.constants import CODING_AGENT_SYSTEM_PROMPT
from luoying_bot.domain.context import Platform

logger = logging.getLogger(__name__)

class CodingAgentSkill(BaseSkill):
    name = "coding_agent"
    platform = [Platform.QQ, Platform.WEB, Platform.CLI]
    description = (
        "编程子agent。适合创建、查看、列出、删除、覆盖、发送脚本文件，"
        "支持写 Python/Rust/C++/C/Java/JS 等任意语言源码；"
        "支持运行 Python 脚本。"
        "payload 可传 instruction，若为空则默认使用用户原消息。"
    )

    async def run(self, req: SkillRequest) -> SkillResult:
        script_service = self.services.script_workspace_service
        transport = self.services.transport

        user_id = str(req.context.user.user_id)
        instruction = (req.payload.get("instruction") or req.message.get_plain_text() or "").strip()
        if not instruction:
            logger.warning("编程子 Agent 任务内容为空")
            return SkillResult(text="没有收到编程任务内容")
        logger.info("编程子 Agent 开始处理任务：%s", instruction)
        debug_counts = {
            "create_script": 0,
            "overwrite_script": 0,
            "run_python_script": 0,
            "auto_send_output": 0,
            "send_script": 0,
        }

        async def debug_track(text: str) -> None:
            try:
                await transport.send_track(req.context, f"[coding-debug] {text}", kind="coding_debug")
            except Exception:
                logger.debug("发送 coding debug track 失败", exc_info=True)

        checkpointer=InMemorySaver()
        config:RunnableConfig = {
            "configurable": {
                "thread_id":req.context.thread_id
            }
        }


        @tool
        def list_scripts() -> str:
            """列出当前用户工作区中的所有脚本文件。
            无需参数
            返回该用户所有脚本
            """
            logger.debug("编程子 Agent 调用 list_scripts")
            result = script_service.list_scripts(user_id)
            return result.text

        @tool
        def read_script(file_path: str) -> str:
            """读取指定脚本文件的完整内容。
            需要一个参数
            file_path:str 是当前工作区下要读取的脚本的相对路径， 例如 hello.py 或 src/main.rs。
            返回读取的脚本的内容
            """
            logger.debug("编程子 Agent 调用 read_script，file_path=%s", file_path)
            result = script_service.read_script(user_id, file_path)
            return result.text

        @tool
        def create_script(file_path: str, content: str) -> str:
            """创建新脚本文件；若已存在则不会覆盖。
            需要两个参数
            file_path:str 是当前工作区下要创建的脚本的相对路径，
            content:str 是要写入的内容
            返回脚本创建情况
            """
            debug_counts["create_script"] += 1
            logger.debug("编程子 Agent 调用 create_script，file_path=%s", file_path)
            result = script_service.write_script(user_id, file_path, content, overwrite=False)
            return result.text

        @tool
        def overwrite_script(file_path: str, content: str) -> str:
            """覆盖写入脚本文件；文件存在时会直接替换原内容。
            需要两个参数
            file_path:str 是当前工作区下要覆写的脚本的相对路径，
            content:str 是要覆写的内容
            返回覆写情况
            """
            debug_counts["overwrite_script"] += 1
            logger.debug("编程子 Agent 调用 overwrite_script，file_path=%s", file_path)
            result = script_service.write_script(user_id, file_path, content, overwrite=True)
            return result.text

        @tool
        def delete_script(file_path: str) -> str:
            """删除指定脚本文件。
            需要一个参数
            file_path:str 是当前工作区下要删除的脚本的相对路径
            返回删除的情况
            """
            
            logger.debug("编程子 Agent 调用 delete_script，file_path=%s", file_path)
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
            返回运行情况；并自动把 _script_out.txt 发送到当前会话
            """
            debug_counts["run_python_script"] += 1
            await debug_track(
                f"run_python_script #{debug_counts['run_python_script']} file_path={file_path} args={canshu or '(none)'}"
            )
            logger.debug("编程子 Agent 调用 run_python_script，file_path=%s", file_path)
            result = await script_service.run_python_script(user_id, file_path, args=canshu)
            if result.data.get("output_written"):
                try:
                    debug_counts["auto_send_output"] += 1
                    output_file = result.data.get("output_file", "_script_out.txt")
                    await debug_track(
                        f"auto_send_output #{debug_counts['auto_send_output']} file_path={output_file}"
                    )
                    send_result = await script_service.send_script_to_transport(
                        user_id=user_id,
                        file_path=output_file,
                        context=req.context,
                        transport=transport,
                    )
                except Exception as e:
                    return f"{result.text}\n\n运行输出文件发送异常：{type(e).__name__}: {e}"

                if send_result.ok:
                    return f"{result.text}\n\n已自动发送运行输出文件：{result.data.get('output_file', '_script_out.txt')}"
                return f"{result.text}\n\n运行输出文件发送失败：{send_result.text}"

            return result.text

        @tool
        async def send_script(file_path: str) -> str:
            """把指定脚本文件发送到当前聊天会话。
            需要一个参数           
            file_path:str 是当前工作区下要发送的脚本的相对路径
            返回发送情况
            """
            debug_counts["send_script"] += 1
            await debug_track(f"send_script #{debug_counts['send_script']} file_path={file_path}")
            logger.debug("编程子 Agent 调用 send_script，file_path=%s", file_path)
            result = await script_service.send_script_to_transport(
                user_id=user_id,
                file_path=file_path,
                context=req.context,
                transport=transport,
            )
            return result.text

        tools = [
            list_scripts,
            read_script,
            create_script,
            overwrite_script,
            delete_script,
            run_python_script,
            send_script,
        ]

        model = ChatOpenAI(
            model=settings.coding_model,
            api_key=settings.coding_api_key,
            base_url=settings.coding_base_url,
            temperature=0.2,
        )

        agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=CODING_AGENT_SYSTEM_PROMPT,
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
            logger.exception("编程子 Agent 执行失败")
            return SkillResult(text=f"编程子agent执行失败：{type(e).__name__}: {e}")

        final_text = self._extract_final_text(state)
        logger.info("编程子 Agent 完成处理")
        return SkillResult(
            text=final_text or "编程任务已处理，但没有拿到明确文本结果",
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
