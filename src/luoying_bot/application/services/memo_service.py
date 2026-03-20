from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from luoying_bot.ports.repos import MemoItem, MemoRepo


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class MemoActionResult:
    ok: bool
    text: str
    data: dict


class MemoService:
    def __init__(self, repo: MemoRepo):
        self.repo = repo

    def list_items(self, user_id: str) -> MemoActionResult:
        items = self.repo.list_items(user_id)
        if not items:
            return MemoActionResult(
                ok=True,
                text="当前还没有备忘录",
                data={"items": []},
            )

        lines = ["你的备忘录如下："]
        for idx, item in enumerate(items, start=1):
            tag_text = f" tags={item.tags}" if item.tags else ""
            lines.append(
                f"{idx}. [{item.id}] {item.content}{tag_text} "
                f"(创建:{item.created_at} 更新:{item.updated_at})"
            )

        return MemoActionResult(
            ok=True,
            text="\n".join(lines),
            data={
                "items": [
                    {
                        "index": i + 1,
                        "id": item.id,
                        "content": item.content,
                        "tags": item.tags,
                        "created_at": item.created_at,
                        "updated_at": item.updated_at,
                    }
                    for i, item in enumerate(items)
                ]
            },
        )

    def read_one(self, user_id: str, index: int | None = None, memo_id: str | None = None) -> MemoActionResult:
        items = self.repo.list_items(user_id)
        target = self._find_item(items, index=index, memo_id=memo_id)
        if target is None:
            return MemoActionResult(False, "没有找到对应备忘录", {})

        return MemoActionResult(
            ok=True,
            text=f"备忘录内容：{target.content}",
            data={
                "id": target.id,
                "content": target.content,
                "tags": target.tags,
                "created_at": target.created_at,
                "updated_at": target.updated_at,
            },
        )

    def add_item(self, user_id: str, content: str, tags: list[str] | None = None) -> MemoActionResult:
        content = (content or "").strip()
        if not content:
            return MemoActionResult(False, "备忘录内容不能为空", {})

        items = self.repo.list_items(user_id)
        memo_id = self._next_id(items)
        now = _now_str()

        item = MemoItem(
            id=memo_id,
            content=content,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        items.append(item)
        self.repo.save_items(user_id, items)

        return MemoActionResult(
            ok=True,
            text=f"已新增备忘录：{content}",
            data={
                "id": item.id,
                "content": item.content,
                "tags": item.tags,
            },
        )

    def overwrite_all(self, user_id: str, content: str) -> MemoActionResult:
        content = (content or "").strip()
        if not content:
            return MemoActionResult(False, "覆盖内容不能为空", {})

        now = _now_str()
        item = MemoItem(
            id="m_001",
            content=content,
            tags=[],
            created_at=now,
            updated_at=now,
        )
        self.repo.save_items(user_id, [item])

        return MemoActionResult(
            ok=True,
            text="已覆盖原有备忘录",
            data={"items": [{"id": item.id, "content": item.content}]},
        )

    def update_item(
        self,
        user_id: str,
        new_content: str,
        index: int | None = None,
        memo_id: str | None = None,
        tags: list[str] | None = None,
    ) -> MemoActionResult:
        new_content = (new_content or "").strip()
        if not new_content:
            return MemoActionResult(False, "新内容不能为空", {})

        items = self.repo.list_items(user_id)
        target = self._find_item(items, index=index, memo_id=memo_id)
        if target is None:
            return MemoActionResult(False, "没有找到要修改的备忘录", {})

        target.content = new_content
        if tags is not None:
            target.tags = tags
        target.updated_at = _now_str()

        self.repo.save_items(user_id, items)
        return MemoActionResult(
            ok=True,
            text=f"已修改备忘录：{target.content}",
            data={
                "id": target.id,
                "content": target.content,
                "tags": target.tags,
            },
        )

    def delete_item(self, user_id: str, index: int | None = None, memo_id: str | None = None) -> MemoActionResult:
        items = self.repo.list_items(user_id)
        target = self._find_item(items, index=index, memo_id=memo_id)
        if target is None:
            return MemoActionResult(False, "没有找到要删除的备忘录", {})

        items = [x for x in items if x.id != target.id]
        self.repo.save_items(user_id, items)

        return MemoActionResult(
            ok=True,
            text=f"已删除备忘录：{target.content}",
            data={"id": target.id},
        )

    def search_items(self, user_id: str, keyword: str) -> MemoActionResult:
        keyword = (keyword or "").strip()
        if not keyword:
            return MemoActionResult(False, "搜索关键词不能为空", {})

        items = self.repo.list_items(user_id)
        matched = [
            item for item in items
            if keyword in item.content or any(keyword in tag for tag in item.tags)
        ]

        if not matched:
            return MemoActionResult(
                ok=True,
                text=f"没有找到包含“{keyword}”的备忘录",
                data={"items": []},
            )

        lines = [f"找到 {len(matched)} 条相关备忘录："]
        for idx, item in enumerate(matched, start=1):
            lines.append(f"{idx}. [{item.id}] {item.content}")

        return MemoActionResult(
            ok=True,
            text="\n".join(lines),
            data={
                "items": [
                    {
                        "id": item.id,
                        "content": item.content,
                        "tags": item.tags,
                    }
                    for item in matched
                ]
            },
        )

    def clear_all(self, user_id: str) -> MemoActionResult:
        self.repo.save_items(user_id, [])
        return MemoActionResult(
            ok=True,
            text="已清空全部备忘录",
            data={},
        )

    def _find_item(
        self,
        items: list[MemoItem],
        index: int | None = None,
        memo_id: str | None = None,
    ) -> MemoItem | None:
        if memo_id:
            for item in items:
                if item.id == memo_id:
                    return item

        if index is not None:
            if 1 <= index <= len(items):
                return items[index - 1]

        return None

    def _next_id(self, items: list[MemoItem]) -> str:
        max_num = 0
        for item in items:
            if item.id.startswith("m_"):
                try:
                    num = int(item.id[2:])
                    max_num = max(max_num, num)
                except Exception:
                    pass
        return f"m_{max_num + 1:03d}"