
from __future__ import annotations
import logging
from luoying_bot.bootstrap_web import build_web_container
from luoying_bot.infra.web.api import WebApiFactory

logging.basicConfig(level=logging.INFO)

def create_app():
    app = WebApiFactory().create()

    @app.on_event('startup')
    async def _startup() -> None:
        # AIGC: 在 FastAPI 生命周期中异步构建容器，避免 asyncio.run 嵌套事件循环
        container = await build_web_container()
        app.state.container = container
        app.state.web_session_store = container.web_session_store
        app.state.event_handler = container.event_handler
        app.state.video_understanding_service = container.video_understanding_service
        check_result = await container.event_handler.transport.startup_self_check()
        logging.info("Web startup self-check: %s", check_result)
        logging.info("Web session policy: %s", container.session_policy)

    return app
#以上代码aigc
