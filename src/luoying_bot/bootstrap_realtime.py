from __future__ import annotations

from dataclasses import dataclass

from luoying_bot.infra.transports.realtime_ws_transport import RealtimeWsTransport


@dataclass(slots=True)
class RealtimeAppContainer:
    realtime_transport: RealtimeWsTransport
    realtime_policy: dict[str, object]


async def build_realtime_container() -> RealtimeAppContainer:
    realtime_policy: dict[str, object] = {
        "max_participants_per_session": 2,
        "default_ws_path": "/realtime/ws/{session_id}",
        "server_webrtc_enabled": True,
        "server_signaling_target": "server",
    }
    transport = RealtimeWsTransport(
        max_participants_per_session=int(realtime_policy["max_participants_per_session"]),
        server_webrtc_enabled=bool(realtime_policy["server_webrtc_enabled"]),
    )
    return RealtimeAppContainer(
        realtime_transport=transport,
        realtime_policy=realtime_policy,
    )
