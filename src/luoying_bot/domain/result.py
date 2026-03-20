from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict

#返回的消息格式
@dataclass(slots=True)
class Reply:
    text: str #文本
    silent: bool = False #是否静默不发出
    metadata: Dict[str, Any] = field(default_factory=dict)
