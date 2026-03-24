from __future__ import annotations
import asyncio, json, os, re, tempfile, uuid
from typing import Any, Dict, List, Optional
import websockets
from PIL import Image
from luoying_bot.config import Settings
from luoying_bot.domain.context import ChannelType, ChatContext, ConversationTarget, Platform, UserIdentity
from luoying_bot.domain.message import UniMessage
from luoying_bot.ports.transport import ChatTransport

# QQ平台适配器

class QQWsTransport(ChatTransport):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.platfrom = Platform.QQ
        self.websocket = None
    
    #连接到WebSocket
    async def connect(self) -> None:
        self.websocket = await websockets.connect(self.settings.ws_url, additional_headers={"Authorization": f"Bearer {self.settings.ws_token}"})

    #发送一个东西，看不懂这个函数先往下看
    async def _send_raw(self, data: Dict[str, Any]) -> None:
        if not self.websocket:
            raise RuntimeError('QQ transport 尚未连接')
        await self.websocket.send(json.dumps(data, ensure_ascii=False))
    
    #拉取一个东西，看不懂往下看
    async def _call(self, action: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        echo_id = str(uuid.uuid4())
        await self._send_raw({'action': action, 'params': params or {}, 'echo': echo_id})
        while True:
            raw = await self.websocket.recv()
            data = json.loads(raw)
            if data.get('echo') == echo_id:
                return data
    
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
        raw = await self.websocket.recv()#收到消息
        data: Dict[str, Any] = json.loads(raw)#json成data

#打印事件，调试时候可以de注释一下
        print(json.dumps(data, indent=4, ensure_ascii=False))

        if data.get('post_type') not in {'message', 'notice'}:# meta事件和request事件忽略不处理
            return UniMessage(platform=Platform.QQ, raw_event=data)
        
        if data.get('post_type') == 'notice' and data.get('notice_type') == 'notify':
            #构造戳一戳上下文策略
            context = ChatContext(
                user=UserIdentity(
                    user_id=str(data.get('user_id') or ''),
                    user_name=self._extract_user_name(data)
                ),
                target=ConversationTarget(
                    channel_type=ChannelType.GROUP,
                    conversation_id=str(data.get('group_id') or data.get('user_id') or ''),
                    platform=Platform.QQ,
                    group_name=data.get('group_name')
                ),
                message_id=str(data.get('message_id') or ''),
                request_uid=str(uuid.uuid4())
            )
            return UniMessage(
                platform=Platform.QQ,
                raw_event=data,
                context=context
            )
        
        return await self._build_unimessage_from_event(
            data,
            fetch_reply=True,
            keep_reply_segment=True,
        )
        """
        else:
            #构造普通上下文策略
            context = ChatContext(
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
            )"""
        """
        #构造unimessage
        msg = UniMessage(
            platform=Platform.QQ,
            raw_event=data,
            context=context
        )
        raw_message = data.get('raw_message', '') or ''#由CQ码组成的原始信息
        message_field = data.get('message', raw_message)#经过LLbot格式化的message（如果开了array模式）
        for seg_type, seg_data in self._parse_segments(message_field, raw_message):
            msg.add_segment(seg_type, **seg_data)
        return msg"""
    
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
        return (
            await self._call(
                'get_msg', 
                {
                    'message_id': int(message_id)
                }
            )
        ).get('data')
    
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

    async def upload_file(self,context,file):
        await self._send_raw(
            {
                'action': 'upload_group_file', 
                'params': {
                    'group_id': int(context.target.conversation_id), 
                    'file': file
                }
            }
        )
