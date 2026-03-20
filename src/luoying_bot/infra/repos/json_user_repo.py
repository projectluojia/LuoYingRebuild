from __future__ import annotations
import json
from pathlib import Path
from threading import Lock
from typing import Optional
from luoying_bot.ports.repos import UserProfile, UserRepo

#负责存取用户仓库
#要换sqlite直接重写这个
class JsonUserRepo(UserRepo):
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        if not self.path.exists():
            self.path.write_text('{}', encoding='utf-8')

    def _read(self) -> dict:
        return json.loads(
            self.path.read_text(encoding='utf-8')
        )
    
    def _write(self, data: dict) -> None:
        tmp = self.path.with_suffix(self.path.suffix + '.tmp')

        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(self.path)

    def get(self, user_id: str) -> Optional[UserProfile]:
        row = self._read().get(user_id)
        return UserProfile(user_id=user_id, **row) if row else None
    
    def create(self, profile: UserProfile) -> None:
        with self._lock:
            data = self._read()
            if profile.user_id in data:
                raise ValueError('User already exist')
            
            data[profile.user_id] = {
                'department': profile.department, 
                'college': profile.college, 
                'year': profile.year, 
                'name': profile.name
            }
            self._write(data)

    def update_fields(self, user_id: str, **fields: str | None) -> None:
        with self._lock:
            data = self._read()
            if user_id not in data:
                raise ValueError('User not exist')
            for key, value in fields.items():
                if value is not None:
                    data[user_id][key] = value
            self._write(data)
            
    def delete(self, user_id: str) -> bool:
        with self._lock:
            data = self._read()
            existed = user_id in data
            if existed:
                del data[user_id]
                self._write(data)
            return existed
