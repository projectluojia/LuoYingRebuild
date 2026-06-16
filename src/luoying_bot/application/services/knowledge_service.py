from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from luoying_bot.ports.repos import KnowledgeItem, KnowledgeRepo

if TYPE_CHECKING:
    from luoying_bot.ports.llm import ChatModel

logger = logging.getLogger(__name__)


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class KnowledgeActionResult:
    ok: bool
    text: str
    data: dict


class KnowledgeService:
    def __init__(self, repo: KnowledgeRepo, model: "ChatModel | None" = None):
        self.repo = repo
        self.model = model

    def list_items(self) -> KnowledgeActionResult:
        items = self.repo.list_items()
        if not items:
            return KnowledgeActionResult(
                ok=True,
                text="知识库暂无内容",
                data={"items": []},
            )

        lines = ["知识库内容如下："]
        for idx, item in enumerate(items, start=1):
            tag_text = f" [{', '.join(item.tags)}]" if item.tags else ""
            source_text = f" 来源:{item.source}" if item.source else ""
            lines.append(
                f"{idx}. [{item.id}] {item.title}{tag_text}{source_text}"
                f" (创建:{item.created_at} 更新:{item.updated_at})"
            )

        return KnowledgeActionResult(
            ok=True,
            text="\n".join(lines),
            data={
                "items": [
                    {
                        "index": i + 1,
                        "id": item.id,
                        "title": item.title,
                        "content": item.content,
                        "tags": item.tags,
                        "source": item.source,
                        "created_at": item.created_at,
                        "updated_at": item.updated_at,
                    }
                    for i, item in enumerate(items)
                ]
            },
        )

    def read_one(self, index: int | None = None, item_id: str | None = None) -> KnowledgeActionResult:
        items = self.repo.list_items()
        target = self._find_item(items, index=index, item_id=item_id)
        if target is None:
            return KnowledgeActionResult(False, "没有找到对应的知识库条目", {})

        tag_text = f"标签：{', '.join(target.tags)}" if target.tags else "标签：无"
        source_text = f"来源：{target.source}" if target.source else "来源：无"

        return KnowledgeActionResult(
            ok=True,
            text=(
                f"标题：{target.title}\n"
                f"内容：{target.content}\n"
                f"{tag_text}\n"
                f"{source_text}\n"
                f"创建时间：{target.created_at}\n"
                f"更新时间：{target.updated_at}"
            ),
            data={
                "id": target.id,
                "title": target.title,
                "content": target.content,
                "tags": target.tags,
                "source": target.source,
                "created_at": target.created_at,
                "updated_at": target.updated_at,
            },
        )

    def add_item(
        self,
        title: str,
        content: str,
        tags: list[str] | None = None,
        source: str = "",
    ) -> KnowledgeActionResult:
        title = (title or "").strip()
        content = (content or "").strip()
        if not title:
            return KnowledgeActionResult(False, "知识库条目标题不能为空", {})
        if not content:
            return KnowledgeActionResult(False, "知识库条目内容不能为空", {})

        items = self.repo.list_items()
        item_id = self._next_id(items)
        now = _now_str()

        item = KnowledgeItem(
            id=item_id,
            title=title,
            content=content,
            tags=tags or [],
            source=source.strip(),
            created_at=now,
            updated_at=now,
        )
        items.append(item)
        self.repo.save_items(items)

        tag_text = f"，标签：{', '.join(item.tags)}" if item.tags else ""
        return KnowledgeActionResult(
            ok=True,
            text=f"已添加知识库条目：{item.title}{tag_text}",
            data={
                "id": item.id,
                "title": item.title,
                "tags": item.tags,
            },
        )

    def update_item(
        self,
        index: int | None = None,
        item_id: str | None = None,
        new_title: str | None = None,
        new_content: str | None = None,
        new_tags: list[str] | None = None,
        new_source: str | None = None,
    ) -> KnowledgeActionResult:
        items = self.repo.list_items()
        target = self._find_item(items, index=index, item_id=item_id)
        if target is None:
            return KnowledgeActionResult(False, "没有找到要修改的知识库条目", {})

        if new_title is not None:
            t = new_title.strip()
            if not t:
                return KnowledgeActionResult(False, "标题不能为空", {})
            target.title = t
        if new_content is not None:
            c = new_content.strip()
            if not c:
                return KnowledgeActionResult(False, "内容不能为空", {})
            target.content = c
        if new_tags is not None:
            target.tags = new_tags
        if new_source is not None:
            target.source = new_source.strip()

        target.updated_at = _now_str()
        self.repo.save_items(items)

        return KnowledgeActionResult(
            ok=True,
            text=f"已修改知识库条目：{target.title}",
            data={
                "id": target.id,
                "title": target.title,
                "tags": target.tags,
            },
        )

    def delete_item(self, index: int | None = None, item_id: str | None = None) -> KnowledgeActionResult:
        items = self.repo.list_items()
        target = self._find_item(items, index=index, item_id=item_id)
        if target is None:
            return KnowledgeActionResult(False, "没有找到要删除的知识库条目", {})

        items = [x for x in items if x.id != target.id]
        self.repo.save_items(items)

        return KnowledgeActionResult(
            ok=True,
            text=f"已删除知识库条目：{target.title}",
            data={"id": target.id},
        )

    def search_items(self, keyword: str) -> KnowledgeActionResult:
        keyword = (keyword or "").strip()
        if not keyword:
            return KnowledgeActionResult(False, "搜索关键词不能为空", {})

        items = self.repo.list_items()
        matched = [
            item for item in items
            if keyword in item.title
            or keyword in item.content
            or any(keyword in tag for tag in item.tags)
        ]

        if not matched:
            return KnowledgeActionResult(
                ok=True,
                text=f"没有找到包含「{keyword}」的知识库条目",
                data={"items": []},
            )

        lines = [f"找到 {len(matched)} 条相关知识库条目："]
        for idx, item in enumerate(matched, start=1):
            tag_text = f" [{', '.join(item.tags)}]" if item.tags else ""
            lines.append(f"{idx}. [{item.id}] {item.title}{tag_text}")
            # 截取内容前 100 字符作为预览
            preview = item.content[:100] + "…" if len(item.content) > 100 else item.content
            lines.append(f"   {preview}")

        return KnowledgeActionResult(
            ok=True,
            text="\n".join(lines),
            data={
                "items": [
                    {
                        "id": item.id,
                        "title": item.title,
                        "content": item.content,
                        "tags": item.tags,
                    }
                    for item in matched
                ]
            },
        )

    async def generate_summary(self) -> KnowledgeActionResult:
        items = self.repo.list_items()
        if not items:
            return KnowledgeActionResult(
                ok=True,
                text="知识库暂无内容，无法生成摘要",
                data={},
            )

        if self.model is None:
            return KnowledgeActionResult(
                False,
                "摘要服务不可用：未配置语言模型",
                {},
            )

        # 拼接所有条目
        parts = []
        for i, item in enumerate(items, start=1):
            tag_text = f"（标签：{', '.join(item.tags)}）" if item.tags else ""
            parts.append(f"{i}. {item.title}{tag_text}\n{item.content}")
        all_text = "\n\n".join(parts)

        # 截断保护，避免超出 token 限制
        max_chars = 12000
        if len(all_text) > max_chars:
            all_text = all_text[:max_chars] + "\n\n（内容过长，已截断）"

        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个知识库摘要助手。请对以下知识库内容生成一份简洁、有条理的中文摘要。"
                    "摘要应涵盖所有条目的核心要点，使用分点或分段的方式组织，便于快速了解知识库全貌。"
                    "不要遗漏重要信息，也不要添加知识库中不存在的内容。"
                ),
            },
            {
                "role": "user",
                "content": f"以下是知识库的全部内容（共 {len(items)} 条）：\n\n{all_text}",
            },
        ]

        try:
            summary_text = await self.model.chat(messages)
            return KnowledgeActionResult(
                ok=True,
                text=f"📚 知识库摘要（共 {len(items)} 条）：\n\n{summary_text.strip()}",
                data={"summary": summary_text.strip(), "item_count": len(items)},
            )
        except Exception as e:
            logger.exception("生成知识库摘要失败")
            return KnowledgeActionResult(
                False,
                f"生成摘要失败：{type(e).__name__}: {e}",
                {},
            )

    def clear_all(self) -> KnowledgeActionResult:
        self.repo.save_items([])
        return KnowledgeActionResult(
            ok=True,
            text="已清空全部知识库内容",
            data={},
        )

    def _find_item(
        self,
        items: list[KnowledgeItem],
        index: int | None = None,
        item_id: str | None = None,
    ) -> KnowledgeItem | None:
        if item_id:
            for item in items:
                if item.id == item_id:
                    return item

        if index is not None:
            if 1 <= index <= len(items):
                return items[index - 1]

        return None

    def _next_id(self, items: list[KnowledgeItem]) -> str:
        max_num = 0
        for item in items:
            if item.id.startswith("kb_"):
                try:
                    num = int(item.id[3:])
                    max_num = max(max_num, num)
                except Exception:
                    pass
        return f"kb_{max_num + 1:03d}"
