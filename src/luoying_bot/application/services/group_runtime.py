from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List


#这是一个群聊Runtime数据类
@dataclass(slots=True)
class GroupRuntime:

    enabled_groups: Dict[str, bool] = field(default_factory=dict)
    banned_users: Dict[str, bool] = field(default_factory=dict)
    repeat_mode: Dict[str, bool] = field(default_factory=dict)
    member_cache: Dict[str, List[dict]] = field(default_factory=dict)
    
    #查询该群聊是否可用
    def is_group_enabled(self, group_id: str) -> bool:
        return self.enabled_groups.get(group_id,False)
    
    #设置该群聊可用
    def set_group_enabled(self, group_id: str, enabled: bool) -> None:
        self.enabled_groups[group_id] = enabled
    
    #是否这个用户ban了
    def is_user_banned(self, user_id: str) -> bool:
        return self.banned_users.get(user_id, False)
    
    #ban这个人
    def ban_user(self, user_id: str) -> None:
        self.banned_users[user_id] = True
    
    #unban这个人
    def unban_user(self, user_id: str) -> None:
        self.banned_users[user_id] = False
    
    #修改repeat services
    def toggle_repeat(self, group_id: str) -> bool:
        current = self.repeat_mode.get(group_id, False)
        self.repeat_mode[group_id] = not current
        return self.repeat_mode[group_id]
