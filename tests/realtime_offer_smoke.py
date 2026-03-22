from __future__ import annotations

import argparse
import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import websockets


def _http_json(
    url: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any]]:
    payload: bytes | None = None
    headers: dict[str, str] = {}
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url=url, data=payload, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = int(getattr(response, "status", 200))
        raw = response.read().decode("utf-8", errors="replace")
    data = json.loads(raw) if raw.strip() else {}
    return status, data


def _parse_server_candidate(raw_candidate: str, candidate_from_sdp_fn: Any) -> Any:
    try:
        return candidate_from_sdp_fn(raw_candidate)
    except Exception:
        if raw_candidate.startswith("candidate:"):
            return candidate_from_sdp_fn(raw_candidate[len("candidate:") :])
        raise


async def _run(args: argparse.Namespace) -> int:
    try:
        from aiortc import RTCPeerConnection, RTCSessionDescription
        from aiortc.sdp import candidate_from_sdp, candidate_to_sdp
    except Exception as exc:
        print(f"[FAIL] aiortc unavailable: {type(exc).__name__}: {exc}")
        return 2

    base_url = args.base_url.strip().rstrip("/")
    parsed = urllib.parse.urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        print(f"[FAIL] invalid --base-url: {base_url!r}")
        return 2

    if parsed.scheme == "https":
        ws_scheme = "wss"
    elif parsed.scheme == "http":
        ws_scheme = "ws"
    else:
        print(f"[FAIL] unsupported base-url scheme: {parsed.scheme}")
        return 2

    health_url = f"{base_url}/realtime/health"
    create_url = f"{base_url}/realtime/sessions"
    close_url_tpl = f"{base_url}/realtime/sessions/{{session_id}}/close"

    try:
        health_status, health_data = _http_json(health_url, timeout=args.http_timeout)
    except Exception as exc:
        print(f"[FAIL] health check failed: {type(exc).__name__}: {exc}")
        return 1
    print(f"[INFO] health status={health_status} body={json.dumps(health_data, ensure_ascii=False)}")

    try:
        create_status, create_data = _http_json(
            create_url,
            method="POST",
            body={"owner_id": args.owner_id, "metadata": {"source": "realtime_offer_smoke"}},
            timeout=args.http_timeout,
        )
    except Exception as exc:
        print(f"[FAIL] create session failed: {type(exc).__name__}: {exc}")
        return 1
    if create_status != 200:
        print(f"[FAIL] create session status={create_status} body={create_data}")
        return 1

    session = create_data.get("session", {})
    session_id = str(session.get("session_id") or "").strip()
    if not session_id:
        print(f"[FAIL] missing session_id in response: {create_data}")
        return 1
    print(f"[OK] created session_id={session_id}")

    ws_url = (
        f"{ws_scheme}://{parsed.netloc}/realtime/ws/{session_id}"
        f"?client_id={urllib.parse.quote(args.client_id)}&role={urllib.parse.quote(args.role)}"
    )
    print(f"[INFO] ws_url={ws_url}")

    pc = RTCPeerConnection()
    pc.addTransceiver("video", direction="recvonly")
    if args.send_video:
        try:
            from aiortc import VideoStreamTrack
            from av import VideoFrame
        except Exception as exc:
            print(f"[FAIL] --send-video requires VideoStreamTrack + av.VideoFrame: {type(exc).__name__}: {exc}")
            return 2

        class _DummySendVideoTrack(VideoStreamTrack):
            def __init__(self) -> None:
                super().__init__()
                self._luma_tick = 0

            async def recv(self):  # noqa: ANN202
                pts, time_base = await self.next_timestamp()
                frame = VideoFrame(width=320, height=180, format="yuv420p")
                self._luma_tick = (self._luma_tick + 3) % 220
                luma = 16 + self._luma_tick
                frame.planes[0].update(bytes([luma]) * frame.planes[0].buffer_size)
                frame.planes[1].update(bytes([128]) * frame.planes[1].buffer_size)
                frame.planes[2].update(bytes([128]) * frame.planes[2].buffer_size)
                frame.pts = pts
                frame.time_base = time_base
                return frame

        pc.addTrack(_DummySendVideoTrack())
        print("[INFO] local dummy video track added (send_video=True)")

    got_joined = False
    got_track_ready = False
    got_answer = False
    got_connected = False
    got_assistant_final = False
    got_assistant_semantic_final = False
    assistant_final_sources: set[str] = set()
    seen_events = 0

    @pc.on("connectionstatechange")
    async def _on_connection_state_change() -> None:
        print(f"[INFO] local pc.connectionState={pc.connectionState}")

    @pc.on("track")
    def _on_track(track: Any) -> None:
        print(f"[INFO] local on_track kind={getattr(track, 'kind', 'unknown')}")

    try:
        async with websockets.connect(ws_url, open_timeout=args.ws_timeout) as ws:
            async def _send_local_ice(candidate: Any) -> None:
                payload: dict[str, Any]
                if candidate is None:
                    payload = {"candidate": None, "sdpMid": None, "sdpMLineIndex": None}
                else:
                    candidate_text = candidate_to_sdp(candidate)
                    if not str(candidate_text).startswith("candidate:"):
                        candidate_text = f"candidate:{candidate_text}"
                    payload = {
                        "candidate": candidate_text,
                        "sdpMid": getattr(candidate, "sdpMid", None),
                        "sdpMLineIndex": getattr(candidate, "sdpMLineIndex", None),
                    }
                    username_fragment = getattr(candidate, "usernameFragment", None)
                    if username_fragment:
                        payload["usernameFragment"] = str(username_fragment)

                await ws.send(
                    json.dumps(
                        {
                            "type": "signal.ice",
                            "to": "server",
                            "payload": payload,
                        }
                    )
                )

            @pc.on("icecandidate")
            async def _on_ice_candidate(candidate: Any) -> None:
                await _send_local_ice(candidate)

            offer = await pc.createOffer()
            await pc.setLocalDescription(offer)
            await ws.send(
                json.dumps(
                    {
                        "type": "signal.offer",
                        "to": "server",
                        "payload": {
                            "offer": {
                                "type": str(pc.localDescription.type),
                                "sdp": str(pc.localDescription.sdp),
                            }
                        },
                    }
                )
            )
            print("[OK] sent signal.offer -> to: server")

            loop = asyncio.get_running_loop()
            deadline = loop.time() + args.recv_timeout
            while seen_events < args.max_events and loop.time() < deadline:
                remaining = deadline - loop.time()
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, remaining))
                seen_events += 1
                msg = json.loads(raw)
                msg_type = str(msg.get("type") or "")
                payload = msg.get("payload", {})
                print(f"[EVENT] {msg_type}")

                if msg_type == "session.joined":
                    got_joined = True
                elif msg_type == "webrtc.media.track.ready":
                    if isinstance(payload, dict) and payload.get("kind") == "video":
                        got_track_ready = True
                elif msg_type == "signal.answer":
                    inner = payload.get("payload", {}) if isinstance(payload, dict) else {}
                    answer_sdp = str(inner.get("sdp") or "")
                    answer_type = str(inner.get("type") or "")
                    if answer_sdp and answer_type:
                        await pc.setRemoteDescription(
                            RTCSessionDescription(sdp=answer_sdp, type=answer_type)
                        )
                        got_answer = True
                elif msg_type == "signal.ice":
                    inner = payload.get("payload", {}) if isinstance(payload, dict) else {}
                    if isinstance(inner, dict):
                        raw_candidate = inner.get("candidate")
                        if raw_candidate is None or str(raw_candidate).strip() == "":
                            await pc.addIceCandidate(None)
                        else:
                            candidate = _parse_server_candidate(str(raw_candidate), candidate_from_sdp)
                            candidate.sdpMid = inner.get("sdpMid")
                            mline = inner.get("sdpMLineIndex")
                            candidate.sdpMLineIndex = int(mline) if mline is not None else None
                            username_fragment = inner.get("usernameFragment")
                            if username_fragment is not None and hasattr(candidate, "usernameFragment"):
                                setattr(candidate, "usernameFragment", str(username_fragment))
                            await pc.addIceCandidate(candidate)
                elif msg_type == "webrtc.state.changed":
                    if isinstance(payload, dict) and str(payload.get("state") or "") == "connected":
                        got_connected = True
                elif msg_type == "assistant.text.final":
                    got_assistant_final = True
                    if isinstance(payload, dict):
                        source = str(payload.get("source") or "").strip()
                        if source:
                            assistant_final_sources.add(source)
                        if source == args.semantic_source:
                            got_assistant_semantic_final = True

                success = got_joined and got_track_ready and got_answer
                if args.require_connected:
                    success = success and got_connected
                if args.send_video:
                    success = success and got_assistant_final
                if args.require_semantic:
                    success = success and got_assistant_semantic_final
                if success:
                    break
    except asyncio.TimeoutError:
        print("[FAIL] websocket recv timed out")
        return 1
    except websockets.WebSocketException as exc:
        print(f"[FAIL] websocket error: {type(exc).__name__}: {exc}")
        return 1
    finally:
        try:
            await pc.close()
        except Exception:
            pass

        try:
            close_url = close_url_tpl.format(session_id=session_id)
            _http_json(
                close_url,
                method="POST",
                body={"reason": "realtime_offer_smoke_done"},
                timeout=args.http_timeout,
            )
            print("[INFO] session closed")
        except urllib.error.HTTPError as exc:
            print(f"[WARN] close session http error: {exc.code} {exc.reason}")
        except Exception as exc:
            print(f"[WARN] close session failed: {type(exc).__name__}: {exc}")

    print(
        "[INFO] summary "
        f"joined={got_joined}, track_ready={got_track_ready}, answer={got_answer}, "
        f"connected={got_connected}, assistant_final={got_assistant_final}, "
        f"assistant_semantic_final={got_assistant_semantic_final}, "
        f"assistant_final_sources={sorted(assistant_final_sources)}, "
        f"events={seen_events}"
    )
    if not got_joined:
        print("[FAIL] missing session.joined")
        return 1
    if not got_track_ready:
        print("[FAIL] missing webrtc.media.track.ready(video)")
        return 1
    if not got_answer:
        print("[FAIL] missing signal.answer")
        return 1
    if args.require_connected and not got_connected:
        print("[FAIL] missing webrtc.state.changed=connected")
        return 1
    if args.send_video and not got_assistant_final:
        print("[FAIL] missing assistant.text.final when send_video is enabled")
        return 1
    if args.require_semantic and not got_assistant_semantic_final:
        print(
            "[FAIL] missing semantic assistant.text.final "
            f"(source={args.semantic_source!r})"
        )
        return 1

    print("[OK] realtime offer smoke passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Realtime offer smoke: create session, send offer to server, verify answer + placeholder video track."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8010", help="Realtime service base URL")
    parser.add_argument("--owner-id", default="smoke_user", help="Owner id for create session")
    parser.add_argument("--client-id", default="smoke_client", help="WebSocket client id")
    parser.add_argument("--role", default="peer", help="WebSocket role")
    parser.add_argument("--http-timeout", type=float, default=10.0, help="HTTP timeout seconds")
    parser.add_argument("--ws-timeout", type=float, default=10.0, help="WebSocket connect timeout seconds")
    parser.add_argument("--recv-timeout", type=float, default=20.0, help="WebSocket receive loop timeout seconds")
    parser.add_argument("--max-events", type=int, default=40, help="Max received WS events before stop")
    parser.add_argument(
        "--send-video",
        action="store_true",
        help="Add a local dummy outbound video track and require assistant.text.final confirmation from server.",
    )
    parser.add_argument(
        "--require-semantic",
        action="store_true",
        help="Require assistant.text.final from semantic source (default: realtime_transport_video_semantic).",
    )
    parser.add_argument(
        "--semantic-source",
        default="realtime_transport_video_semantic",
        help="assistant.text.final payload.source expected when --require-semantic is enabled.",
    )
    parser.add_argument(
        "--require-connected",
        action="store_true",
        help="Also require webrtc.state.changed=connected before success",
    )
    args = parser.parse_args()
    if args.require_semantic and not args.send_video:
        args.send_video = True
        print("[INFO] --require-semantic enabled, auto set --send-video=true")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
