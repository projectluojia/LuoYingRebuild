from __future__ import annotations

from pathlib import Path
from luoying_bot.config import settings

class TextUserMemoryRepo:
    def __init__(self,memory_dir:Path | None = None ):
        self.memory_dir=memory_dir or settings.user_memory_dir
        self.memory_dir.mkdir(parents=True,exist_ok=True)

    def _path(self,user_id:str)->Path:
        return self.memory_dir / f"{user_id}.txt"

    def get(self,user_id:str)->str:
        path = self._path(user_id)
        if not path.exists():
            return ""

        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""
    
    def set(self,user_id:str,content:str)->None:
        path=self._path(user_id)
        path.write_text((content or "").strip(),encoding="utf-8")

    def clear(self,user_id:str)->None:
        path=self._path(user_id)
        if path.exists():
            path.unlink()

