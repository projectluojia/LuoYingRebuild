from __future__ import annotations

import asyncio
import sys
import unittest
from asyncio import run as asyncio_run
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from luoying_bot.infra.transports.realtime_ws_transport import RealtimeWsTransport


class _FakeWebSocket:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def send_json(self, event: dict[str, Any]) -> None:
        self.events.append(event)


class _FakeRTCSessionDescription:
    def __init__(self, sdp: str, type: str) -> None:
        self.sdp = sdp
        self.type = type


class _FakeCandidate:
    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.sdpMid: str | None = None
        self.sdpMLineIndex: int | None = None
        self.usernameFragment: str | None = None


class _FakePeerConnection:
    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}
        self.localDescription: _FakeRTCSessionDescription | None = None
        self.remoteDescription: _FakeRTCSessionDescription | None = None
        self.connectionState: str = "new"
        self.iceConnectionState: str = "new"
        self.added_candidates: list[Any] = []
        self.added_tracks: list[Any] = []
        self.closed = False

    def on(self, event_name: str):  # noqa: ANN001
        def _register(handler):  # noqa: ANN001
            self.handlers[event_name] = handler
            return handler

        return _register

    async def setRemoteDescription(self, desc: _FakeRTCSessionDescription) -> None:
        self.remoteDescription = desc

    async def createAnswer(self) -> _FakeRTCSessionDescription:
        return _FakeRTCSessionDescription(sdp="fake-answer-sdp", type="answer")

    async def setLocalDescription(self, desc: _FakeRTCSessionDescription) -> None:
        self.localDescription = desc

    async def addIceCandidate(self, candidate: Any) -> None:
        self.added_candidates.append(candidate)

    def addTrack(self, track: Any) -> None:  # noqa: ANN401
        self.added_tracks.append(track)

    async def close(self) -> None:
        self.closed = True


class _FakePlane:
    def __init__(self, buffer_size: int) -> None:
        self.buffer_size = buffer_size
        self.updated: bytes | None = None

    def update(self, data: bytes) -> None:
        self.updated = data


