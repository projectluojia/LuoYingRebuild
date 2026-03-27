from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from luoying_bot.constants import quick_replies as default_quick_replies
from luoying_bot.domain.context import ChatContext

class QuickReplyService:
    def __init__(self,path: Path | None =None):
        self.path = Path(path) if path else None
        self._rules:list[dict] = []
        self._last_mtime: float | None = None
        self._load_rules(force=True)
    def _load_rules(self,force:bool = False)->None:
        if self.path is None:
            self._rules = list(default_quick_replies)
            return
        
        if not self.path.exists():
            self._rules=list(default_quick_replies)
            self._last_mtime=None
            return

        mtime=self.path.stat().st_mtime
        if not force and self._last_mtime == mtime:
            return
        
        with self.path.open('r',encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data,list):
            raise ValueError('quick reply 配置文件必须是 list')
        
        self._rules=data
        self._last_mtime=mtime

    def match(self,text:str,context:ChatContext|None=None)->Optional[str]:
        try:
            self._load_rules(force=False)
        except Exception as e:
            pass
        
        text=(text or "").strip()

        if not text:
            return None
        
        group_id = None
        if context is not None and context.target is not None:
            group_id = str(context.target.conversation_id or "")        

        for rule in self._rules:
            trigger=str(rule.get("trigger","")).strip()
            reply=str(rule.get("reply","")).strip()
            enabled_groups = rule.get("enabled_groups")

            if not trigger or not reply:
                continue

            if enabled_groups:
                enabled_groups = {str(x) for x in enabled_groups}
                if group_id not in enabled_groups:
                    continue

            if text == trigger:
                return reply
            
        return None
        