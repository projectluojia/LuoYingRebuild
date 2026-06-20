from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from luoying_bot.capabilities.knowledge_base import KnowledgeBaseService
    from luoying_bot.application.services.group_runtime import GroupRuntime
    from luoying_bot.application.services.memo_service import MemoService
    from luoying_bot.application.services.reminder_service import ReminderService
    from luoying_bot.application.services.risk_control_service import RiskControlService
    from luoying_bot.application.services.script_workspace_service import ScriptWorkspaceService
    from luoying_bot.application.services.user_memory_service import UserMemoryService
    from luoying_bot.application.services.user_prompt_settings_service import UserPromptSettingsService
    from luoying_bot.application.services.user_service import UserService
    from luoying_bot.ports.memory import ConversationMemory
    from luoying_bot.ports.transport import ChatTransport


@dataclass(slots=True)
class ServiceHub:
    ops: list[str]
    HELP: str
    LOG: str
    transport: 'ChatTransport'
    runtime: 'GroupRuntime'
    user_service: 'UserService'
    reminder_service: 'ReminderService'
    memo_service: 'MemoService'
    script_workspace_service: 'ScriptWorkspaceService'
    memory: 'ConversationMemory'
    risk_control_service: 'RiskControlService'
    user_memory_service: 'UserMemoryService'
    user_prompt_settings_service: 'UserPromptSettingsService'
    knowledge_base_service: 'KnowledgeBaseService'
