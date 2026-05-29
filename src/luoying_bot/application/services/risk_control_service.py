from __future__ import annotations

import copy

from typing import Union

from luoying_bot.config import settings
from luoying_bot.constants import risk_control
from luoying_bot.domain.message import UniMessage,MessageSegment

class RiskControlService:
    """
    请注意，该服务不具有引用语义！不具有引用语义！不具有引用语义！
    """
    def __init__(self):
        self.danger=[dg for dg in risk_control if dg.get("level")=="danger"]
        self.sensitive=[dg for dg in risk_control if dg.get("level")=="sensitive"]

    def _match_sen(self,text:str)->str:
        for sen in self.sensitive:
            text=text.replace(sen.get('content'),"")
        return text
    
    def _match_input_danger(self,text:str)->str:
        for dan in self.danger:
            if dan.get('content') in text:
                return "包含危险词汇，已被风控"
        return text
            
    def _match_output_danger(self,text:str)->str:
        for dan in self.danger:
            if dan.get('content') in text:
                return "你好，这个问题我暂时无法回答，让我们换个话题再聊聊吧。"
        return text
            
    def do_input_risk_control(self,text:str)->str:
        text=self._match_sen(text)
        text=self._match_input_danger(text)
        return text
    
    def do_output_risk_control(self,text:str)->str:
        text=self._match_sen(text)
        text=self._match_output_danger(text)
        return text

    #输入一个segment，输出风控后的segment
    def _process_segment_for_input(self,seg:MessageSegment)->MessageSegment:
        if seg.type!="text":
            return MessageSegment(type=seg.type,data=dict(seg.data))
        original_text = str(seg.data.get("text", ""))
        new_text = self.do_input_risk_control(original_text)
        return MessageSegment(type="text", data={**seg.data, "text": new_text})

    #基本复用上面那个的逻辑
    def _process_segment_for_output(self, seg: MessageSegment) -> MessageSegment:
        if seg.type != "text":
            return MessageSegment(type=seg.type, data=dict(seg.data))

        original_text = str(seg.data.get("text", ""))
        new_text = self.do_output_risk_control(original_text)
        return MessageSegment(type="text", data={**seg.data, "text": new_text})

    def _clone_message_base(self, msg: UniMessage) -> UniMessage:
        new_msg = UniMessage(
            uid=msg.uid,
            platform=msg.platform,
            raw_event=copy.deepcopy(msg.raw_event),
            context=copy.deepcopy(msg.context),
            segments=[],
            reply_message=None,
        )
        return new_msg

    def do_input_risk_control_message(self, msg: UniMessage) -> UniMessage:
        new_msg = self._clone_message_base(msg)

        new_msg.segments=[
            self._process_segment_for_input(seg)
            for seg in msg.segments
        ]

        if msg.reply_message is not None:
            new_msg.reply_message = self.do_input_risk_control_message(msg.reply_message)

        return new_msg
    
    def do_output_risk_control_message(self, msg: UniMessage) -> UniMessage:
        new_msg = self._clone_message_base(msg)

        new_msg.segments=[
            self._process_segment_for_output(seg)
            for seg in msg.segments
        ]

        if msg.reply_message is not None:
            new_msg.reply_message = self.do_output_risk_control_message(msg.reply_message)

        return new_msg

    def do_input_risk_control_any(self, content: str | UniMessage)->str | UniMessage:
        if isinstance(content,UniMessage):
            return self.do_input_risk_control_message(content)
        return self.do_input_risk_control(content)

    def do_output_risk_control_any(self, content: str | UniMessage)->str | UniMessage:
        if isinstance(content,UniMessage):
            return self.do_output_risk_control_message(content)
        return self.do_output_risk_control(content)

