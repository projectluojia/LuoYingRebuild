from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
from dotenv import load_dotenv
load_dotenv()

def _split_csv(value: str) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(',') if item.strip()]

# 集中读取配置
# 将配置整理封装成一个setting
@dataclass(slots=True)
class Settings:
    ws_url: str = os.getenv('WS_URL', 'ws://127.0.0.1:3001')
    HELP: str = os.getenv('HELP', '拉取链接失败')
    LOG: str = os.getenv('LOG', '拉取链接失败')
    version: str = os.getenv('VERSION','unknown')
    bot_qq: str = os.getenv('BOT_QQ', '3949843218')
    bot_name: str = os.getenv('BOT_NAME', '珞樱')
    openai_base_url: str = os.getenv('OPENAI_BASE_URL', 'https://api.deepseek.com')
    openai_api_key: str = os.getenv('OPENAI_API_KEY', '')
    openai_model: str = os.getenv('OPENAI_MODEL', 'deepseek-chat')
    llm_temperature: float = float(os.getenv('LLM_TEMPERATURE', '1.0'))

    coding_base_url: str = os.getenv('CODER_BASE_URL', 'https://api.deepseek.com')
    coding_api_key: str = os.getenv('CODER_API_KEY', '')
    coding_model: str = os.getenv('CODER_MODEL', 'deepseek-reasoner')
    coding_temperature: float = float(os.getenv('CODER_TEMPERATURE', '0.2'))

    image_base_url: str = os.getenv("IMAGE_BASE_URL", "")
    image_api_key: str = os.getenv("IMAGE_API_KEY", "")
    image_model: str = os.getenv("IMAGE_MODEL", "")

    qweather_api_key: str = os.getenv('QWEATHER_API_KEY', '')
    weather_base_url: str = os.getenv('WEATHER_BASE_URL', 'https://pn6yvyt6je.re.qweatherapi.com/v7/weather/now')
    tavily_api_key: str = os.getenv('TAVILY_API_KEY', '')

    data_dir: Path = Path(os.getenv('DATA_DIR', './data'))
    memo_dir: Path = Path(os.getenv('MEMO_DIR', './data/memo'))
    quick_reply_file: Path = Path(os.getenv('QUICK_REPLY_FILE', './data/quick_replies.json'))
    user_db_file: Path = Path(os.getenv('USER_DB_FILE', './data/userdatabase.json'))
    reminder_db_file: Path = Path(os.getenv('REMINDER_DB_FILE', './data/reminders.json'))

    script_workspace_dir: Path = Path(os.getenv('SCRIPT_WORKSPACE_DIR', './data/scripts'))
    python_script_timeout_sec: int = int(os.getenv('PYTHON_SCRIPT_TIMEOUT_SEC', '15'))
    script_send_chunk_size: int = int(os.getenv('SCRIPT_SEND_CHUNK_SIZE', '1200'))
    script_max_output_chars: int = int(os.getenv('SCRIPT_MAX_OUTPUT_CHARS', '12000'))

    ops: List[str] = field(default_factory=lambda: _split_csv(os.getenv('OPS', '')))
    specific_group_ids: List[str] = field(default_factory=lambda: _split_csv(os.getenv('SPECIFIC_GROUP_IDS', '')))
    trigger_prefix: List[str] = field(default_factory=lambda: _split_csv(os.getenv('TRIGGER_PREFIX', '/,!')))

settings = Settings()
#别的文件只需要import这个就能拿到配置