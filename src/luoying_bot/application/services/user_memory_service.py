from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from memobase import AsyncMemoBaseClient, ChatBlob

logger = logging.getLogger(__name__)

_SAFE_MEMOBASE_USER_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")


@dataclass
class UserMemoryResult:
    ok:bool
    text:str
    data:dict


class UserMemoryService:
    def __init__(
        self,
        *,
        api_key: str,
        project_url: str,
        max_context_tokens: int = 1000,
        write_sync: bool = False,
    ):
        self.enabled = bool((api_key or "").strip())
        self.max_context_tokens = max_context_tokens
        self.write_sync = write_sync
        self.client = (
            AsyncMemoBaseClient(api_key=api_key, project_url=project_url)
            if self.enabled
            else None
        )

    def _memobase_user_id(self, user_id: str) -> str:
        cleaned = _SAFE_MEMOBASE_USER_ID_RE.sub("_", str(user_id or "").strip())
        cleaned = cleaned.strip("_") or "unknown"
        return f"luoying_{cleaned}"

    async def _get_user(self, user_id: str):
        if not self.client:
            return None
        memobase_user_id = self._memobase_user_id(user_id)
        try:
            return await self.client.get_user(memobase_user_id)
        except Exception:
            await self.client.add_user(
                data={"source": "luoying", "app_user_id": str(user_id)},
                id=memobase_user_id,
            )
            return await self.client.get_user(memobase_user_id, no_get=True)

    async def get_memory(self,user_id:str)->UserMemoryResult:
        if not self.enabled:
            return UserMemoryResult(False, "Memobase 未配置：请设置 MEMOBASE_API_KEY", {})
        memobase_user_id = self._memobase_user_id(user_id)
        try:
            user = await self._get_user(user_id)
            content = await user.context(max_token_size=self.max_context_tokens)
        except Exception as exc:
            logger.exception(
                "读取 Memobase 长期记忆失败：user_id=%s memobase_user_id=%s",
                user_id,
                memobase_user_id,
            )
            return UserMemoryResult(False, f"读取长期记忆失败：{type(exc).__name__}: {exc}", {})
        if not content:
            return UserMemoryResult(True, "当前没有长期记忆", {"memory": ""})
        return UserMemoryResult(True,content,{"memory":content})

    async def set_memory(self,user_id:str,content:str)->UserMemoryResult:
        if not self.enabled:
            return UserMemoryResult(False, "Memobase 未配置：请设置 MEMOBASE_API_KEY", {})
        memobase_user_id = self._memobase_user_id(user_id)
        content = (content or "").strip()

        if not content:
            return UserMemoryResult(False,"记忆内容不能为空",{})
        try:
            user = await self._get_user(user_id)
            profile_id = await user.add_profile(
                content=content,
                topic="explicit_memory",
                sub_topic="user_requested",
            )
        except Exception as exc:
            logger.exception(
                "写入 Memobase 长期记忆失败：user_id=%s memobase_user_id=%s",
                user_id,
                memobase_user_id,
            )
            return UserMemoryResult(False, f"写入长期记忆失败：{type(exc).__name__}: {exc}", {})
        return UserMemoryResult(True, "已写入长期记忆", {"memory": content, "profile_id": profile_id})

    async def clear_memory(self, user_id: str) -> UserMemoryResult:
        if not self.enabled:
            return UserMemoryResult(False, "Memobase 未配置：请设置 MEMOBASE_API_KEY", {})
        memobase_user_id = self._memobase_user_id(user_id)
        try:
            try:
                await self.client.delete_user(memobase_user_id)
            except Exception:
                logger.info(
                    "Memobase 用户不存在或删除失败，将尝试重新创建：user_id=%s memobase_user_id=%s",
                    user_id,
                    memobase_user_id,
                )
            await self.client.add_user(
                data={"source": "luoying", "app_user_id": str(user_id)},
                id=memobase_user_id,
            )
        except Exception as exc:
            logger.exception(
                "清空 Memobase 长期记忆失败：user_id=%s memobase_user_id=%s",
                user_id,
                memobase_user_id,
            )
            return UserMemoryResult(False, f"清空长期记忆失败：{type(exc).__name__}: {exc}", {})
        return UserMemoryResult(True, "已清空长期记忆", {})

    async def build_prompt_block(self, user_id: str, latest_user_text: str = "") -> str:
        if not self.enabled:
            return "（暂无该用户长期记忆）"
        memobase_user_id = self._memobase_user_id(user_id)
        try:
            user = await self._get_user(user_id)
            chats = (
                [{"role": "user", "content": latest_user_text}]
                if latest_user_text.strip()
                else None
            )
            content = await user.context(
                max_token_size=self.max_context_tokens,
                chats=chats,
            )
        except Exception:
            logger.exception(
                "构建 Memobase 长期记忆上下文失败：user_id=%s memobase_user_id=%s",
                user_id,
                memobase_user_id,
            )
            return "（长期记忆暂时不可用）"
        return content.strip() if content and content.strip() else "（暂无该用户长期记忆）"

    async def record_turn(
        self,
        *,
        user_id: str,
        user_text: str,
        assistant_text: str,
    ) -> None:
        if not self.enabled:
            return
        user_text = (user_text or "").strip()
        assistant_text = (assistant_text or "").strip()
        if not user_text and not assistant_text:
            return
        memobase_user_id = self._memobase_user_id(user_id)
        try:
            user = await self._get_user(user_id)
            await user.insert(
                ChatBlob(
                    messages=[
                        {"role": "user", "content": user_text},
                        {"role": "assistant", "content": assistant_text},
                    ]
                ),
                sync=self.write_sync,
            )
            await user.flush(sync=self.write_sync)
        except Exception:
            logger.exception(
                "写入 Memobase 对话记忆失败：user_id=%s memobase_user_id=%s",
                user_id,
                memobase_user_id,
            )
    
    
