from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from luoying_bot.config import settings

class QuickReplyService:
    def __init__(self,path: Path | None =None):
        self.path=path or (settings.data_dir/"quick_replies.json")
    
    def _load_rules(self) -> list[dict]:
        if not self.path.exists():
            return []

        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []
        
    def match(self,text:str)->Optional[str]:
        text=(text or "").strip()

        if not text:
            return None
        
        rules=self._load_rules()

        for rule in rules:
            trigger=str(rule.get("trigger","")).strip()
            reply=str(rule.get("reply","")).strip()

            if not trigger or not reply:
                continue
            if text == trigger:
                return reply
            
        return None
        