from __future__ import annotations

import importlib.util
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket
from pydantic import BaseModel, Field

from luoying_bot.bootstrap_realtime import build_realtime_container

logging.basicConfig(level=logging.INFO)


class CreateSessionRequest(BaseModel):
    owner_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CloseSessionRequest(BaseModel):
    reason: str = "closed_by_api"


class SessionEnvelope(BaseModel):
    session: dict[str, Any]


def create_app() -> FastAPI:
    app = FastAPI(title="Luoying Realtime Signaling")

    @app.on_event("startup")
    async def _startup() -> None:
        container = await build_realtime_container()
        app.state.realtime_container = container
        app.state.realtime_transport = container.realtime_transport
        check_result = await container.realtime_transport.startup_self_check()
        logging.info("Realtime startup self-check: %s", check_result)
        logging.info("Realtime policy: %s", container.realtime_policy)

    def _get_transport(app: FastAPI) -> Any:
        transport = getattr(app.state, "realtime_transport", None)
        if transport is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "REALTIME_NOT_READY",
                    "message": "Realtime transport is not ready",
                    "status": 503,
                },
            )
        return transport

    @app.get("/realtime/health")
    async def health(request: Request) -> dict[str, Any]:
        transport = _get_transport(request.app)
        policy = getattr(request.app.state, "realtime_container", None)
        realtime_policy = {} if policy is None else dict(getattr(policy, "realtime_policy", {}))
        return {
            "status": "ok",
            "server_webrtc_enabled": bool(getattr(transport, "server_webrtc_enabled", False)),
            "aiortc_available": importlib.util.find_spec("aiortc") is not None,
            "policy": realtime_policy,
        }

    @app.post("/realtime/sessions", response_model=SessionEnvelope)
    async def create_session(req: CreateSessionRequest, request: Request) -> SessionEnvelope:
        transport = _get_transport(request.app)
        session = await transport.create_session(owner_id=req.owner_id, metadata=req.metadata)
        return SessionEnvelope(session=session)

    @app.get("/realtime/sessions/{session_id}", response_model=SessionEnvelope)
    async def get_session(session_id: str, request: Request) -> SessionEnvelope:
        transport = _get_transport(request.app)
        session = await transport.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "SESSION_NOT_FOUND",
                    "message": "Realtime session not found",
                    "status": 404,
                },
            )
        return SessionEnvelope(session=session)

    @app.post("/realtime/sessions/{session_id}/close", response_model=SessionEnvelope)
    async def close_session(session_id: str, req: CloseSessionRequest, request: Request) -> SessionEnvelope:
        transport = _get_transport(request.app)
        session = await transport.close_session(session_id, reason=req.reason)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "SESSION_NOT_FOUND",
                    "message": "Realtime session not found",
                    "status": 404,
                },
            )
        return SessionEnvelope(session=session)

    @app.websocket("/realtime/ws/{session_id}")
    async def realtime_ws(
        websocket: WebSocket,
        session_id: str,
        client_id: str | None = None,
        role: str = "peer",
    ) -> None:
        transport = getattr(websocket.app.state, "realtime_transport", None)
        if transport is None:
            await websocket.accept()
            await websocket.send_json(
                {
                    "type": "signal.error",
                    "session_id": session_id,
                    "payload": {
                        "code": "REALTIME_NOT_READY",
                        "message": "Realtime transport is not ready",
                    },
                }
            )
            await websocket.close(code=4403)
            return
        await transport.handle_websocket(
            websocket=websocket,
            session_id=session_id,
            client_id=client_id,
            role=role,
        )

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "luoying_bot.main_realtime:create_app",
        factory=True,
        host="0.0.0.0",
        port=8010,
        log_level="info",
    )
