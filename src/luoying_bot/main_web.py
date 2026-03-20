from __future__ import annotations
from luoying_bot.bootstrap import build_qq_container
from luoying_bot.infra.web.api import WebApiFactory

async def create_app():
    container = await build_qq_container()
    return WebApiFactory(container.event_handler).create()
#以上代码aigc
