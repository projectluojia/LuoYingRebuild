from __future__ import annotations

from dataclasses import dataclass

from luoying_bot.application.agent.agent_service import AgentService
from luoying_bot.application.agent.skill_registry import SkillRegistry
from luoying_bot.application.commands.dispatcher import CommandDispatcher
from luoying_bot.application.event_handler import EventHandler
from luoying_bot.application.services.group_runtime import GroupRuntime
from luoying_bot.application.services.memo_service import MemoService
from luoying_bot.application.services.quick_reply_service import QuickReplyService
from luoying_bot.application.services.reminder_service import ReminderService
from luoying_bot.application.services.script_workspace_service import ScriptWorkspaceService
from luoying_bot.application.services.user_service import UserService
from luoying_bot.config import settings
from luoying_bot.infra.llm.openai_chat import OpenAICompatibleChatModel
from luoying_bot.infra.memory.in_memory import InMemoryConversationMemory
from luoying_bot.infra.repos.json_memo_repo import JsonMemoRepo
from luoying_bot.infra.repos.json_reminder_repo import JsonReminderRepo
from luoying_bot.infra.repos.json_user_repo import JsonUserRepo
from luoying_bot.infra.scheduler.async_scheduler import AsyncScheduler
from luoying_bot.infra.transports.web_noop_transport import WebNoopTransport

# AIGC: Web 专用容器，和 QQ 容器解耦，避免 Web 启动路径触发 QQ 连接逻辑。

@dataclass(slots=True)
class WebAppContainer:
    runtime: GroupRuntime
    user_service: UserService
    reminder_service: ReminderService
    script_workspace_service: ScriptWorkspaceService
    memo_service: MemoService
    quick_reply_service: QuickReplyService
    commands: CommandDispatcher
    skills: SkillRegistry
    agent: AgentService
    event_handler: EventHandler
    scheduler: AsyncScheduler


async def build_web_container() -> WebAppContainer:
    # AIGC: Web 场景使用无副作用 transport，HTTP 返回即为消息输出。
    transport = WebNoopTransport()
    runtime = GroupRuntime(enabled_groups={gid: True for gid in settings.specific_group_ids})
    user_service = UserService(JsonUserRepo(settings.user_db_file))
    scheduler = AsyncScheduler()
    reminder_service = ReminderService(JsonReminderRepo(settings.reminder_db_file), scheduler, transport)
    memo_service = MemoService(JsonMemoRepo(settings.memo_dir))
    quick_reply_service = QuickReplyService(settings.quick_reply_file)
    script_workspace_service = ScriptWorkspaceService(
        root_dir=settings.script_workspace_dir,
        python_timeout_sec=settings.python_script_timeout_sec,
        send_chunk_size=settings.script_send_chunk_size,
        max_output_chars=settings.script_max_output_chars,
    )

    memory = InMemoryConversationMemory()
    main_model_base_url = settings.ollama_base_url if settings.use_local_ollama else settings.openai_base_url
    main_model_api_key = settings.ollama_api_key if settings.use_local_ollama else settings.openai_api_key
    main_model_name = settings.ollama_main_model if settings.use_local_ollama else settings.openai_model
    model = OpenAICompatibleChatModel(
        main_model_base_url,
        main_model_api_key,
        main_model_name,
        settings.llm_temperature,
    )

    services = {
        'ops': settings.ops,
        'HELP': settings.HELP,
        'LOG': settings.LOG,
        'transport': transport,
        'runtime': runtime,
        'user_service': user_service,
        'reminder_service': reminder_service,
        'memo_service': memo_service,
        'script_workspace_service': script_workspace_service,
        'memory': memory,
    }

    commands = CommandDispatcher(services)
    commands.auto_register()

    skills = SkillRegistry(services)
    skills.auto_register()

    agent = AgentService(model, memory, skills)
    event_handler = EventHandler(
        transport=transport,
        runtime=runtime,
        commands=commands,
        agent=agent,
        quick_reply_service=quick_reply_service,
        trigger_prefix=settings.trigger_prefix,
        bot_qq=settings.bot_qq,
        bot_name=settings.bot_name,
    )

    return WebAppContainer(
        runtime=runtime,
        user_service=user_service,
        reminder_service=reminder_service,
        script_workspace_service=script_workspace_service,
        memo_service=memo_service,
        quick_reply_service=quick_reply_service,
        commands=commands,
        skills=skills,
        agent=agent,
        event_handler=event_handler,
        scheduler=scheduler,
    )
