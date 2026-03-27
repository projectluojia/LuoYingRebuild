from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from luoying_bot.domain.context import ChatContext,Platform
from luoying_bot.domain.message import UniMessage

class TransportCapabilityError(RuntimeError):
    pass

class ChatTransport(ABC):
    
    platform=Platform.QQ

    #连接到。。。。
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self)->None:...



    #接收消息
    @abstractmethod
    async def recv_message(self) -> UniMessage: ...
    
    def format_mention(self,context:ChatContext,user_id:str)->str:
        return ""


    #发文本
    @abstractmethod
    async def send_text(self, context: ChatContext, text: str) -> None: ...

    async def send_reaction(self, context: ChatContext, emoji_id: int) -> None:
        raise TransportCapabilityError('当前 transport 不支持消息表情反应')
    async def set_special_title(self, context: ChatContext, title: str) -> None:
        raise TransportCapabilityError('当前 transport 不支持群头衔')
    async def set_group_whole_ban(self, context: ChatContext, enable: bool) -> None:
        raise TransportCapabilityError('当前 transport 不支持全员禁言')
    async def group_poke(self, context: ChatContext, user_id: str) -> None:
        raise TransportCapabilityError('当前 transport 不支持戳一戳')
    async def get_group_members(self, context: ChatContext) -> List[Dict[str, Any]]:
        raise TransportCapabilityError('当前 transport 不支持获取群成员')
    async def fetch_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        raise TransportCapabilityError('当前 transport 不支持获取消息详情')
    async def download_image(self, file_name: str) -> Optional[str]:
        raise TransportCapabilityError('当前 transport 不支持下载图片')
    async def upload_file(self,context: ChatContext, file: str):
        raise TransportCapabilityError('当前 transport 不支持上传文件')
