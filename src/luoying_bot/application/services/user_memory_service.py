from __future__ import annotations

from dataclasses import dataclass

@dataclass
class UserMemoryResult:
    ok:bool
    text:str
    data:dict

class UserMemoryService:
    def __init__(self,repo):
        self.repo=repo

    def get_memory(self,user_id:str)->UserMemoryResult:
        content = self.repo.get(user_id)

        if not content:
            return UserMemoryResult(True, "当前没有长期记忆", {"memory": ""})
        return UserMemoryResult(True,content,{"memory":content})

    def set_memory(self,user_id:str,content:str)->UserMemoryResult:
        content = (content or "").strip()

        if not content:
            return UserMemoryResult(False,"记忆内容不能为空",{})
        self.repo.set(user_id, content)
        return UserMemoryResult(True, "已更新长期记忆", {"memory": content})

    def clear_memory(self, user_id: str) -> UserMemoryResult:
        self.repo.clear(user_id)
        return UserMemoryResult(True, "已清空长期记忆", {})

    def build_prompt_block(self, user_id: str) -> str:
        content = self.repo.get(user_id)
        if not content:
            return "（暂无该用户长期记忆）"
        return content
    
    