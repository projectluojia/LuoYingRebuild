from __future__ import annotations
from typing import Dict, List
import httpx
from luoying_bot.ports.llm import ChatModel

#模型的调用实现
class OpenAICompatibleChatModel(ChatModel):
    def __init__(self, base_url: str, api_key: str, model: str, default_temperature: float = 1.3):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.default_temperature = default_temperature

    async def chat(self, messages: List[Dict[str, str]], temperature: float | None = None) -> str:

        if not self.api_key:
            last_user = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), '')
            return f'{{"mode":"direct","answer":" [LLM未配置] 我收到了：{last_user[:120]}"}}'
        
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

        async with httpx.AsyncClient(timeout=60) as client:
            #别问这是啥，问就是我也不懂，面向CV编程
            resp = await client.post(f'{self.base_url}/chat/completions', json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data['choices'][0]['message']['content']
