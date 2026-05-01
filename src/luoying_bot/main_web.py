from __future__ import annotations

import os

import uvicorn

from luoying_bot.infra.web.api import WebApiFactory

def create_app():
    return WebApiFactory().create()


def main() -> None:
    host = os.getenv("WEB_HOST", "127.0.0.1")
    port = int(os.getenv("WEB_PORT", "8000"))
    uvicorn.run(
        "luoying_bot.main_web:create_app",
        factory=True,
        host=host,
        port=port,
    )


if __name__ == "__main__":
    main()
