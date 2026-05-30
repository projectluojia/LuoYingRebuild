from __future__ import annotations
import asyncio, logging

from luoying_bot.bootstrap import build_qq_container
from luoying_bot.infra.logging_setup import configure_logging

configure_logging(logging.INFO)
logger = logging.getLogger(__name__)

async def main() -> None:
    while True:

        container = None
        scheduler_task = None
        
        try:
            #构造container
            container = await build_qq_container()
            logger.info("QQ 应用容器已注册完毕")
            #连接到
            await container.transport.connect()
            logger.info('QQ 已成功连接 Websocket')
            #从提醒恢复
            await container.reminder_service.restore_jobs()
            logger.info('QQ 提醒事件已成功恢复')
            #注册内置计划事件
            container.builtin_schedule_service.register_builtin_jobs()
            logger.info('QQ 内置计划事件已成功注册')
            #启动计划事件
            scheduler_task=asyncio.create_task(
                container.scheduler.start(),
                name="luoying-scheduler"
            )
            logger.info('QQ 计划事件协程已启动')

            logger.info('QQ transport 已就绪')
            while True:
                msg=await container.transport.recv_message()
                if msg.context is None:
                    logger.debug("忽略无上下文 QQ 事件：post_type=%s", msg.raw_event.get("post_type"))
                    continue
                container.message_processor.submit(msg)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception('QQ 主循环异常，5 秒后重连：%s', exc)
        finally:
            if container is not None:
                container.scheduler.stop()

            if scheduler_task is not None:
                scheduler_task.cancel()
                await asyncio.gather(scheduler_task, return_exceptions=True)

            if container is not None:
                await container.message_processor.aclose(cancel_running=True)
                await container.transport.close()

        await asyncio.sleep(5)


if __name__ == '__main__':
    asyncio.run(main())
