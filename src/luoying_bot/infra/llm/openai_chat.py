from __future__ import annotations
import json
from collections.abc import AsyncIterator
from typing import Dict, List
import httpx
from luoying_bot.ports.llm import ChatModel

#模型的调用实现
class OpenAICompatibleChatModel(ChatModel):
    def __init__(
            self, 
            base_url: str, 
            api_key: str, 
            model: str, 
            default_temperature: float = 1.3,
            client: httpx.AsyncClient | None = None,
        ):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.default_temperature = default_temperature

        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

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
        
        #这是payload
        payload = {
            'model': self.model, 
            'messages': messages, 
            'temperature': self.default_temperature if temperature is None else temperature
        }
        #这是headers
        headers = {
            'Authorization': f'Bearer {self.api_key}', 
            'Content-Type': 'application/json'
        }

        resp = await self.client.post(
            f'{self.base_url}/chat/completions',
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return data['choices'][0]['message']['content']
        """
        async with httpx.AsyncClient(timeout=60) as client:
            #别问这是啥，问就是我也不懂，面向CV编程
            resp = await client.post(f'{self.base_url}/chat/completions', json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data['choices'][0]['message']['content']
"""

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

        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': self.default_temperature if temperature is None else temperature,
            'stream': True,
        }
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

        async with self.client.stream(
            'POST',
            f'{self.base_url}/chat/completions',
            json=payload,
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith('data:'):
                    line = line.removeprefix('data:').strip()
                if line == '[DONE]':
                    break
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                choices = data.get('choices') or []
                if not choices:
                    continue

                delta = choices[0].get('delta') or {}
                content = delta.get('content')
                if content:
                    yield content
