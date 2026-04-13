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
    platform = [Platform.QQ, Platform.WEB]
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
            print(f"编程子Agent：任务内容为空")
            return SkillResult(text="没有收到编程任务内容")
        print(f"编程子Agent：{instruction}")

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
            print(f"编程子Agent：列出脚本被调用了")
            result = script_service.list_scripts(user_id)
            return result.text

        @tool
        def read_script(file_path: str) -> str:
            """读取指定脚本文件的完整内容。
            需要一个参数
            file_path:str 是当前工作区下要读取的脚本的相对路径， 例如 hello.py 或 src/main.rs。
            返回读取的脚本的内容
            """
            print(f"编程子Agent：读取脚本被调用了")
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
            print(f"编程子Agent：创建脚本被调用了")
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
            print(f"编程子Agent：覆写脚本被调用了")
            result = script_service.write_script(user_id, file_path, content, overwrite=True)
            return result.text

        @tool
        def delete_script(file_path: str) -> str:
            """删除指定脚本文件。
            需要一个参数
            file_path:str 是当前工作区下要删除的脚本的相对路径
            返回删除的情况
            """
            
            print(f"编程子Agent：删除脚本被调用了")
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
            print(f"编程子Agent：运行脚本被调用了")
            result = await script_service.run_python_script(user_id, file_path, args=canshu)
            if result.data.get("output_written"):
                try:
                    send_result = await script_service.send_script_to_transport(
                        user_id=user_id,
                        file_path=result.data.get("output_file", "_script_out.txt"),
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
            print(f"编程子Agent：发送脚本被调用了")
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
            print(f"编程子Agent：出错 {e}")
            return SkillResult(text=f"编程子agent执行失败：{type(e).__name__}: {e}")

        final_text = self._extract_final_text(state)
        print(f"编程子Agent：结果 {final_text}")
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