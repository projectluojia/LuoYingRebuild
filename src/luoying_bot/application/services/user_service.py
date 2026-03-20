from __future__ import annotations
from luoying_bot.ports.repos import UserProfile, UserRepo

#用户服务
class UserService:
    def __init__(self, repo: UserRepo):
        self.repo = repo#用户数据仓库
    
    #用户绑定
    def bind(self, user_id: str, department: str, college: str, year: str, name: str | None = None) -> str:
        if not year.isdigit(): 
            raise ValueError('--year 必须是数字')
        self.repo.create(
            UserProfile(
                user_id=user_id, 
                department=department, 
                college=college, 
                year=year, 
                name=name
            )
        )
        return '绑定信息成功！'
    
    #更新用户
    def update(self, user_id: str, *, department: str | None = None, college: str | None = None, year: str | None = None, name: str | None = None) -> str:
        if year is not None and not year.isdigit(): 
            raise ValueError('--year 必须是数字')
        if department is None and college is None and year is None and name is None: 
            return '没有需要更新的字段'
        self.repo.update_fields(
            user_id, 
            department=department, 
            college=college, 
            year=year, 
            name=name
        )
        return '更新用户信息成功！'
    
    #删除用户
    def delete(self, user_id: str) -> str:
        return f'已删除用户 {user_id} 的信息' if self.repo.delete(user_id) else '用户信息不存在，无法删除'
    
    #查询用户
    def query(self, user_id: str) -> str:
        profile = self.repo.get(user_id)
        if not profile: 
            return '未找到该用户资料'
        return f'用户 {user_id}：学部={profile.department}，学院={profile.college}，年级={profile.year}，姓名={profile.name or "未填写"}'
