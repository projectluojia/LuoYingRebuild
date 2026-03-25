from __future__ import annotations
import httpx

from dataclasses import dataclass
from typing import Awaitable, Callable, TYPE_CHECKING
from luoying_bot.config import settings
from luoying_bot.constants import WEB_SYSTEM_PROMPT
from luoying_bot.infra.scheduler.async_scheduler import ScheduledJob
from luoying_bot.infra.llm.openai_chat import OpenAICompatibleChatModel



if TYPE_CHECKING:
    from luoying_bot.application.services.builtin_schedule_service import BuiltinScheduleService

model = OpenAICompatibleChatModel(
    settings.openai_base_url, 
    settings.openai_api_key, 
    settings.openai_model, 
    settings.llm_temperature
)


# 统一的内置计划事件 handler 签名
BuiltinJobHandler = Callable[
    ['BuiltinScheduleService', str, ScheduledJob],
    Awaitable[None]
]


@dataclass(slots=True, frozen=True)
class BuiltinJobSpec:
    job_key: str
    hour: int
    minute: int
    handler: BuiltinJobHandler
    enabled: bool = True


# ========== 通用 handler 示例：发送固定文本 ==========
async def send_midnight_rest(
    service: 'BuiltinScheduleService',
    group_id: str,
    job: ScheduledJob
) -> None:
    await service.send_group_text(group_id, '夜深了，注意休息(´•ω•｀)')

async def send_class_remind(
    service: 'BuiltinScheduleService',
    group_id: str,
    job: ScheduledJob
) -> None:
    await service.send_group_text(group_id, '要上课了，记得打卡哦！')

async def whWeather() -> str:
    if not settings.qweather_api_key: 
        return '天气服务未配置 API Key'
    
    url = settings.weather_base_url
    params = {
        "location": "101200101",
        "lang": "zh",
        "unit": "m",
        "key": settings.qweather_api_key,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        now = data["now"]
        return f"天气：{now['text']}，温度 {now['temp']}°C，体感 {now['feelsLike']}°C，湿度 {now['humidity']}%"

async def send_morning_greeting(
    service: 'BuiltinScheduleService',
    group_id: str,
    job: ScheduledJob
) -> None:
    
    now_weather=None
    try:
        now_weather=await whWeather()
    except Exception as e:
        pass
    try:
        response=await model.chat(
            [
                {"role":"system","content":WEB_SYSTEM_PROMPT},
                {"role":"system","content":f"""生成一份武汉实时天气早报，目前武汉的天气是：{now_weather}示例：今天武汉是阴天，温度11°C，体感9°C，湿度有点高，95%呢～
        记得多穿点衣服，别着凉了哦！❤
        新的一天也要元气满满！✨ 注意 1. 不一定要格式完全和示例一样！ 2. 开头必须是 '早上好，美好的一天又开始啦！' 然后下一行是你的早报，尽量简短 3. 如果天气是None，则代表函数获取天气失败 """},
                {"role":"system","content":"请执行system中的要求"}
            ]
        )
    except Exception as e :
        response="早安信息获取出错！"
    await service.send_group_text(group_id, response.strip())


# 所有内置计划事件统一在这里声明
BUILTIN_JOBS: list[BuiltinJobSpec] = [
    BuiltinJobSpec(
        job_key='midnight_rest',
        hour=0,
        minute=0,
        handler=send_midnight_rest,
    ),
    BuiltinJobSpec(
        job_key='morning_greeting',
        hour=8,
        minute=0,
        handler=send_morning_greeting,
    ),
    BuiltinJobSpec(
        job_key='class_remind',
        hour=9,
        minute=35,
        handler=send_class_remind,
    ),
]