from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# 表示聊天渠道类型
class ChannelType(str, Enum):
    GROUP = 'group'
    PRIVATE = 'private'
    WEB = 'web'

# 平台
class Platform(str, Enum):
    QQ = 'qq'
    WEB = 'web'
    DINGDING = 'dingding'
    FEISHU = 'feishu'
    WHATSAPP = 'whatsapp'

# 用户身份信息，用户是谁
@dataclass(slots=True)
class UserIdentity:
    user_id: str
    user_name: str | None = None

    def to_dict(self)->dict[str,Any]:
        return {
            'user_id':self.user_id,
            'user_name':self.user_name
        }

    @classmethod
    def from_dict(cls,data: dict[str, Any])->'UserIdentity':
        return cls(
            user_id=str(data.get('user_id')),
            user_name=str(data.get('user_name')),
        )

# 消息该发到那里
@dataclass(slots=True)
class ConversationTarget:
    channel_type: ChannelType
    conversation_id: str
    platform: Platform
    group_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'channel_type': self.channel_type.value,
            'conversation_id': self.conversation_id,
            'platform': self.platform.value,
            'group_name': self.group_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'ConversationTarget':
        return cls(
            channel_type=ChannelType(data['channel_type']),
            conversation_id=str(data['conversation_id']),
            platform=Platform(data['platform']),
            group_name=data.get('group_name'),
        )



# 一条消息的上下文信息
# 一条消息！
@dataclass(slots=True)
class ChatContext:
    user: UserIdentity# 谁发的
    target: ConversationTarget# 发给谁
    message_id: str | None = None# 消息id
    reply_to_message_id: str | None = None# 回复的消息id
    request_uid: str | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def thread_id(self) -> str:
        return f'{self.target.platform}:{self.target.channel_type}:{self.target.conversation_id}'
    #生成一个对话的唯一标识

    def to_dict(self)->dict[str,Any]:
        return {
            'user': self.user.to_dict(),
            'target': self.target.to_dict(),
            'message_id': self.message_id,
            'reply_to_message_id': self.reply_to_message_id,
            'request_uid': self.request_uid,
            'metadata': self.metadata or {},
        }

    @classmethod
    def from_dict(cls,data: dict[str,Any])->'ChatContext':
        return cls(
            user=UserIdentity.from_dict(data['user']),
            target=ConversationTarget.from_dict(data['target']),
            message_id=data.get('message_id'),
            reply_to_message_id=data.get('reply_to_message_id'),
            request_uid=data.get('request_uid'),
            metadata=data.get('metadata', {}) or {},
        )

