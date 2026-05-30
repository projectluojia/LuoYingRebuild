from __future__ import annotations

import asyncio
import logging
from typing import Dict

from luoying_bot.application.event_handler import EventHandler
from luoying_bot.domain.message import UniMessage
from luoying_bot.domain.result import Reply

logger = logging.getLogger(__name__)

class MessageProcessor:

    def __init__(self, event_handler:EventHandler,max_concurrent_tasks: int = 200):
        self.event_handler = event_handler
        self._thread_locks: Dict[str, asyncio.Lock] ={}
        self._tasks: set[asyncio.Task] = set()
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._closed = False

    def _thread_key(self, message: UniMessage)->str:
        if message.context is not None:
            return message.context.thread_id
        return f"raw:{message.uid}"
    
    async def process(self,message: UniMessage)->Reply:
        key=self._thread_key(message)
        lock = self._thread_locks.setdefault(key,asyncio.Lock())
    
        async with self._semaphore:
            async with lock:
                return await self.event_handler.handle(message)
            
    def submit(self,message: UniMessage)->asyncio.Task:
        if self._closed:
            raise RuntimeError("MessageProcessor 已关闭，不能再提交新消息")
        
        key = self._thread_key(message)
        task = asyncio.create_task(
            self.process(message),
            name=f"message:{key}:{message.uid}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._on_task_done)
        logger.info("消息已提交到协程：%s", key)
        return task

    def _on_task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("消息任务执行失败")

    async def aclose(self,cancel_running:bool=False)->None:
        self._closed = True
        tasks = list(self._tasks)
        if cancel_running:
            for task in tasks:
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks,return_exceptions=True)
        self._tasks.clear()
        logger.info("所有协程已关闭")
