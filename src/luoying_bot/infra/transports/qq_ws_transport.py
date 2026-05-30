from __future__ import annotations
import asyncio, json, os, re, tempfile, uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx
import websockets
import logging
from PIL import Image
from luoying_bot.config import Settings
from luoying_bot.domain.context import ChannelType, ChatContext, ConversationTarget, Platform, UserIdentity
from luoying_bot.domain.message import UniMessage
from luoying_bot.ports.transport import ChatTransport

logger = logging.getLogger(__name__)
MAX_QQ_FILE_DOWNLOAD_BYTES = 25 * 1024 * 1024

# QQ平台适配器

class QQWsTransport(ChatTransport):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.platform = Platform.QQ
        self.websocket = None

        self._reader_task: asyncio.Task | None = None
        self._event_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=1000)
        self._pending_calls: dict[str, asyncio.Future] = {}
        self._send_lock = asyncio.Lock()

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            await asyncio.gather(self._reader_task, return_exceptions=True)
            self._reader_task = None

        if self.websocket is not None:
            try:
                await self.websocket.close()
            except Exception:
                pass
            self.websocket = None

        for fut in self._pending_calls.values():
            if not fut.done():
                fut.set_exception(RuntimeError("QQ transport 已关闭"))
        self._pending_calls.clear()

        self._event_queue = asyncio.Queue(maxsize=1000)


    #连接到WebSocket
    async def connect(self) -> None:
        await self.close()
        self.websocket = await websockets.connect(
            self.settings.ws_url,
            additional_headers={"Authorization": f"Bearer {self.settings.ws_token}"},
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
        )
        self._reader_task = asyncio.create_task(self._reader_loop(), name="qq-ws-reader")

    async def _reader_loop(self) -> None:
        try:
            while True:
                if not self.websocket:
                    raise RuntimeError("websocket 未连接")

                raw = await self.websocket.recv()
                data = json.loads(raw)
                print(json.dumps(data, ensure_ascii=False, indent=4))

                echo_id = data.get("echo")
                if echo_id:
                    fut = self._pending_calls.pop(echo_id, None)
                    if fut is not None and not fut.done():
                        fut.set_result(data)
                    continue

                await self._event_queue.put(data)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            for fut in self._pending_calls.values():
                if not fut.done():
                    fut.set_exception(RuntimeError(f"reader_loop 异常退出：{exc}"))
            self._pending_calls.clear()

            # 给主循环一个明确错误信号
            await self._event_queue.put({
                "post_type": "__transport_error__",
                "error": str(exc),
            })


    #发送一个东西，看不懂这个函数先往下看
    async def _send_raw(self, data: Dict[str, Any]) -> None:
        if not self.websocket:
            raise RuntimeError('QQ transport 尚未连接')
        async with self._send_lock:
            await self.websocket.send(json.dumps(data, ensure_ascii=False))
    
    #拉取一个东西，看不懂往下看
    async def _call(self, action: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if not self.websocket:
            raise RuntimeError('QQ transport 尚未连接')
        echo_id=str(uuid.uuid4())
        fut = asyncio.get_running_loop().create_future()
        self._pending_calls[echo_id]=fut

        try:
            await self._send_raw(
                {
                    "action":action,
                    "params":params or {},
                    "echo":echo_id,
                }
            )
            return await asyncio.wait_for(fut,timeout=15)
        except Exception:
            self._pending_calls.pop(echo_id,None)
            raise
        
    #抓取到用户的昵称        
    def _extract_user_name(self, data: Dict[str, Any]) -> Optional[str]:
        sender = data.get('sender', {})
        return (sender.get('nickname') or sender.get('card')) if isinstance(sender, dict) else None
    
    #获取回复消息的id
    def _find_reply_message_id(self,segments:list[tuple[str,dict]])->str|None:
        for seg_type,seg_data in segments:
            if seg_type=='reply':
                mid=str(seg_data.get('message_id') or '').strip()
                if mid:
                    return mid
        return None

    #将消息解析成unimessage消息段数组
    def _parse_segments(self, message_field: Any, raw_message: str) -> list[tuple[str, dict]]:
        segments: list[tuple[str, dict]] = []
        
        #如果选择了array模式
        if isinstance(message_field, list):
            #直接用现成的OneBot message段
            for seg in message_field:
                seg_type = seg.get('type'); seg_data = seg.get('data', {})
                if seg_type == 'text':
                    segments.append(('text', {'text': seg_data.get('text', '')}))
                elif seg_type == 'at': 
                    segments.append(('at', {'user_id': str(seg_data.get('qq', ''))}))
                elif seg_type == 'reply': 
                    segments.append(('reply', {'message_id': str(seg_data.get('id', ''))}))
                elif seg_type == 'face': 
                    segments.append(('face', {'face_id': str(seg_data.get('id', ''))}))
                elif seg_type == 'image': 
                    segments.append(('image', {'file': seg_data.get('file', '')}))
                else: 
                    segments.append((seg_type or 'unknown', seg_data))
            return segments
        
        #否则手动用正则表达式解析CQ码
        #这几托正则表达式没测试过
        #建议永远不要用上！
        for reply_id in re.findall(r'\[CQ:reply,id=([0-9-]+)\]', raw_message):
            segments.append(('reply', {'message_id': reply_id}))
        for qq in re.findall(r'\[CQ:at,qq=([0-9]+)\]', raw_message):
            segments.append(('at', {'user_id': qq}))
        for file_name in re.findall(r'\[CQ:image,[^\]]*file=([^,\]]+)', raw_message):
            segments.append(('image', {'file': file_name}))
        text = re.sub(r'\[CQ:[^\]]+\]', '', raw_message).strip()
        if text: segments.append(('text', {'text': text}))
        return segments
    
    async def _build_unimessage_from_event(
        self,
        data:Dict[str,Any],
        *,
        fetch_reply:bool,
        keep_reply_segment:bool
    )->UniMessage:
        context=ChatContext(
            user=UserIdentity(
                user_id=str(data.get('user_id') or ''),
                user_name=self._extract_user_name(data)
            ),
            target=ConversationTarget(
                channel_type=ChannelType.GROUP if data.get('message_type') == 'group' else ChannelType.PRIVATE,
                conversation_id=str(data.get('group_id') or data.get('user_id') or ''),
                platform=Platform.QQ,
                group_name=data.get('group_name')
            ),
            message_id=str(data.get('message_id') or ''),
            request_uid=str(uuid.uuid4())
        )
        msg = UniMessage(
            platform=Platform.QQ,
            raw_event=data,
            context=context
        )

        raw_message = data.get('raw_message', '') or ''
        message_field = data.get('message', raw_message)
        parsed_segments = self._parse_segments(message_field, raw_message)

        reply_to_message_id=self._find_reply_message_id(parsed_segments)
        context.reply_to_message_id=reply_to_message_id

        if context.target.channel_type == ChannelType.PRIVATE:
            await self._download_private_file_segments(context, parsed_segments)

        for seg_type, seg_data in parsed_segments:
            if seg_type == 'reply' and not keep_reply_segment:
                continue
            msg.add_segment(seg_type, **seg_data)

        if fetch_reply and reply_to_message_id:
            try:
                reply_data = await self.fetch_message(reply_to_message_id)
            except Exception:
                reply_data = None

            if isinstance(reply_data, dict):
                msg.reply_message = await self._build_unimessage_from_event(
                    reply_data,
                    fetch_reply=False,
                    keep_reply_segment=False,
                )

        return msg
        

    #接受onebot事件
    async def recv_message(self) -> UniMessage:

        data: Dict[str, Any] = await self._event_queue.get()
        if data.get("post_type") == "__transport_error__":
            raise RuntimeError(f"QQ transport reader 异常：{data.get('error')}")
#打印事件，调试时候可以de注释一下
        logger.debug("收到 QQ 事件：%s", json.dumps(data, ensure_ascii=False))

        post_type = data.get('post_type')
        if post_type == 'message':
            return await self._build_unimessage_from_event(
                data,
                fetch_reply=True,
                keep_reply_segment=True,
            )

        if post_type != 'notice':# meta事件和request事件忽略不处理
            return UniMessage(platform=Platform.QQ, raw_event=data)
        
        if data.get('notice_type') == 'notify' and data.get('sub_type') == 'poke':
            #构造戳一戳上下文策略
            is_group = bool(data.get('group_id'))
            context = ChatContext(
                user=UserIdentity(
                    user_id=str(data.get('user_id') or ''),
                    user_name=self._extract_user_name(data)
                ),
                target=ConversationTarget(
                    channel_type=ChannelType.GROUP if is_group else ChannelType.PRIVATE,
                    conversation_id=str(data.get('group_id') or data.get('user_id') or ''),
                    platform=Platform.QQ,
                    group_name=data.get('group_name') if is_group else None
                ),
                message_id=str(data.get('message_id') or ''),
                request_uid=str(uuid.uuid4())
            )
            return UniMessage(
                platform=Platform.QQ,
                raw_event=data,
                context=context
            )

        logger.debug(
            "忽略未支持的 QQ notice 事件：notice_type=%s sub_type=%s",
            data.get("notice_type"),
            data.get("sub_type"),
        )
        return UniMessage(platform=Platform.QQ, raw_event=data)
    
    #发送纯文本
    async def send_text(self, context: ChatContext, text: str) -> None:
        if context.target.channel_type == ChannelType.GROUP:
            #发送群聊信息
            await self._send_raw(
                {
                    'action': 'send_group_msg',
                    'params': {
                        'group_id': int(context.target.conversation_id),
                        'message': text
                    }
                }
            )
        else:
            #发送私聊信息
            await self._send_raw(
                {
                    'action': 'send_private_msg', 
                    'params': {
                        'user_id': int(context.user.user_id), 
                        'message': text
                    }
                }
            )

    async def send_track(
        self,
        context: ChatContext,
        text: str,
        *,
        kind: str = "agent_action",
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        return


    def format_mention(self, context, user_id):
        if context.target.channel_type == ChannelType.GROUP:
            return f"[CQ:at,qq={user_id}] "
        return ""
    
    #给你贴表情
    async def send_reaction(self, context: ChatContext, emoji_id: int) -> None:
        await self._send_raw(
            {
                'action': 'set_msg_emoji_like',
                'params': {
                    'group_id': int(context.target.conversation_id),
                    'message_id': int(context.message_id), 
                    'emoji_id': emoji_id
                }
            }
        )

    #给你发帽子（头衔）
    async def set_special_title(self, context: ChatContext, title: str) -> None:
        await self._send_raw(
            {
                'action': 'set_group_special_title', 
                'params': {
                    'group_id': int(context.target.conversation_id), 
                    'user_id': int(context.user.user_id), 
                    'special_title': title, 
                    'duration': -1
                }
            }
        )

    #还复读？全员禁言！
    async def set_group_whole_ban(self, context: ChatContext, enable: bool) -> None:
        await self._send_raw(
            {
                'action': 'set_group_whole_ban', 
                'params': {
                    'group_id': int(context.target.conversation_id), 
                    'enable': enable
                }
            }
        )
    
    #戳戳你！！！
    async def group_poke(self, context: ChatContext, user_id: str) -> None:
        await self._send_raw(
            {
                'action': 'group_poke', 
                'params': {
                    'group_id': int(context.target.conversation_id), 
                    'user_id': int(user_id)
                }
            }
        )
    
    #拉去群聊成员
    async def get_group_members(self, context: ChatContext) -> List[Dict[str, Any]]:
        return (
            await self._call(
                'get_group_member_list', 
                {
                    'group_id': int(context.target.conversation_id)
                }
            )
        ).get('data', [])
    
    #拉取消息！
    async def fetch_message(self, message_id: str) -> Optional[Dict[str, Any]]:

        fetch=(
            await self._call(
                'get_msg', 
                {
                    'message_id': int(message_id)
                }
            )
        ).get('data')
        logger.debug("fetch_message 返回：%s", fetch)
        return fetch
    
    #拉取图片路径
    async def _fetch_image_path(self, file_name: str) -> Optional[str]:
        return (
            (
                await self._call(
                    'get_image', 
                    {'file': file_name}
                )
            ).get('data') or {}
        ).get('file')
    
    #不要关注这坨屎！只需要知道压缩图片
    def _compress_image_sync(self, input_path: str, max_dimension: int = 1024, quality: int = 85) -> str:
        with Image.open(input_path) as img:
            ratio = max_dimension / max(img.width, img.height)
            if ratio < 1:
                img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.Resampling.LANCZOS)
            fd, temp_path = tempfile.mkstemp(suffix='.jpg')
            os.close(fd)
            img.save(temp_path, 'PNG', quality=quality)
            return temp_path
    
    #下载图片
    async def download_image(self, file_name: str) -> Optional[str]:
        original_path = await self._fetch_image_path(file_name)
        if not original_path: return None
        try:
            if os.path.getsize(original_path) <= 256 * 1024: return original_path
        except OSError:
            return original_path
        return await asyncio.get_running_loop().run_in_executor(None, self._compress_image_sync, original_path)

    def _safe_workspace_upload_name(self, file_name: str) -> str:
        original = Path(file_name or "").name
        stem = Path(original).stem if original else "upload"
        suffix = Path(original).suffix
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
        if not stem:
            stem = "upload"
        if len(stem) > 80:
            stem = stem[:80]
        if len(suffix) > 16 or any(ch in suffix for ch in ("/", "\\")):
            suffix = ""
        return f"{stem}{suffix}"

    def _private_workspace_upload_target(self, user_id: str, file_name: str) -> tuple[str, Path]:
        upload_dir = self.settings.script_workspace_dir / str(user_id) / "upload"
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = self._safe_workspace_upload_name(file_name)
        target = upload_dir / safe_name
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            for index in range(1, 1000):
                candidate = upload_dir / f"{stem}_{index}{suffix}"
                if not candidate.exists():
                    target = candidate
                    break
            else:
                target = upload_dir / f"{uuid.uuid4().hex}{suffix}"
        return (Path("upload") / target.name).as_posix(), target

    async def _download_url_to_file(self, url: str, target: Path) -> int:
        total = 0
        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    with target.open("wb") as f:
                        async for chunk in response.aiter_bytes():
                            if not chunk:
                                continue
                            total += len(chunk)
                            if total > MAX_QQ_FILE_DOWNLOAD_BYTES:
                                raise ValueError("文件不能超过 25MB")
                            f.write(chunk)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return total

    async def _download_private_file_segments(
        self,
        context: ChatContext,
        segments: list[tuple[str, dict]],
    ) -> None:
        for seg_type, seg_data in segments:
            if seg_type != "file":
                continue
            file_id = str(seg_data.get("file_id") or "").strip()
            if not file_id:
                continue
            try:
                local_path = await self.download_file(
                    file_id=file_id,
                    context=context,
                    metadata=seg_data,
                )
            except Exception:
                logger.exception("下载 QQ 私聊文件失败：file_id=%s", file_id)
                continue
            if not local_path:
                continue
            target = self.settings.script_workspace_dir / str(context.user.user_id) / local_path
            seg_data["file"] = local_path
            seg_data["name"] = Path(local_path).name
            seg_data["path"] = str(target)
            try:
                seg_data["size"] = target.stat().st_size
            except OSError:
                pass

    async def download_file(
        self,
        file_id: str,
        context: ChatContext | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> Optional[str]:
        if context is None or context.target.channel_type != ChannelType.PRIVATE:
            return None

        file_id = str(file_id or "").strip()
        if not file_id:
            return None

        response = await self._call("get_private_file_url", {"file_id": file_id})
        url = ((response.get("data") or {}).get("url") or "").strip()
        if not url:
            logger.warning("获取 QQ 私聊文件下载链接失败：file_id=%s response=%s", file_id, response)
            return None

        meta = metadata or {}
        file_name = (
            str(meta.get("name") or "").strip()
            or str(meta.get("file") or "").strip()
            or Path(file_id).name
            or "upload"
        )
        rel_path, target = self._private_workspace_upload_target(context.user.user_id, file_name)
        size = await self._download_url_to_file(url, target)
        logger.info("已下载 QQ 私聊文件到工作区：%s，大小 %s bytes", rel_path, size)
        return rel_path

    async def upload_file(self,context,file):
        file_path = f"file://{os.path.abspath(file)}" if os.path.exists(file) else file

        if context.target.channel_type == ChannelType.PRIVATE:
            await self._send_raw(
                {
                    'action': 'upload_private_file',
                    'params': {
                        'user_id': int(context.user.user_id),
                        'file': file_path,
                    }
                }
            )
            return

        await self._send_raw(
            {
                'action': 'upload_group_file',
                'params': {
                    'group_id': int(context.target.conversation_id),
                    'file': file_path,
                }
            }
        )

    async def send_script_result(self, context: ChatContext, result: Dict[str, Any]) -> None:
        timeout = result.get("timeout")
        exit_code = "timeout" if timeout and timeout is not False else result.get("returncode")
        text = (
            f"脚本运行结果：{result.get('file_path') or '(unknown)'}\n"
            f"args: {result.get('args') or '(none)'}\n"
            f"exit_code: {exit_code}\n\n"
            f"[stdout]\n{result.get('stdout') or '(empty)'}\n\n"
            f"[stderr]\n{result.get('stderr') or '(empty)'}"
        )
        await self.send_text(context, text)
