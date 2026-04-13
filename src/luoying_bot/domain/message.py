from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid
from .context import ChannelType, ChatContext, ConversationTarget, Platform, UserIdentity

#程序内部统一消息


#单一消息子段
@dataclass(slots=True)
class MessageSegment:
    type: str
    data: Dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class UniMessage:
    uid: str = field(default_factory=lambda: str(uuid.uuid4()))# 这条消息自己唯一的id
    platform: Platform = Platform.QQ  #平台
    raw_event: Dict[str, Any] = field(default_factory=dict) # 原始事件
    context: Optional[ChatContext] = None # 该条消息上下文策略
    segments: List[MessageSegment] = field(default_factory=list)
    reply_message: Optional['UniMessage']=None

    # 向该消息添加一个段
    def add_segment(self, seg_type: str, **data: Any) -> None:
        self.segments.append(MessageSegment(type=seg_type, data=data))
    
    # 获取纯文本
    def get_plain_text(self) -> str:
        return ''.join(str(seg.data.get('text', '')) for seg in self.segments if seg.type == 'text').strip()

    def has_at(self,user_id:str)->bool:
        user_id = str(user_id)
        return any(seg.type == 'at' and str(seg.data.get('user_id','')) == user_id for seg in self.segments)

    def get_images(self) -> list[str]:
        return [str(seg.data.get('file', '')) for seg in self.segments if seg.type == 'image']
    
    def get_files(self) -> list[dict[str, Any]]:
        return [dict(seg.data) for seg in self.segments if seg.type == 'file']

    # 将消息转换成更适合大模型理解的文本
    def _segment_to_llm_text(self,include_reply_segment:bool=True) -> str:
        parts: List[str] = []
        for seg in self.segments:
            if seg.type == 'text':
                parts.append(str(seg.data.get('text', '')))
            elif seg.type == 'at':
                parts.append(f"[艾特:{seg.data.get('user_id')}]")
            elif seg.type == 'reply':
                if include_reply_segment:
                    parts.append(f"[回复消息:{seg.data.get('message_id')}]")
            elif seg.type == 'face':
                parts.append(f"[QQ表情:{seg.data.get('face_id')}]")
            elif seg.type == 'image':
                parts.append(f"[图片:{seg.data.get('file')}]")
            elif seg.type == 'file':
                name = seg.data.get('name') or seg.data.get('file') or seg.data.get('file_id') or 'unknown'
                size = seg.data.get('size') or seg.data.get('file_size')
                if size:
                    parts.append(f"[文件:{name}, 大小={size}]")
                else:
                    parts.append(f"[文件:{name}]")
            else:
                parts.append(f"[{seg.type}:{seg.data}]")
        return ' '.join(p for p in parts if p).strip()
    
    def to_llm_text(self)->str:
        current_text=self._segment_to_llm_text(include_reply_segment=False)

        if not self.reply_message:
            return current_text
        
        reply_sender_id=""
        reply_sender_name=""

        if self.reply_message.context and self.reply_message.context.user:
            reply_sender_id=str(self.reply_message.context.user.user_id or "")
            reply_sender_name=str(self.reply_message.context.user.user_name or "")
            
        reply_text = self.reply_message._segment_to_llm_text(include_reply_segment=False)

        if reply_text:    
            return (
                f"[用户当前消息]\n{current_text}\n\n"
                f"[用户回复的那条消息]\n"
                f"发送者ID：{reply_sender_id}\n"
                f"发送者昵称：{reply_sender_name}\n"
                f"消息内容：\n{reply_text}"
            ).strip()

        return current_text

    # 网页端纯文本请求包装
    @classmethod
    def from_web_text(cls, session_id: str, user_id: str, user_name: str, text: str) -> 'UniMessage':
        context = ChatContext(
            user=UserIdentity(user_id=user_id, user_name=user_name),
            target=ConversationTarget(channel_type=ChannelType.WEB, conversation_id=session_id, platform=Platform.WEB),
        )
        msg = cls(platform=Platform.WEB, context=context)
        msg.add_segment('text', text=text)
        return msg
