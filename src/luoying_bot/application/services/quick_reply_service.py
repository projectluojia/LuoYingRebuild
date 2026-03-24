from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from luoying_bot.config import settings
from luoying_bot.constants import quick_replies

class QuickReplyService:
    def __init__(self,path: Path | None =None):
        pass
        
    def match(self,text:str)->Optional[str]:
        text=(text or "").strip()

        if not text:
            return None
        
        rules=quick_replies

        for rule in rules:
            trigger=str(rule.get("trigger","")).strip()
            reply=str(rule.get("reply","")).strip()

            if not trigger or not reply:
                continue
            if text == trigger:
                return reply
            
        return None
        