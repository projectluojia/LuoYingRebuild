from __future__ import annotations

from luoying_bot.ports.repos import UserPromptSettings, UserPromptSettingsRepo
from luoying_bot.system_prompt_parts import (
    BASIC_STYLE_ALIASES,
    BASIC_STYLE_RULES,
    EXTRA_TRAIT_ALIASES,
    EXTRA_TRAIT_RULES,
    LEVEL_ALIASES,
)


class UserPromptSettingsService:
    def __init__(self, repo: UserPromptSettingsRepo):
        self.repo = repo

    def get(self, user_id: str) -> UserPromptSettings:
        return self.repo.get(user_id) or UserPromptSettings(user_id=user_id)

    def set_basic_style(self, user_id: str, raw_style: str) -> str:
        style_key = self._normalize_basic_style(raw_style)
        settings = self.get(user_id)
        settings.basic_style = str(BASIC_STYLE_RULES[style_key]["name"])
        self.repo.save(settings)
        return f"已将基本风格与语调设置为：{settings.basic_style}"

    def set_extra_trait_level(self, user_id: str, raw_trait: str, raw_level: str) -> str:
        trait_key = self._normalize_extra_trait(raw_trait)
        level = self._normalize_level(raw_level)
        settings = self.get(user_id)
        trait_name = str(EXTRA_TRAIT_RULES[trait_key]["name"])
        settings.extra_trait_levels[trait_name] = level
        self.repo.save(settings)
        return f"已将额外特征「{trait_name}」设置为：{level}"

    def reset(self, user_id: str) -> str:
        deleted = self.repo.delete(user_id)
        return "已重置你的系统提示词偏好" if deleted else "你还没有设置过系统提示词偏好"

    def render(self, user_id: str) -> str:
        settings = self.get(user_id)
        lines = [
            "当前系统提示词偏好：",
            f"基本风格与语调：{settings.basic_style}",
            "额外特征：",
        ]
        for spec in EXTRA_TRAIT_RULES.values():
            name = str(spec["name"])
            level = settings.extra_trait_levels.get(name, "默认")
            lines.append(f"- {name}：{level}")
        return "\n".join(lines)

    def _normalize_basic_style(self, raw_style: str) -> str:
        key = BASIC_STYLE_ALIASES.get(raw_style.strip().lower()) or BASIC_STYLE_ALIASES.get(raw_style.strip())
        if key is None:
            raise ValueError(
                "未知基本风格。可选："
                + "、".join(str(spec["name"]) for spec in BASIC_STYLE_RULES.values())
            )
        return key

    def _normalize_extra_trait(self, raw_trait: str) -> str:
        key = EXTRA_TRAIT_ALIASES.get(raw_trait.strip().lower()) or EXTRA_TRAIT_ALIASES.get(raw_trait.strip())
        if key is None:
            raise ValueError(
                "未知额外特征。可选："
                + "、".join(str(spec["name"]) for spec in EXTRA_TRAIT_RULES.values())
            )
        return key

    def _normalize_level(self, raw_level: str) -> str:
        level = LEVEL_ALIASES.get(raw_level.strip().lower()) or LEVEL_ALIASES.get(raw_level.strip())
        if level is None:
            raise ValueError("未知强度。可选：增强、默认、减弱")
        return level