class _FakeVideoFrame:
    def __init__(self, width: int, height: int, format: str) -> None:  # noqa: A002
        self.width = width
        self.height = height
        self.format = format
        self.planes = [
            _FakePlane(width * height),
            _FakePlane((width * height) // 4),
            _FakePlane((width * height) // 4),
        ]
        self.pts: int | None = None
        self.time_base: int | None = None


class _FakeVideoStreamTrack:
    def __init__(self) -> None:
        self._pts = 0

    async def next_timestamp(self) -> tuple[int, int]:
        self._pts += 3000
        return self._pts, 90000


class _FakeRemoteTrack:
    def __init__(self, kind: str, track_id: str) -> None:
        self.kind = kind
        self.id = track_id


class RealtimeWsTransportTest(unittest.TestCase):
    @staticmethod
    async def _prepare_transport() -> tuple[RealtimeWsTransport, str, str, _FakeWebSocket]:
        transport = RealtimeWsTransport(server_signaling_target="server")
        created = await transport.create_session(owner_id="u_test", metadata={"source": "test"})
        session_id = str(created["session_id"])
        client_id = "client_a"
        ws = _FakeWebSocket()
        async with transport._lock:
            transport._connections[session_id][client_id] = ws
        return transport, session_id, client_id, ws

    def test_server_offer_with_nested_payload_returns_answer(self) -> None:
        async def _run() -> None:
            transport, session_id, client_id, ws = await self._prepare_transport()
            fake_pc = _FakePeerConnection()

            def _candidate_from_sdp(raw: str) -> _FakeCandidate:
                return _FakeCandidate(raw)

            transport._import_aiortc = lambda: {  # type: ignore[assignment]
                "RTCPeerConnection": lambda: fake_pc,
                "RTCSessionDescription": _FakeRTCSessionDescription,
                "candidate_from_sdp": _candidate_from_sdp,
                "candidate_to_sdp": lambda candidate: candidate.raw,
            }

            handled = await transport._handle_server_signal(
                session_id=session_id,
                from_client_id=client_id,
                msg_type="signal.offer",
                packet={
                    "type": "signal.offer",
                    "to": "server",
                    "payload": {
                        "offer": {"type": "offer", "sdp": "v=0 fake-offer"},
                    },
                },
            )
            self.assertTrue(handled)
            answer_events = [event for event in ws.events if event.get("type") == "signal.answer"]
            self.assertEqual(len(answer_events), 1)
            payload = answer_events[0].get("payload", {}).get("payload", {})
            self.assertEqual(payload.get("type"), "answer")
            self.assertEqual(payload.get("sdp"), "fake-answer-sdp")
            server_peer = await transport._get_server_peer(session_id, client_id)
            self.assertIsNotNone(server_peer)

        asyncio_run(_run())

    def test_server_ice_accepts_candidate_object_payload(self) -> None:
        async def _run() -> None:
            transport, session_id, client_id, ws = await self._prepare_transport()
            fake_pc = _FakePeerConnection()

            def _candidate_from_sdp(raw: str) -> _FakeCandidate:
                return _FakeCandidate(raw)

            transport._import_aiortc = lambda: {  # type: ignore[assignment]
                "RTCPeerConnection": lambda: fake_pc,
                "RTCSessionDescription": _FakeRTCSessionDescription,
                "candidate_from_sdp": _candidate_from_sdp,
                "candidate_to_sdp": lambda candidate: candidate.raw,
            }

            await transport._set_server_peer(session_id, client_id, fake_pc)
            handled = await transport._handle_server_signal(
                session_id=session_id,
                from_client_id=client_id,
                msg_type="signal.ice",
                packet={
                    "type": "signal.ice",
                    "to": "server",
                    "payload": {
                        "candidate": {
                            "candidate": "candidate:demo-1",
                            "sdpMid": "0",
                            "sdpMLineIndex": "1",
                            "usernameFragment": "ufrag-1",
                        }
                    },
                },
            )
            self.assertTrue(handled)
            self.assertEqual(len(fake_pc.added_candidates), 1)
            parsed_candidate = fake_pc.added_candidates[0]
            self.assertIsInstance(parsed_candidate, _FakeCandidate)
            self.assertEqual(parsed_candidate.raw, "candidate:demo-1")
            self.assertEqual(parsed_candidate.sdpMid, "0")
            self.assertEqual(parsed_candidate.sdpMLineIndex, 1)
            self.assertEqual(parsed_candidate.usernameFragment, "ufrag-1")
            errors = [event for event in ws.events if event.get("type") == "signal.error"]
            self.assertEqual(errors, [])

        asyncio_run(_run())

    def test_server_ice_empty_candidate_treated_as_end_of_candidates(self) -> None:
        async def _run() -> None:
            transport, session_id, client_id, _ = await self._prepare_transport()
            fake_pc = _FakePeerConnection()
            await transport._set_server_peer(session_id, client_id, fake_pc)

            transport._import_aiortc = lambda: {  # type: ignore[assignment]
                "RTCPeerConnection": lambda: fake_pc,
                "RTCSessionDescription": _FakeRTCSessionDescription,
                "candidate_from_sdp": lambda raw: _FakeCandidate(raw),
                "candidate_to_sdp": lambda candidate: candidate.raw,
            }

            handled = await transport._handle_server_signal(
                session_id=session_id,
                from_client_id=client_id,
                msg_type="signal.ice",
                packet={
                    "type": "signal.ice",
                    "to": "server",
                    "payload": {"candidate": ""},
                },
            )
            self.assertTrue(handled)
            self.assertEqual(fake_pc.added_candidates, [None])

        asyncio_run(_run())

    def test_server_offer_without_aiortc_emits_structured_error(self) -> None:
        async def _run() -> None:
            transport, session_id, client_id, ws = await self._prepare_transport()
            transport._import_aiortc = lambda: None  # type: ignore[assignment]

            handled = await transport._handle_server_signal(
                session_id=session_id,
                from_client_id=client_id,
                msg_type="signal.offer",
                packet={
                    "type": "signal.offer",
                    "to": "server",
                    "payload": {"type": "offer", "sdp": "v=0 fake-offer"},
                },
            )
            self.assertTrue(handled)
            errors = [event for event in ws.events if event.get("type") == "signal.error"]
            self.assertEqual(len(errors), 1)
            self.assertEqual(errors[0].get("payload", {}).get("code"), "AIORTC_NOT_AVAILABLE")

        asyncio_run(_run())

    def test_server_offer_attaches_placeholder_video_track_when_available(self) -> None:
        async def _run() -> None:
            transport, session_id, client_id, ws = await self._prepare_transport()
            fake_pc = _FakePeerConnection()

            def _candidate_from_sdp(raw: str) -> _FakeCandidate:
                return _FakeCandidate(raw)

            transport._import_aiortc = lambda: {  # type: ignore[assignment]
                "RTCPeerConnection": lambda: fake_pc,
                "RTCSessionDescription": _FakeRTCSessionDescription,
                "VideoStreamTrack": _FakeVideoStreamTrack,
                "VideoFrame": _FakeVideoFrame,
                "candidate_from_sdp": _candidate_from_sdp,
                "candidate_to_sdp": lambda candidate: candidate.raw,
            }

            handled = await transport._handle_server_signal(
                session_id=session_id,
                from_client_id=client_id,
                msg_type="signal.offer",
                packet={
                    "type": "signal.offer",
                    "to": "server",
                    "payload": {
                        "offer": {"type": "offer", "sdp": "v=0 fake-offer"},
                    },
                },
            )
            self.assertTrue(handled)
            self.assertEqual(len(fake_pc.added_tracks), 1)
            media_events = [event for event in ws.events if event.get("type") == "webrtc.media.track.ready"]
            self.assertEqual(len(media_events), 1)
            payload = media_events[0].get("payload", {})
            self.assertEqual(payload.get("kind"), "video")
            self.assertEqual(payload.get("source"), "placeholder")

        asyncio_run(_run())

    def test_server_track_event_emits_assistant_text_confirmation(self) -> None:
        async def _run() -> None:
            transport, session_id, client_id, ws = await self._prepare_transport()
            fake_pc = _FakePeerConnection()

            def _candidate_from_sdp(raw: str) -> _FakeCandidate:
                return _FakeCandidate(raw)

            transport._import_aiortc = lambda: {  # type: ignore[assignment]
                "RTCPeerConnection": lambda: fake_pc,
                "RTCSessionDescription": _FakeRTCSessionDescription,
                "VideoStreamTrack": _FakeVideoStreamTrack,
                "VideoFrame": _FakeVideoFrame,
                "candidate_from_sdp": _candidate_from_sdp,
                "candidate_to_sdp": lambda candidate: candidate.raw,
            }

            handled = await transport._handle_server_signal(
                session_id=session_id,
                from_client_id=client_id,
                msg_type="signal.offer",
                packet={
                    "type": "signal.offer",
                    "to": "server",
                    "payload": {
                        "offer": {"type": "offer", "sdp": "v=0 fake-offer"},
                    },
                },
            )
            self.assertTrue(handled)
            self.assertIn("track", fake_pc.handlers)

            await fake_pc.handlers["track"](_FakeRemoteTrack(kind="video", track_id="remote_v_1"))
            received_events = [event.get("type") for event in ws.events]
            self.assertIn("webrtc.remote.track.received", received_events)
            self.assertIn("assistant.text.start", received_events)
            self.assertIn("assistant.text.delta", received_events)
            self.assertIn("assistant.text.final", received_events)

            final_events = [event for event in ws.events if event.get("type") == "assistant.text.final"]
            self.assertGreaterEqual(len(final_events), 1)
            track_observer_final = next(
                (
                    event
                    for event in final_events
                    if str(event.get("payload", {}).get("source") or "") == "realtime_transport_track_observer"
                ),
                final_events[0],
            )
            final_payload = track_observer_final.get("payload", {})
            final_text = str(final_payload.get("text") or "")
            self.assertIn("视频流", final_text)
            self.assertIn("remote_v_1", final_text)

        asyncio_run(_run())

    def test_video_track_semantic_analysis_emits_additional_assistant_text(self) -> None:
        async def _run() -> None:
            transport, session_id, client_id, ws = await self._prepare_transport()
            fake_pc = _FakePeerConnection()

            async def _fake_describe_video_track_semantic(track: Any, track_id: str) -> str | None:  # noqa: ARG001
                return f"语义分析：画面中有一只猫（track_id={track_id}）"

            transport._describe_video_track_semantic = _fake_describe_video_track_semantic  # type: ignore[assignment]

            def _candidate_from_sdp(raw: str) -> _FakeCandidate:
                return _FakeCandidate(raw)

            transport._import_aiortc = lambda: {  # type: ignore[assignment]
                "RTCPeerConnection": lambda: fake_pc,
                "RTCSessionDescription": _FakeRTCSessionDescription,
                "VideoStreamTrack": _FakeVideoStreamTrack,
                "VideoFrame": _FakeVideoFrame,
                "candidate_from_sdp": _candidate_from_sdp,
                "candidate_to_sdp": lambda candidate: candidate.raw,
            }

            handled = await transport._handle_server_signal(
                session_id=session_id,
                from_client_id=client_id,
                msg_type="signal.offer",
                packet={
                    "type": "signal.offer",
                    "to": "server",
                    "payload": {
                        "offer": {"type": "offer", "sdp": "v=0 fake-offer"},
                    },
                },
            )
            self.assertTrue(handled)
            self.assertIn("track", fake_pc.handlers)

            await fake_pc.handlers["track"](_FakeRemoteTrack(kind="video", track_id="remote_v_2"))
            await asyncio.sleep(0.01)

            semantic_final_events = [
                event
                for event in ws.events
                if event.get("type") == "assistant.text.final"
                and str(event.get("payload", {}).get("source") or "") == "realtime_transport_video_semantic"
            ]
            self.assertGreaterEqual(len(semantic_final_events), 1)
            semantic_text = str(semantic_final_events[-1].get("payload", {}).get("text") or "")
            self.assertIn("语义分析", semantic_text)
            self.assertIn("remote_v_2", semantic_text)

        asyncio_run(_run())


if __name__ == "__main__":
    unittest.main(verbosity=2)
