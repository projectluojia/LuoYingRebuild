from __future__ import annotations
import asyncio, logging
from luoying_bot.bootstrap import build_qq_container
logging.basicConfig(level=logging.INFO)

async def main() -> None:
    while True:
        try:
            #构造container
            container = await build_qq_container()
            #连接到
            await container.transport.connect()
            #从提醒恢复
            await container.reminder_service.restore_jobs()
            #注册内置计划事件
            container.builtin_schedule_service.register_builtin_jobs()
            #启动计划事件
            asyncio.create_task(container.scheduler.start())
            logging.info('QQ transport 已连接，开始接收消息')
            while True:
                await container.event_handler.handle(await container.transport.recv_message())
        except Exception as exc:
            logging.exception('QQ 主循环异常，5 秒后重连：%s', exc)
            await asyncio.sleep(5)

if __name__ == '__main__':
    asyncio.run(main())
