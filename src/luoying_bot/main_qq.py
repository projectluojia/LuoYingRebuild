from __future__ import annotations
import asyncio, logging
from luoying_bot.bootstrap import build_qq_container
logging.basicConfig(level=logging.INFO)

async def main() -> None:
    while True:

        container = None
        scheduler_task = None
        
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
            
            scheduler_task=asyncio.create_task(
                container.scheduler.start(),
                name="luoying-scheduler"
            )
            logging.info('QQ transport 已连接，开始接收消息')
            while True:
                msg=await container.transport.recv_message()
                await container.event_handler.handle(msg)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logging.exception('QQ 主循环异常，5 秒后重连：%s', exc)
        finally:
            if container is not None:
                container.scheduler.stop()

            if scheduler_task is not None:
                scheduler_task.cancel()
                await asyncio.gather(scheduler_task, return_exceptions=True)

            if container is not None:
                await container.transport.close()

        await asyncio.sleep(5)


if __name__ == '__main__':
    asyncio.run(main())
