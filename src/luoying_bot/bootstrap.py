from __future__ import annotations

from dataclasses import dataclass

from luoying_bot.application.agent.agent_service import AgentService
from luoying_bot.application.agent.skill_registry import SkillRegistry
from luoying_bot.application.commands.dispatcher import CommandDispatcher
from luoying_bot.application.event_handler import EventHandler
from luoying_bot.application.message_processor import MessageProcessor
from luoying_bot.application.service_hub import ServiceHub
from luoying_bot.application.services.builtin_schedule_service import BuiltinScheduleService
from luoying_bot.application.services.group_runtime import GroupRuntime
from luoying_bot.application.services.memo_service import MemoService
from luoying_bot.application.services.quick_reply_service import QuickReplyService
from luoying_bot.application.services.reminder_service import ReminderService
from luoying_bot.application.services.risk_control_service import RiskControlService
from luoying_bot.application.services.script_workspace_service import ScriptWorkspaceService
from luoying_bot.application.services.user_prompt_settings_service import UserPromptSettingsService
from luoying_bot.application.services.user_service import UserService
from luoying_bot.application.services.user_memory_service import UserMemoryService
from luoying_bot.config import settings
from luoying_bot.infra.repos.text_user_memory_repo import TextUserMemoryRepo
from luoying_bot.infra.llm.openai_chat import OpenAICompatibleChatModel
from luoying_bot.infra.memory.in_memory import InMemoryConversationMemory
from luoying_bot.infra.repos.json_memo_repo import JsonMemoRepo
from luoying_bot.infra.repos.json_reminder_repo import JsonReminderRepo
from luoying_bot.infra.repos.json_user_prompt_settings_repo import JsonUserPromptSettingsRepo
from luoying_bot.infra.repos.json_user_repo import JsonUserRepo
from luoying_bot.infra.scheduler.async_scheduler import AsyncScheduler
from luoying_bot.infra.transports.cli_transport import CliTransport
from luoying_bot.infra.transports.qq_ws_transport import QQWsTransport
from luoying_bot.infra.transports.web_transport import WebTransport
from luoying_bot.ports.transport import ChatTransport

@dataclass(slots=True)
class AppContainer:
    transport: ChatTransport
    runtime: GroupRuntime
    user_service: UserService
    reminder_service: ReminderService
    builtin_schedule_service: BuiltinScheduleService
    script_workspace_service: ScriptWorkspaceService
    risk_control_service: RiskControlService
    user_prompt_settings_service: UserPromptSettingsService
    memo_service: MemoService
    quick_reply_service: QuickReplyService | None
    commands: CommandDispatcher
    skills: SkillRegistry
    agent: AgentService
    event_handler: EventHandler
    message_processor: MessageProcessor
    scheduler: AsyncScheduler
    services: ServiceHub

async def build_qq_container() -> AppContainer:
    transport = QQWsTransport(settings)
    runtime = GroupRuntime(enabled_groups={gid: True for gid in settings.specific_group_ids})
    return await _build_container(transport, runtime)

async def build_cli_container() -> AppContainer:
    transport = CliTransport()
    runtime = GroupRuntime(enabled_groups={})
    return await _build_container(transport, runtime)

async def build_web_container() -> AppContainer:
    transport = WebTransport()
    runtime = GroupRuntime(enabled_groups={})
    return await _build_container(transport, runtime, enable_commands=False,enable_quick_reply=False)

async def _build_container(
    transport: ChatTransport,
    runtime: GroupRuntime,
    *,
    enable_commands: bool = True,
    enable_quick_reply: bool = True,
) -> AppContainer:
    user_service = UserService(JsonUserRepo(settings.user_db_file))
    user_prompt_settings_service = UserPromptSettingsService(
        JsonUserPromptSettingsRepo(settings.user_prompt_settings_file)
    )
    scheduler = AsyncScheduler()
    reminder_service = ReminderService(
        JsonReminderRepo(settings.reminder_db_file),
        scheduler,
        transport,
    )
    risk_control_service = RiskControlService()
    builtin_schedule_service = BuiltinScheduleService(
        scheduler=scheduler,
        transport=transport,
        runtime=runtime,
    )
    memo_service = MemoService(JsonMemoRepo(settings.memo_dir))
    quick_reply_service =( QuickReplyService(settings.quick_reply_file) if enable_quick_reply else None)
    script_workspace_service = ScriptWorkspaceService(
        root_dir=settings.script_workspace_dir,
        python_timeout_sec=settings.python_script_timeout_sec,
    )
    user_memory_service = UserMemoryService(
        TextUserMemoryRepo(settings.user_memory_dir)
    )


    memory = InMemoryConversationMemory(
        max_messages_per_thread=settings.memory_max_messages_per_thread
    )
    model = OpenAICompatibleChatModel(
        settings.openai_base_url, 
        settings.openai_api_key, 
        settings.openai_model, 
        settings.llm_temperature,
        settings.openai_enable_thinking,
    )
    #把以上东西打个包
    services = ServiceHub(
        ops=settings.ops,
        HELP=settings.HELP,
        LOG=settings.LOG,
        transport=transport,
        runtime=runtime,
        user_service=user_service,
        reminder_service=reminder_service,
        memo_service=memo_service,
        script_workspace_service=script_workspace_service,
        memory=memory,
        risk_control_service=risk_control_service,
        user_memory_service=user_memory_service,
        user_prompt_settings_service=user_prompt_settings_service,
    )

    #指令
    commands = CommandDispatcher(services) 
    if enable_commands:
        commands.auto_register()

    #skill
    skills = SkillRegistry(services)
    skills.auto_register()
    
    #agent
    agent = AgentService(
        model, 
        memory, 
        skills,
        max_steps=20,
        skill_timeout_sec=settings.agent_skill_timeout_sec,
        total_timeout_sec=settings.agent_total_timeout_sec,
    )

    event_handler = EventHandler(
        transport=transport, 
        runtime=runtime, 
        commands=commands, 
        agent=agent,
        quick_reply_service=quick_reply_service, 
        trigger_prefix=settings.trigger_prefix, 
        qq_private_user_ids=settings.qq_private_user_ids,
        bot_qq=settings.bot_qq, 
        bot_name=settings.bot_name,
        risk_control_service=risk_control_service,
        commands_enabled=enable_commands,
    )
    message_processor = MessageProcessor(
        event_handler=event_handler,
        max_concurrent_tasks=settings.max_concurrent_message_tasks,
    )

    return AppContainer(
        transport=transport,
        runtime=runtime,
        user_service=user_service,
        reminder_service=reminder_service,
        builtin_schedule_service=builtin_schedule_service,
        memo_service=memo_service,
        quick_reply_service=quick_reply_service,
        risk_control_service=risk_control_service,
        user_prompt_settings_service=user_prompt_settings_service,
        script_workspace_service=script_workspace_service,
        commands=commands,
        skills=skills,
        agent=agent,
        event_handler=event_handler,
        message_processor=message_processor,
        scheduler=scheduler,
        services=services,
    )
