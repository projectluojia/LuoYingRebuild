from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import importlib.util
from typing import Any
import uuid

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class RealtimePeer:
    client_id: str
    role: str
    joined_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "client_id": self.client_id,
            "role": self.role,
            "joined_at": self.joined_at,
        }


@dataclass(slots=True)
class RealtimeSession:
    session_id: str
    state: str
    created_at: str
    updated_at: str
    participants: dict[str, RealtimePeer] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "participants": [peer.to_dict() for peer in self.participants.values()],
            "participant_count": len(self.participants),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class _ServerPeer:
    session_id: str
    client_id: str
    pc: Any


class RealtimeWsTransport:
    """
    独立实时信令 transport：
    - 只负责会话状态与 WebSocket 信令事件，不介入现有聊天主链路。
    - 支持 offer/answer/ice 的点对点转发。
    """

    def __init__(
        self,
        max_participants_per_session: int = 2,
        server_webrtc_enabled: bool = True,
        server_signaling_target: str = "server",
        placeholder_video_enabled: bool = True,
        placeholder_video_width: int = 320,
        placeholder_video_height: int = 180,
    ):
        self.max_participants_per_session = max(2, int(max_participants_per_session))
        self.server_webrtc_enabled = bool(server_webrtc_enabled)
        self.server_signaling_target = (server_signaling_target or "server").strip() or "server"
        self.placeholder_video_enabled = bool(placeholder_video_enabled)
        self.placeholder_video_width = max(64, int(placeholder_video_width))
        self.placeholder_video_height = max(64, int(placeholder_video_height))
        self._sessions: dict[str, RealtimeSession] = {}
        self._connections: dict[str, dict[str, WebSocket]] = {}
        self._server_peers: dict[tuple[str, str], _ServerPeer] = {}
        self._lock = asyncio.Lock()

    async def startup_self_check(self) -> str:
        aiortc_available = importlib.util.find_spec("aiortc") is not None
        return (
            "realtime ws transport ready "
            f"(max_participants_per_session={self.max_participants_per_session}, "
            f"server_webrtc_enabled={self.server_webrtc_enabled}, "
            f"server_signaling_target={self.server_signaling_target}, "
            f"placeholder_video_enabled={self.placeholder_video_enabled}, "
            f"aiortc_available={aiortc_available})"
        )

    @staticmethod
    def _event(event_type: str, session_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "type": event_type,
            "session_id": session_id,
            "timestamp": _utc_now_iso(),
            "payload": payload or {},
        }

    async def create_session(self, owner_id: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        now = _utc_now_iso()
        session_id = str(uuid.uuid4())
        session = RealtimeSession(
            session_id=session_id,
            state="created",
            created_at=now,
            updated_at=now,
            metadata={"owner_id": owner_id or "", **(metadata or {})},
        )
        async with self._lock:
            self._sessions[session_id] = session
            self._connections[session_id] = {}
        return session.to_dict()

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        async with self._lock:
            session = self._sessions.get(session_id)
            return None if session is None else session.to_dict()

    async def close_session(self, session_id: str, reason: str = "closed_by_api") -> dict[str, Any] | None:
        targets: list[WebSocket] = []
        snapshot: dict[str, Any] | None = None
        server_peer_keys: list[tuple[str, str]] = []
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            session.state = "closed"
            session.updated_at = _utc_now_iso()
            snapshot = session.to_dict()
            targets = list(self._connections.get(session_id, {}).values())
            self._connections[session_id] = {}
            server_peer_keys = [key for key in self._server_peers if key[0] == session_id]

        event = self._event("call.state.changed", session_id, {"state": "closed", "reason": reason})
        for ws in targets:
            await self._safe_send(ws, event)
            try:
                await ws.close(code=1000)
            except Exception:
                pass
        for _, client_id in server_peer_keys:
            await self._close_server_peer(session_id, client_id)
        return snapshot

    async def handle_websocket(
        self,
        websocket: WebSocket,
        session_id: str,
        client_id: str | None = None,
        role: str = "peer",
    ) -> None:
        await websocket.accept()
        assigned_id = (client_id or "").strip() or str(uuid.uuid4())
        role = (role or "peer").strip() or "peer"

        registered, error_message = await self._register(session_id, assigned_id, role, websocket)
        if not registered:
            await self._safe_send(
                websocket,
                self._event(
                    "signal.error",
                    session_id,
                    {"code": "SESSION_JOIN_FAILED", "message": error_message or "join failed"},
                ),
            )
            await websocket.close(code=4400)
            return

        await self._safe_send(
            websocket,
            self._event(
                "session.joined",
                session_id,
                {
                    "client_id": assigned_id,
                    "role": role,
                    "session": await self.get_session(session_id),
                },
            ),
        )

        try:
            while True:
                packet = await websocket.receive_json()
                await self._handle_incoming(session_id, assigned_id, packet)
        except WebSocketDisconnect:
            pass
        finally:
            await self._unregister(session_id, assigned_id)

    async def _register(
        self,
        session_id: str,
        client_id: str,
        role: str,
        websocket: WebSocket,
    ) -> tuple[bool, str | None]:
        broadcasts: list[tuple[WebSocket, dict[str, Any]]] = []
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False, "session not found"
            if session.state == "closed":
                return False, "session already closed"

            conns = self._connections.setdefault(session_id, {})
            if client_id not in conns and len(conns) >= self.max_participants_per_session:
                return False, "session participant limit reached"

            conns[client_id] = websocket
            session.participants[client_id] = RealtimePeer(
                client_id=client_id,
                role=role,
                joined_at=_utc_now_iso(),
            )
            prev_state = session.state
            session.state = "connected" if len(conns) >= 2 else "signaling"
            session.updated_at = _utc_now_iso()

            join_event = self._event(
                "signaling.peer.joined",
                session_id,
                {"client_id": client_id, "role": role, "participant_count": len(conns)},
            )
            for cid, ws in conns.items():
                if cid == client_id:
                    continue
                broadcasts.append((ws, join_event))

            if prev_state != session.state:
                state_event = self._event("call.state.changed", session_id, {"state": session.state})
                for cid, ws in conns.items():
                    if cid == client_id:
                        continue
                    broadcasts.append((ws, state_event))

        for ws, event in broadcasts:
            await self._safe_send(ws, event)
        return True, None

    async def _unregister(self, session_id: str, client_id: str) -> None:
        broadcasts: list[tuple[WebSocket, dict[str, Any]]] = []
        async with self._lock:
            session = self._sessions.get(session_id)
            conns = self._connections.get(session_id, {})
            if client_id in conns:
                conns.pop(client_id, None)
            if session is None:
                return
            session.participants.pop(client_id, None)
            if session.state != "closed":
                prev_state = session.state
                if len(conns) == 0:
                    session.state = "created"
                elif len(conns) == 1:
                    session.state = "signaling"
                else:
                    session.state = "connected"
                session.updated_at = _utc_now_iso()

                left_event = self._event(
                    "signaling.peer.left",
                    session_id,
                    {"client_id": client_id, "participant_count": len(conns)},
                )
                for ws in conns.values():
                    broadcasts.append((ws, left_event))

                if prev_state != session.state:
                    state_event = self._event("call.state.changed", session_id, {"state": session.state})
                    for ws in conns.values():
                        broadcasts.append((ws, state_event))

        for ws, event in broadcasts:
            await self._safe_send(ws, event)
        await self._close_server_peer(session_id, client_id)

    async def _handle_incoming(self, session_id: str, from_client_id: str, packet: dict[str, Any]) -> None:
        msg_type = str(packet.get("type") or "").strip()
        if msg_type == "ping":
            await self._emit_to_client(
                session_id,
                from_client_id,
                self._event("pong", session_id, {"client_id": from_client_id}),
            )
            return

        if msg_type == "call.close":
            await self.close_session(session_id, reason="closed_by_peer")
            return

        if msg_type not in {"signal.offer", "signal.answer", "signal.ice"}:
            await self._emit_to_client(
                session_id,
                from_client_id,
                self._event(
                    "signal.error",
                    session_id,
                    {"code": "UNKNOWN_SIGNAL_TYPE", "message": f"unsupported type: {msg_type}"},
                ),
            )
            return

        to_client_id = str(packet.get("to") or "").strip() or None
        if to_client_id == self.server_signaling_target:
            handled = await self._handle_server_signal(
                session_id=session_id,
                from_client_id=from_client_id,
                msg_type=msg_type,
                packet=packet,
            )
            if handled:
                return

        payload = packet.get("payload")
        if not isinstance(payload, dict):
            payload = {
                key: value
                for key, value in packet.items()
                if key not in {"type", "to", "from", "session_id"}
            }
        event = self._event(
            msg_type,
            session_id,
            {
                "from": from_client_id,
                "to": to_client_id or "",
                "payload": payload,
            },
        )
        await self._emit_signal(session_id, from_client_id, event, to_client_id)

    async def _emit_signal(
        self,
        session_id: str,
        from_client_id: str,
        event: dict[str, Any],
        to_client_id: str | None,
    ) -> None:
        targets: list[WebSocket] = []
        missing_target = False
        async with self._lock:
            conns = self._connections.get(session_id, {})
            if to_client_id:
                target = conns.get(to_client_id)
                if target is None:
                    missing_target = True
                else:
                    targets = [target]
            else:
                targets = [ws for cid, ws in conns.items() if cid != from_client_id]

        if missing_target:
            await self._emit_to_client(
                session_id,
                from_client_id,
                self._event(
                    "signal.error",
                    session_id,
                    {"code": "TARGET_NOT_FOUND", "message": f"target peer not found: {to_client_id}"},
                ),
            )
            return

        for ws in targets:
            await self._safe_send(ws, event)

    async def _handle_server_signal(
        self,
        session_id: str,
        from_client_id: str,
        msg_type: str,
        packet: dict[str, Any],
    ) -> bool:
        if not self.server_webrtc_enabled:
            await self._emit_to_client(
                session_id,
                from_client_id,
                self._event(
                    "signal.error",
                    session_id,
                    {
                        "code": "SERVER_WEBRTC_DISABLED",
                        "message": "server-side webrtc is disabled",
                    },
                ),
            )
            return True

        if msg_type == "signal.offer":
            await self._handle_server_offer(session_id, from_client_id, packet)
            return True
        if msg_type == "signal.ice":
            await self._handle_server_ice(session_id, from_client_id, packet)
            return True
        if msg_type == "signal.answer":
            await self._emit_to_client(
                session_id,
                from_client_id,
                self._event(
                    "signal.error",
                    session_id,
                    {
                        "code": "UNSUPPORTED_SERVER_SIGNAL",
                        "message": "server side signaling does not accept signal.answer",
                    },
                ),
            )
            return True
        return False

    @staticmethod
    def _resolve_payload(packet: dict[str, Any]) -> dict[str, Any]:
        payload = packet.get("payload")
        if isinstance(payload, dict):
            return payload
        return {
            key: value
            for key, value in packet.items()
            if key not in {"type", "to", "from", "session_id"}
        }

    @staticmethod
    def _extract_offer(payload: dict[str, Any]) -> tuple[str, str]:
        nested_offer = payload.get("offer")
        if isinstance(nested_offer, dict):
            sdp = str(nested_offer.get("sdp") or payload.get("sdp") or "").strip()
            offer_type = str(nested_offer.get("type") or payload.get("type") or "offer").strip() or "offer"
            return sdp, offer_type
        sdp = str(payload.get("sdp") or "").strip()
        offer_type = str(payload.get("type") or "offer").strip() or "offer"
        return sdp, offer_type

    @staticmethod
    def _parse_mline_index(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _extract_ice_fields(self, payload: dict[str, Any]) -> tuple[str | None, str | None, int | None, str | None]:
        raw_candidate = payload.get("candidate")
        sdp_mid = payload.get("sdpMid")
        sdp_mline_index = payload.get("sdpMLineIndex")
        username_fragment = payload.get("usernameFragment")

        if isinstance(raw_candidate, dict):
            if sdp_mid is None:
                sdp_mid = raw_candidate.get("sdpMid")
            if sdp_mline_index is None:
                sdp_mline_index = raw_candidate.get("sdpMLineIndex")
            if username_fragment is None:
                username_fragment = raw_candidate.get("usernameFragment")
            raw_candidate = raw_candidate.get("candidate")

        if raw_candidate is None:
            return None, None if sdp_mid is None else str(sdp_mid), self._parse_mline_index(sdp_mline_index), (
                None if username_fragment is None else str(username_fragment)
            )

        candidate_text = str(raw_candidate).strip()
        if not candidate_text:
            return None, None if sdp_mid is None else str(sdp_mid), self._parse_mline_index(sdp_mline_index), (
                None if username_fragment is None else str(username_fragment)
            )
        return (
            candidate_text,
            None if sdp_mid is None else str(sdp_mid),
            self._parse_mline_index(sdp_mline_index),
            None if username_fragment is None else str(username_fragment),
        )

    def _create_placeholder_video_track(self, aiortc: dict[str, Any]) -> Any | None:
        if not self.placeholder_video_enabled:
            return None
        video_stream_track_cls = aiortc.get("VideoStreamTrack")
        video_frame_cls = aiortc.get("VideoFrame")
        if video_stream_track_cls is None or video_frame_cls is None:
            return None

        width = self.placeholder_video_width
        height = self.placeholder_video_height

        class _PlaceholderVideoTrack(video_stream_track_cls):  # type: ignore[misc, valid-type]
            def __init__(self) -> None:
                super().__init__()
                self._luma_tick = 0

            async def recv(self):  # noqa: ANN202
                pts, time_base = await self.next_timestamp()
                frame = video_frame_cls(width=width, height=height, format="yuv420p")
                self._luma_tick = (self._luma_tick + 2) % 220
                luma = 16 + self._luma_tick

                frame.planes[0].update(bytes([luma]) * frame.planes[0].buffer_size)
                frame.planes[1].update(bytes([128]) * frame.planes[1].buffer_size)
                frame.planes[2].update(bytes([128]) * frame.planes[2].buffer_size)
                frame.pts = pts
                frame.time_base = time_base
                return frame

        return _PlaceholderVideoTrack()

    def _attach_placeholder_video_track(self, pc: Any, aiortc: dict[str, Any]) -> tuple[str, str | None]:
        track = self._create_placeholder_video_track(aiortc)
        if track is None:
            return "skipped", None
        try:
            pc.addTrack(track)
        except Exception as exc:
            return "failed", str(exc)
        return "attached", None

    async def _emit_assistant_text(
        self,
        session_id: str,
        client_id: str,
        text: str,
        source: str = "realtime_transport",
    ) -> None:
        message_id = str(uuid.uuid4())
        await self._emit_to_client(
            session_id,
            client_id,
            self._event(
                "assistant.text.start",
                session_id,
                {
                    "message_id": message_id,
                    "source": source,
                },
            ),
        )
        await self._emit_to_client(
            session_id,
            client_id,
            self._event(
                "assistant.text.delta",
                session_id,
                {
                    "message_id": message_id,
                    "delta": text,
                    "source": source,
                },
            ),
        )
        await self._emit_to_client(
            session_id,
            client_id,
            self._event(
                "assistant.text.final",
                session_id,
                {
                    "message_id": message_id,
                    "text": text,
                    "source": source,
                },
            ),
        )

    async def _handle_server_offer(self, session_id: str, client_id: str, packet: dict[str, Any]) -> None:
        aiortc = self._import_aiortc()
        if aiortc is None:
            await self._emit_to_client(
                session_id,
                client_id,
                self._event(
                    "signal.error",
                    session_id,
                    {
                        "code": "AIORTC_NOT_AVAILABLE",
                        "message": "aiortc is not installed, server-side WebRTC is unavailable",
                    },
                ),
            )
            return

        payload = self._resolve_payload(packet)
        sdp, offer_type = self._extract_offer(payload)
        if not sdp:
            await self._emit_to_client(
                session_id,
                client_id,
                self._event(
                    "signal.error",
                    session_id,
                    {"code": "INVALID_OFFER", "message": "missing SDP in offer payload"},
                ),
            )
            return
        if offer_type != "offer":
            await self._emit_to_client(
                session_id,
                client_id,
                self._event(
                    "signal.error",
                    session_id,
                    {"code": "INVALID_OFFER_TYPE", "message": f"unsupported offer type: {offer_type}"},
                ),
            )
            return

        await self._close_server_peer(session_id, client_id)
        pc = aiortc["RTCPeerConnection"]()
        await self._set_server_peer(session_id, client_id, pc)

        attach_status, attach_error = self._attach_placeholder_video_track(pc, aiortc)
        if attach_status == "failed":
            await self._close_server_peer(session_id, client_id)
            await self._emit_to_client(
                session_id,
                client_id,
                self._event(
                    "signal.error",
                    session_id,
                    {"code": "PLACEHOLDER_VIDEO_ATTACH_FAILED", "message": attach_error or "attach track failed"},
                ),
            )
            return
        if attach_status == "attached":
            await self._emit_to_client(
                session_id,
                client_id,
                self._event(
                    "webrtc.media.track.ready",
                    session_id,
                    {
                        "from": self.server_signaling_target,
                        "to": client_id,
                        "kind": "video",
                        "source": "placeholder",
                        "resolution": {
                            "width": self.placeholder_video_width,
                            "height": self.placeholder_video_height,
                        },
                    },
                ),
            )

        @pc.on("connectionstatechange")
        async def _on_conn_state_change() -> None:
            state = str(pc.connectionState or "").strip() or "unknown"
            await self._emit_to_client(
                session_id,
                client_id,
                self._event(
                    "webrtc.state.changed",
                    session_id,
                    {"from": self.server_signaling_target, "to": client_id, "state": state},
                ),
            )
            if state == "connected":
                await self._set_session_state(session_id, "connected")
            elif state in {"disconnected", "failed", "closed"}:
                await self._set_session_state(session_id, "signaling")
                if state in {"failed", "closed"}:
                    await self._close_server_peer(session_id, client_id)

        @pc.on("iceconnectionstatechange")
        async def _on_ice_conn_state_change() -> None:
            state = str(getattr(pc, "iceConnectionState", "") or "").strip() or "unknown"
            await self._emit_to_client(
                session_id,
                client_id,
                self._event(
                    "webrtc.ice.state.changed",
                    session_id,
                    {"from": self.server_signaling_target, "to": client_id, "state": state},
                ),
            )

        @pc.on("icecandidate")
        async def _on_ice_candidate(candidate) -> None:  # noqa: ANN001
            if candidate is None:
                await self._emit_to_client(
                    session_id,
                    client_id,
                    self._event(
                        "signal.ice",
                        session_id,
                        {
                            "from": self.server_signaling_target,
                            "to": client_id,
                            "payload": {
                                "candidate": None,
                                "sdpMid": None,
                                "sdpMLineIndex": None,
                            },
                        },
                    ),
                )
                return
            candidate_sdp = aiortc["candidate_to_sdp"](candidate)
            if not candidate_sdp.startswith("candidate:"):
                candidate_sdp = f"candidate:{candidate_sdp}"
            payload: dict[str, Any] = {
                "candidate": candidate_sdp,
                "sdpMid": candidate.sdpMid,
                "sdpMLineIndex": candidate.sdpMLineIndex,
            }
            username_fragment = getattr(candidate, "usernameFragment", None)
            if username_fragment:
                payload["usernameFragment"] = str(username_fragment)
            await self._emit_to_client(
                session_id,
                client_id,
                self._event(
                    "signal.ice",
                    session_id,
                    {
                        "from": self.server_signaling_target,
                        "to": client_id,
                        "payload": payload,
                    },
                ),
            )

        @pc.on("track")
        async def _on_track(track) -> None:  # noqa: ANN001
            kind = str(getattr(track, "kind", "") or "unknown").strip() or "unknown"
            track_id = str(getattr(track, "id", "") or "").strip()
            await self._emit_to_client(
                session_id,
                client_id,
                self._event(
                    "webrtc.remote.track.received",
                    session_id,
                    {
                        "from": self.server_signaling_target,
                        "to": client_id,
                        "kind": kind,
                        "track_id": track_id,
                    },
                ),
            )

            if kind == "video":
                text = f"我已收到你的视频流（track_id={track_id or 'unknown'}），当前实时链路正常。"
            elif kind == "audio":
                text = f"我已收到你的音频流（track_id={track_id or 'unknown'}）。"
            else:
                text = f"我已收到你的媒体流（kind={kind}, track_id={track_id or 'unknown'}）。"

            await self._emit_assistant_text(
                session_id=session_id,
                client_id=client_id,
                text=text,
                source="realtime_transport_track_observer",
            )

        try:
            await pc.setRemoteDescription(aiortc["RTCSessionDescription"](sdp=sdp, type=offer_type))
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
        except Exception as exc:
            await self._close_server_peer(session_id, client_id)
            await self._emit_to_client(
                session_id,
                client_id,
                self._event(
                    "signal.error",
                    session_id,
                    {"code": "OFFER_PROCESS_FAILED", "message": str(exc)},
                ),
            )
            return

        await self._set_session_state(session_id, "signaling")
        await self._emit_to_client(
            session_id,
            client_id,
            self._event(
                "signal.answer",
                session_id,
                {
                    "from": self.server_signaling_target,
                    "to": client_id,
                    "payload": {
                        "type": str(pc.localDescription.type),
                        "sdp": str(pc.localDescription.sdp),
                    },
                },
            ),
        )

    async def _handle_server_ice(self, session_id: str, client_id: str, packet: dict[str, Any]) -> None:
        peer = await self._get_server_peer(session_id, client_id)
        if peer is None:
            await self._emit_to_client(
                session_id,
                client_id,
                self._event(
                    "signal.error",
                    session_id,
                    {"code": "SERVER_PEER_NOT_FOUND", "message": "server peer is not initialized"},
                ),
            )
            return

        aiortc = self._import_aiortc()
        if aiortc is None:
            await self._emit_to_client(
                session_id,
                client_id,
                self._event(
                    "signal.error",
                    session_id,
                    {
                        "code": "AIORTC_NOT_AVAILABLE",
                        "message": "aiortc is not installed, server-side WebRTC is unavailable",
                    },
                ),
            )
            return

        payload = self._resolve_payload(packet)
        candidate_text, sdp_mid, sdp_mline_index, username_fragment = self._extract_ice_fields(payload)
        if candidate_text is None:
            try:
                await peer.pc.addIceCandidate(None)
            except Exception as exc:
                await self._emit_to_client(
                    session_id,
                    client_id,
                    self._event(
                        "signal.error",
                        session_id,
                        {"code": "ICE_ADD_FAILED", "message": str(exc)},
                    ),
                )
            return

        candidate = None
        try:
            candidate = aiortc["candidate_from_sdp"](candidate_text)
        except Exception:
            if candidate_text.startswith("candidate:"):
                try:
                    candidate = aiortc["candidate_from_sdp"](candidate_text[len("candidate:"):])
                except Exception as exc:
                    await self._emit_to_client(
                        session_id,
                        client_id,
                        self._event(
                            "signal.error",
                            session_id,
                            {"code": "INVALID_ICE_CANDIDATE", "message": str(exc)},
                        ),
                    )
                    return
            else:
                await self._emit_to_client(
                    session_id,
                    client_id,
                    self._event(
                        "signal.error",
                        session_id,
                        {"code": "INVALID_ICE_CANDIDATE", "message": "invalid candidate format"},
                    ),
                )
                return

        candidate.sdpMid = sdp_mid
        candidate.sdpMLineIndex = sdp_mline_index
        if username_fragment is not None and hasattr(candidate, "usernameFragment"):
            try:
                setattr(candidate, "usernameFragment", username_fragment)
            except Exception:
                pass
        try:
            await peer.pc.addIceCandidate(candidate)
        except Exception as exc:
            await self._emit_to_client(
                session_id,
                client_id,
                self._event(
                    "signal.error",
                    session_id,
                    {"code": "ICE_ADD_FAILED", "message": str(exc)},
                ),
            )

    @staticmethod
    def _import_aiortc() -> dict[str, Any] | None:
        try:
            from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
            from aiortc.sdp import candidate_from_sdp, candidate_to_sdp
        except Exception:
            return None
        try:
            from av import VideoFrame
        except Exception:
            VideoFrame = None
        return {
            "RTCPeerConnection": RTCPeerConnection,
            "RTCSessionDescription": RTCSessionDescription,
            "VideoStreamTrack": VideoStreamTrack,
            "VideoFrame": VideoFrame,
            "candidate_from_sdp": candidate_from_sdp,
            "candidate_to_sdp": candidate_to_sdp,
        }

    async def _set_server_peer(self, session_id: str, client_id: str, pc: Any) -> None:
        async with self._lock:
            self._server_peers[(session_id, client_id)] = _ServerPeer(
                session_id=session_id,
                client_id=client_id,
                pc=pc,
            )

    async def _get_server_peer(self, session_id: str, client_id: str) -> _ServerPeer | None:
        async with self._lock:
            return self._server_peers.get((session_id, client_id))

    async def _close_server_peer(self, session_id: str, client_id: str) -> None:
        peer: _ServerPeer | None
        async with self._lock:
            peer = self._server_peers.pop((session_id, client_id), None)
        if peer is None:
            return
        try:
            await peer.pc.close()
        except Exception:
            pass

    async def _set_session_state(self, session_id: str, state: str) -> None:
        targets: list[WebSocket] = []
        changed = False
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.state == "closed":
                return
            if session.state != state:
                session.state = state
                session.updated_at = _utc_now_iso()
                changed = True
                targets = list(self._connections.get(session_id, {}).values())
        if changed:
            event = self._event("call.state.changed", session_id, {"state": state})
            for ws in targets:
                await self._safe_send(ws, event)

    async def _emit_to_client(self, session_id: str, client_id: str, event: dict[str, Any]) -> None:
        ws: WebSocket | None
        async with self._lock:
            ws = self._connections.get(session_id, {}).get(client_id)
        if ws is not None:
            await self._safe_send(ws, event)

    @staticmethod
    async def _safe_send(websocket: WebSocket, event: dict[str, Any]) -> None:
        try:
            await websocket.send_json(event)
        except Exception:
            pass
