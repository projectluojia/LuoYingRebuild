
from __future__ import annotations
from luoying_bot.bootstrap_web import build_web_container
from luoying_bot.infra.web.api import WebApiFactory

def create_app():
    app = WebApiFactory().create()

    @app.on_event('startup')
    async def _startup() -> None:
        # AIGC: 在 FastAPI 生命周期中异步构建容器，避免 asyncio.run 嵌套事件循环
        container = await build_web_container()
        app.state.container = container
        app.state.event_handler = container.event_handler

    return app
#以上代码aigc
