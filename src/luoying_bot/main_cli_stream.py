from __future__ import annotations

import argparse
import asyncio
import contextlib

from luoying_bot.bootstrap import build_cli_container
from luoying_bot.domain.message import UniMessage
from luoying_bot.infra.cli.tui import CliTui
from luoying_bot.infra.transports.cli_transport import CliTransport

EXIT_WORDS = {"exit", "quit", "q", "退出", "再见"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Luoying CLI 完整链路入口")
    parser.add_argument("--session-id", default="cli-session", help="CLI 会话 ID")
    parser.add_argument("--user-id", default="cli-user", help="CLI 用户 ID")
    parser.add_argument("--user-name", default="CLI用户", help="CLI 用户昵称")
    return parser


async def _render_transport_events(
    tui: CliTui,
    transport: CliTransport,
    processing_task: asyncio.Task,
) -> None:
    while True:
        if processing_task.done() and transport.events.empty():
            break

        try:
            event = await asyncio.wait_for(transport.events.get(), timeout=0.1)
        except asyncio.TimeoutError:
            continue

        event_type = event.get("type")
        if event_type == "track":
            tui.track(str(event.get("text") or ""))
        elif event_type == "text":
            tui.assistant(str(event.get("text") or ""))
        elif event_type == "text_start":
            tui.assistant_stream_start()
        elif event_type == "text_delta":
            tui.assistant_stream_delta(str(event.get("text") or ""))
        elif event_type == "text_end":
            tui.assistant_stream_end()
        elif event_type == "file":
            tui.file(str(event.get("file") or ""))
        elif event_type == "script_result":
            result = event.get("result") or {}
            timeout = result.get("timeout")
            exit_code = "timeout" if timeout and timeout is not False else result.get("returncode")
            tui.info(
                "\n".join(
                    [
                        f"脚本运行结果：{result.get('file_path') or '(unknown)'}",
                        f"args: {result.get('args') or '(none)'}",
                        f"exit_code: {exit_code}",
                        "",
                        "[stdout]",
                        str(result.get("stdout") or "(empty)"),
                        "",
                        "[stderr]",
                        str(result.get("stderr") or "(empty)"),
                    ]
                )
            )
        else:
            tui.info(str(event))

    try:
        await processing_task
    except Exception as exc:
        tui.error(f"{type(exc).__name__}: {exc}")


async def main() -> None:
    args = _build_parser().parse_args()
    tui = CliTui()
    container = await build_cli_container()
    transport = container.transport
    if not isinstance(transport, CliTransport):
        raise RuntimeError("CLI 入口需要 CliTransport")

    scheduler_task: asyncio.Task | None = None

    try:
        await transport.connect()
        await container.reminder_service.restore_jobs()
        scheduler_task = asyncio.create_task(container.scheduler.start(), name="luoying-cli-scheduler")

        tui.banner()
        while True:
            text = await asyncio.to_thread(tui.prompt)
            if not text:
                continue
            if text.lower() in EXIT_WORDS:
                break

            message = UniMessage.from_cli_text(
                session_id=args.session_id,
                user_id=args.user_id,
                user_name=args.user_name,
                text=text,
            )
            processing_task = asyncio.create_task(
                container.message_processor.process(message),
                name=f"cli-message:{message.uid}",
            )
            await _render_transport_events(tui, transport, processing_task)

    finally:
        container.scheduler.stop()
        if scheduler_task is not None:
            scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler_task
        await container.message_processor.aclose(cancel_running=True)
        await transport.close()


if __name__ == "__main__":
    asyncio.run(main())
