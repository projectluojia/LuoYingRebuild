from __future__ import annotations

import logging
from typing import Any

from luoying_bot.domain.context import ChatContext

class _ContextDefaultsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key in ("request_uid", "thread_id", "message_id", "user_id", "conversation_id"):
            if not hasattr(record, key):
                setattr(record, key, "-")
        return True
    
def configure_logging(level: int = logging.INFO)->None:
    if getattr(configure_logging, "_configured", False):
        return
    log_format = (
        "%(asctime)s | %(levelname)s | %(name)s | "
        "req=%(request_uid)s thread=%(thread_id)s msg=%(message_id)s "
        "user=%(user_id)s conv=%(conversation_id)s | %(message)s"
    )
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        logging.basicConfig(level=level, format=log_format)
    for handler in root.handlers:
        handler.addFilter(_ContextDefaultsFilter())

    setattr(configure_logging, "_configured", True)

def context_log_extra(context: ChatContext | None) -> dict[str, Any]:
    if context is None:
        return {
            "request_uid": "-",
            "thread_id": "-",
            "message_id": "-",
            "user_id": "-",
            "conversation_id": "-",
        }

    return {
        "request_uid": context.request_uid or "-",
        "thread_id": context.thread_id,
        "message_id": context.message_id or "-",
        "user_id": context.user.user_id if context.user else "-",
        "conversation_id": context.target.conversation_id if context.target else "-",
    }
