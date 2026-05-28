from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
from dotenv import load_dotenv
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def _split_csv(value: str) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(',') if item.strip()]

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

def _env_path(name: str, default: str) -> Path:
    raw = os.getenv(name, default)
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path

# 集中读取配置
# 将配置整理封装成一个setting
@dataclass(slots=True)
class Settings:
    ws_url: str = os.getenv('WS_URL', 'ws://127.0.0.1:3001')
    ws_token: str = os.getenv('WS_TOKEN', '')
    HELP: str = os.getenv('HELP', '拉取链接失败')
    LOG: str = os.getenv('LOG', '拉取链接失败')
    version: str = os.getenv('VERSION','unknown')
    bot_qq: str = os.getenv('BOT_QQ', '3949843218')
    bot_name: str = os.getenv('BOT_NAME', '珞樱')
    openai_base_url: str = os.getenv('OPENAI_BASE_URL', 'https://api.deepseek.com')
    openai_api_key: str = os.getenv('OPENAI_API_KEY', '')
    openai_model: str = os.getenv('OPENAI_MODEL', 'deepseek-chat')
    llm_temperature: float = float(os.getenv('LLM_TEMPERATURE', '1.0'))
    openai_enable_thinking: bool = _env_bool('OPENAI_ENABLE_THINKING', False)

    coding_base_url: str = os.getenv('CODER_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
    coding_api_key: str = os.getenv('CODER_API_KEY', '')
    coding_model: str = os.getenv('CODER_MODEL', 'qwen3-max')
    coding_temperature: float = float(os.getenv('CODER_TEMPERATURE', '0.2'))

    image_base_url: str = os.getenv("IMAGE_BASE_URL", "")
    image_api_key: str = os.getenv("IMAGE_API_KEY", "")
    image_model: str = os.getenv("IMAGE_MODEL", "")

    qweather_api_key: str = os.getenv('QWEATHER_API_KEY', '')
    weather_base_url: str = os.getenv('WEATHER_BASE_URL', 'https://pn6yvyt6je.re.qweatherapi.com/v7/weather/now')
    tavily_api_key: str = os.getenv('TAVILY_API_KEY', '')

    data_dir: Path = _env_path('DATA_DIR', './data')
    memo_dir: Path = _env_path('MEMO_DIR', './data/memo')
    quick_reply_file: Path = _env_path('QUICK_REPLY_FILE', './data/quick_replies.json')
    user_db_file: Path = _env_path('USER_DB_FILE', './data/userdatabase.json')
    user_prompt_settings_file: Path = _env_path('USER_PROMPT_SETTINGS_FILE', './data/user_prompt_settings.json')
    reminder_db_file: Path = _env_path('REMINDER_DB_FILE', './data/reminders.json')
    user_memory_dir: Path = _env_path('USER_MEMORY_DIR', './data/user_memory')
    script_workspace_dir: Path = _env_path('SCRIPT_WORKSPACE_DIR', './data/scripts')
    python_script_timeout_sec: int = int(os.getenv('PYTHON_SCRIPT_TIMEOUT_SEC', '15'))


    memory_max_messages_per_thread: int = int(os.getenv('MEMORY_MAX_MESSAGES_PER_THREAD', '80'))
    agent_skill_timeout_sec: float = float(os.getenv('AGENT_SKILL_TIMEOUT_SEC', '30'))
    agent_total_timeout_sec: float = float(os.getenv('AGENT_TOTAL_TIMEOUT_SEC', '90'))
    max_concurrent_message_tasks: int = int(os.getenv('MAX_CONCURRENT_MESSAGE_TASKS', '200'))

    ops: List[str] = field(default_factory=lambda: _split_csv(os.getenv('OPS', '')))
    specific_group_ids: List[str] = field(default_factory=lambda: _split_csv(os.getenv('SPECIFIC_GROUP_IDS', '')))
    trigger_prefix: List[str] = field(default_factory=lambda: _split_csv(os.getenv('TRIGGER_PREFIX', '/,!')))

settings = Settings()

#别的文件只需要import这个就能拿到配置
