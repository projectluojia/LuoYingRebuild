from __future__ import annotations
from datetime import datetime
from typing import Optional
import httpx
import asyncio
import logging
import hashlib
import re
from luoying_bot.application.agent.skill_base import BaseSkill, SkillRequest, SkillResult
from luoying_bot.config import settings
from luoying_bot.constants import FORTUNE_DO,FORTUNE_LEVELS
from luoying_bot.domain.context import Platform

logger = logging.getLogger(__name__)

#测试通过
class ReminderSkill(BaseSkill):
    name = 'reminder'
    platform = [Platform.QQ, Platform.WEB]
    description = (
        '创建、查看、删除提醒事项。'
        '你不能假装知道时间！你不知道目前的时间！'
        '在使用之前，必须先调用TimeSkill来查看当前时间！'
        'payload 里可带 action=create/list/delete run_time=YYYY-MM-DD HH:MM （这是格式：年-月-日 时:分，请填入数字，禁止任何额外内容） content=（提醒的内容） repeat=True/False （是否每日重复）indexes=[（一个列表，是要删除的编号，编号不是从0而是从1开始！）]'
    )

    def _parse_run_time(self,value: str) -> datetime:
        text = str(value).strip()
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M',
        ]
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                pass
        raise ValueError(
            f"无法识别的时间格式：{value}。请使用 YYYY-MM-DD HH:MM 或 YYYY-MM-DD HH:MM:SS"
        )
    
    def _to_bool(self,value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {'true', '1', 'yes', 'y'}
        return bool(value)

    async def run(self, req: SkillRequest) -> SkillResult:
        action = req.payload.get('action', 'list') 
        svc = self.services.reminder_service
        if action == 'list': 
            return SkillResult(text=svc.list_for_user(req.context))
        if action == 'delete': 
            return SkillResult(text=svc.delete_by_indexes(req.context, req.payload.get('indexes', [])))
        if action == 'create':
            run_time=self._parse_run_time(req.payload['run_time'])
            repeat = self._to_bool(req.payload.get('repeat', False))
            return SkillResult(
                text=await svc.create(
                    req.context, 
                    run_time,
                    req.payload['content'], 
                    repeat,
                )
            )
        return SkillResult(text='暂不支持这个提醒动作')
#测试通过
class WeatherSkill(BaseSkill):
    name = 'weather'
    platform = [Platform.QQ, Platform.WEB]
    description = '查询武汉天气。'
    async def run(self, req: SkillRequest) -> SkillResult:
        if not settings.qweather_api_key: 
            return SkillResult(text='天气服务未配置 API Key')
        
        url = settings.weather_base_url
        params = {
            "location": "101200101",
            "lang": "zh",
            "unit": "m",
            "key": settings.qweather_api_key,
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            now = data["now"]
            return SkillResult(text=f"天气：{now['text']}，温度 {now['temp']}°C，体感 {now['feelsLike']}°C，湿度 {now['humidity']}%")
        

#测试通过
class WebSearchSkill(BaseSkill):
    name = 'web_search'
    platform = [Platform.QQ, Platform.WEB]
    description = '联网搜索信息。payload 需要 query 查询内容，k 返回条数，最多 5 '

    def _tavily_search_sync(self, query: str, k: int = 5) -> Optional[str]:
        try:
            from tavily import TavilyClient
            api_key = settings.tavily_api_key

            if not api_key:
                print("Tavily 搜索失败")
                return None

            client = TavilyClient(api_key=api_key)
            resp = client.search(
                query=query,
                max_results=max(1, min(k, 5)),
                include_answer=True,
                include_raw_content=False,
                include_images=False,
            )

            answer = resp.get("answer") or ""
            results = resp.get("results") or []
            lines = []

            if answer:
                lines.append(f"【摘要】{answer}")
            lines.append("【结果】")

            for i, r in enumerate(results[:k], 1):
                title = (r.get("title") or "").strip()
                url = (r.get("url") or "").strip()
                content = (r.get("content") or "").strip().replace("\n", " ").strip()
                if len(content) > 160:
                    content = content[:160] + "…"
                lines.append(f"{i}. {title}\n{url}\n{content}")

            print("Tavily 搜索成功")
            return "\n".join(lines).strip()
        except Exception:
            print("Tavily 搜索失败")
            return None

    async def _tavily_search(self, query: str, k: int = 5) -> Optional[str]:
        return await asyncio.to_thread(self._tavily_search_sync, query, k)
    
    async def _ddg_search(self, query: str, k: int = 5) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        url = "https://duckduckgo.com/html/"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, data={"q": query}, headers=headers)
            resp.raise_for_status()
            html = resp.text

        results = []
        blocks = re.findall(
            r'<a rel="nofollow" class="result__a" href="([^"]+)".*?>(.*?)</a>.*?<a class="result__snippet".*?>(.*?)</a>',
            html,
            flags=re.S,
        )
        for link, title, snippet in blocks:
            title = re.sub(r"<.*?>", "", title).strip()
            snippet = re.sub(r"<.*?>", "", snippet).strip()
            snippet = re.sub(r"\s+", " ", snippet)
            results.append((title, link, snippet))
            if len(results) >= k:
                break

        if not results:
            print("DDG 搜索失败")
            return "未搜索到结果（DDG 兜底可能被限制/结构变更）。"

        lines = ["【结果】"]
        for i, (title, link, snippet) in enumerate(results, 1):
            if len(snippet) > 160:
                snippet = snippet[:160] + "…"
            lines.append(f"{i}. {title}\n{link}\n{snippet}")

        print("DDG 搜索成功")
        return "\n".join(lines)
    
    async def run(self, req: SkillRequest) -> SkillResult:
        query = req.payload.get('query') or req.message.get_plain_text()
        k = req.payload.get('k') or 5

        if not query:
            return SkillResult(text='query 不能为空')

        k = max(1, min(int(k or 5), 10))

        try:
            tavily_out = await self._tavily_search(query=query, k=k)
            if tavily_out:
                print("Tavily called")
                return SkillResult(text=tavily_out)
        except Exception as e:
            print(str(e))

        try:
            print("ddg called")
            return SkillResult(text=await self._ddg_search(query=query, k=k))
        except Exception as e:
            return SkillResult(text=f'联网搜索失败：{e}')


#测试通过
class MemoSkill(BaseSkill):
    name = "memo"
    platform = [Platform.QQ, Platform.WEB]
    description = (
        "读写用户备忘录。"
        "支持 action=list/read/add/update/delete/search/clear/overwrite。"
        "永远不要猜测用户的意图"
        "执行修改或删除时，如果存在多条相似备忘录，一定要询问用户是哪一条，不能自己猜测执行。"
        "常见 payload："
        '{"action":"list"} '
        '{"action":"add","content":"周四交作业","tags":["学习"]} '
        '{"action":"read","index":1} '
        '{"action":"update","index":1,"content":"周五交作业"} '
        '{"action":"delete","index":1} '
        '{"action":"search","keyword":"作业"} '
        '{"action":"clear"}'
    )

    async def run(self, req: SkillRequest) -> SkillResult:
        self.memo_service = self.services.memo_service
        user_id = str(req.context.user.user_id)
        action = (req.payload.get("action") or "list").strip().lower()

        try:
            if action == "list":
                print("LIST Called")
                result = self.memo_service.list_items(user_id)

            elif action == "read":
                print("READ Called")
                result = self.memo_service.read_one(
                    user_id=user_id,
                    index=self._to_int(req.payload.get("index")),
                    memo_id=req.payload.get("id"),
                )

            elif action == "add":
                print("ADD Called")
                result = self.memo_service.add_item(
                    user_id=user_id,
                    content=req.payload.get("content", ""),
                    tags=self._to_tags(req.payload.get("tags")),
                )

            elif action == "overwrite":
                result = self.memo_service.overwrite_all(
                    user_id=user_id,
                    content=req.payload.get("content", ""),
                )

            elif action == "update":
                print("UPDATE Called")
                result = self.memo_service.update_item(
                    user_id=user_id,
                    index=self._to_int(req.payload.get("index")),
                    memo_id=req.payload.get("id"),
                    new_content=req.payload.get("content", ""),
                    tags=self._to_tags(req.payload.get("tags"), allow_none=True),
                )

            elif action == "delete":
                print("DELETE Called")
                result = self.memo_service.delete_item(
                    user_id=user_id,
                    index=self._to_int(req.payload.get("index")),
                    memo_id=req.payload.get("id"),
                )

            elif action == "search":
                print("SEARCH Called")
                result = self.memo_service.search_items(
                    user_id=user_id,
                    keyword=req.payload.get("keyword", ""),
                )

            elif action == "clear":
                print("CLEAR Called")
                result = self.memo_service.clear_all(user_id)

            else:
                return SkillResult(
                    text=f"不支持的 memo action：{action}",
                    data={"ok": False, "action": action},
                )

            return SkillResult(
                text=result.text,
                data={
                    "ok": result.ok,
                    "action": action,
                    **result.data,
                },
            )

        except Exception as e:
            return SkillResult(
                text=f"备忘录操作失败：{type(e).__name__}: {e}",
                data={"ok": False, "action": action},
            )

    def _to_int(self, value):
        if value is None or value == "":
            return None
        try:
            return int(value)
        except Exception:
            return None

    def _to_tags(self, value, allow_none: bool = False):
        if value is None:
            return None if allow_none else []
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            return [x.strip() for x in text.split(",") if x.strip()]
        return []
#测试通过
class TimeSkill(BaseSkill):
    name = "time"
    platform = [Platform.QQ, Platform.WEB]
    description = "查询当前时间"
    async def run(self, req: SkillRequest) -> SkillResult:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday_str = weekdays[today.weekday()] 
        return SkillResult(text=f"当前时间是 {now} {weekday_str}")   
#测试通过
class FortuneSkill(BaseSkill):
    name = "fortune"
    platform = [Platform.QQ, Platform.WEB]
    description = "获取运势 payload 无需提供内容"
    async def run(self,req: SkillRequest) -> SkillResult:
        user_id = str(req.context.user.user_id)

        today = datetime.now().strftime("%Y-%m-%d")
        h = int(hashlib.md5(f"{user_id}_{today}".encode()).hexdigest(), 16)
        weights = {
            "大凶": 8,
            "下下": 10,
            "末凶": 10,
            "下凶": 10,
            "小凶": 10,
            "中平": 10,
            "小吉": 10,
            "下吉": 10,
            "中吉": 10,
            "上吉": 10,
            "大吉": 8,
        }
        s = sum(weights.values())
        r = (h % 10000) / 10000 * s
        acc = 0
        print(f"运势工具Call，原哈希码：{h} ，映射哈希码：{r}")
        for lv in FORTUNE_LEVELS:
            acc += weights[lv]
            if r <= acc:
                fortune_level = lv
                break

        if fortune_level == "大吉":
            return SkillResult(text="今日运势：大吉\n宜：诸事皆宜\n忌：无")
        if fortune_level == "大凶":
            return SkillResult(text="今日运势：大凶\n宜：无\n忌：诸事不宜")

        keys = sorted(FORTUNE_DO.keys())
        n = len(keys)

        def pick2(seed, banned=set()):
            out, used = [], set()
            for t in range(n * 2):
                k = keys[(seed + t * 7) % n]
                title = FORTUNE_DO[k]["title"]
                if title in banned or title in used:
                    continue
                out.append(k); used.add(title)
                if len(out) == 2:
                    break
            return out, used

        do_idx, do_titles = pick2(h >> 8)
        not_idx, _ = pick2(h >> 24, do_titles)

        do = [f"{FORTUNE_DO[i]['title']}：{FORTUNE_DO[i]['do']}" for i in do_idx]
        not_do = [f"{FORTUNE_DO[i]['title']}：{FORTUNE_DO[i]['not_do']}" for i in not_idx]

        return SkillResult(text=f"今日运势：{fortune_level}\n宜：{'；'.join(do)}\n忌：{'；'.join(not_do)}")
#测试通过
class ArxivSkill(BaseSkill):
    name = 'arxiv'
    platform = [Platform.QQ, Platform.WEB]
    description = (
        '查询arxiv论文'
        '你可以选择性返回信息，但是必须告诉用户原文链接！！！！'
        'payload 应包含 query = 【查询关键词，最好英语】 max_results=【查询篇数，最多5】'
    )
    async def run(self,req: SkillRequest) -> SkillResult:
        import arxiv
        query=req.payload.get('query') or 'AI' 
        max_results=req.payload.get('max_results') or 5 
        max_results = max(1, min(int(max_results or 5), 10))
        print(f"论文推荐工具 调用 query：{query} 最大数量：{max_results}")
        try:
            client = arxiv.Client()
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate
            )
            results = client.results(search)
        except Exception as e:
            print(f"论文推荐工具 结束，出错：{e}")
            return f"Arxiv出错：{e}"
        print("论文推荐工具 拉取论文成功")
        rt_list=[]

        for r in results:
            rt_list.append(f"第一篇论文：{r.title}，论文地址：{r.links}，论文summary：{r.summary}")

        print("论文推荐工具 结束")
        return "\n".join(rt_list)