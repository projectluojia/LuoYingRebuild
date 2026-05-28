from __future__ import annotations

from luoying_bot.application.commands.base import BaseCommand
from luoying_bot.domain.context import ChatContext
from luoying_bot.domain.result import Reply


class PromptCommand(BaseCommand):
    name = "/prompt"
    aliases = ["/prompt_settings"]

    async def validate(self, args: dict[str, str]) -> dict[str, str]:
        return args

    async def execute(self, context: ChatContext, args: dict[str, str]) -> Reply:
        return Reply(text=self.services.user_prompt_settings_service.render(context.user.user_id))


class PromptStyleCommand(BaseCommand):
    name = "/prompt_style"
    aliases = ["/set_prompt_style"]
    args_required = True
    required_args = {"--style": ["-s"]}

    async def validate(self, args: dict[str, str]) -> dict[str, str]:
        return args

    async def execute(self, context: ChatContext, args: dict[str, str]) -> Reply:
        text = self.services.user_prompt_settings_service.set_basic_style(
            context.user.user_id,
            args["--style"],
        )
        return Reply(text=text)


class PromptTraitCommand(BaseCommand):
    name = "/prompt_trait"
    aliases = ["/set_prompt_trait"]
    args_required = True
    required_args = {
        "--trait": ["-t"],
        "--level": ["-l"],
    }

    async def validate(self, args: dict[str, str]) -> dict[str, str]:
        return args

    async def execute(self, context: ChatContext, args: dict[str, str]) -> Reply:
        text = self.services.user_prompt_settings_service.set_extra_trait_level(
            context.user.user_id,
            args["--trait"],
            args["--level"],
        )
        return Reply(text=text)


class PromptResetCommand(BaseCommand):
    name = "/prompt_reset"
    aliases = ["/reset_prompt"]

    async def validate(self, args: dict[str, str]) -> dict[str, str]:
        return args

    async def execute(self, context: ChatContext, args: dict[str, str]) -> Reply:
        return Reply(text=self.services.user_prompt_settings_service.reset(context.user.user_id))


class PromptHelpCommand(BaseCommand):
    name = "/prompt_help"

    async def validate(self, args: dict[str, str]) -> dict[str, str]:
        return args

    async def execute(self, context: ChatContext, args: dict[str, str]) -> Reply:
        return Reply(
            text=(
                "系统提示词偏好指令：\n"
                "/prompt 查看当前设置\n"
                "/prompt_style --style 专业可靠\n"
                "/prompt_trait --trait 表情符号 --level 减弱\n"
                "/prompt_reset 重置设置\n"
                "基本风格可选：默认、专业可靠、亲和友善、直言不讳、天马行空、高效务实、吐槽达人\n"
                "额外特征可选：温和体贴、热情洋溢、表情符号、标题和列表\n"
                "强度可选：增强、默认、减弱"
            )
        )
