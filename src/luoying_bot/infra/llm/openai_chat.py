from __future__ import annotations
import json
from collections.abc import AsyncIterator
from typing import Dict, List
from openai import AsyncOpenAI
from luoying_bot.ports.llm import ChatModel

#模型的调用实现
class OpenAICompatibleChatModel(ChatModel):
    def __init__(
            self, 
            base_url: str, 
            api_key: str, 
            model: str, 
            default_temperature: float = 1.3,
            client: AsyncOpenAI | None = None,
        ):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.default_temperature = default_temperature

        self.client = client or AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=60.0,
            max_retries=2,
        )
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self.client.close()

    async def chat(self, messages: List[Dict[str, str]], temperature: float | None = None) -> str:

        if not self.api_key:
            last_user = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), '')
            return json.dumps(
                {
                    "type": "final",
                    "answer": f" [LLM未配置] 我收到了：{last_user[:120]}",
                },
                ensure_ascii=False,
            )
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.default_temperature if temperature is None else temperature,
        )
        return response.choices[0].message.content or ""

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        if not self.api_key:
            fallback = await self.chat(messages, temperature=temperature)
            for char in fallback:
                yield char
            return

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.default_temperature if temperature is None else temperature,
            stream=True,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if content:
                yield content
