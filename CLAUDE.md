# CLAUDE.md

本文件供 Claude 参考。通用 agent 规范见 [AGENTS.md](AGENTS.md)。协作规范以 [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md) 和 [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md) 为基准；如果本文与 `.github` 下文档冲突，以 `.github` 为准。

珞樱（LuoYing）是一个多入口 AI 助手机器人，支持 QQ OneBot、FastAPI Web API 和 CLI。

## 协作规范

- 所有协作内容必须使用中文，包括 Issue、PR 标题、PR 正文、提交信息和 review 讨论。
- 所有更新都应通过新建分支并提交 PR 的方式合入，禁止直接向 `main` 或其他长期维护分支提交业务改动。
- 分支名推荐使用 `feat/中文或英文简述`、`fix/中文或英文简述`、`docs/中文或英文简述`、`refactor/中文或英文简述`、`test/中文或英文简述`、`other/中文或英文简述`。
- 提交信息必须使用 `类型: 中文内容` 格式，类型限于 `feat`、`fix`、`docs`、`refactor`、`test`、`other`。
- PR 标题和正文必须使用中文，并按 `.github/PULL_REQUEST_TEMPLATE.md` 说明摘要、类型、改动内容、验证方式、影响范围、风险与关联事项。
- review 时重点检查分支来源、中文协作、提交格式、改动范围、验证方式，以及配置、依赖或部署影响。

## 项目结构

```
src/luoying_bot/          # Python 后端（主业务逻辑）
  main_web.py             # Web 入口
  main_cli_stream.py      # CLI 入口
  main_qq.py              # QQ OneBot 入口
  domain/                 # 核心领域模型
  application/            # 消息处理、命令、服务、Agent / Skill
  capabilities/           # 知识库等能力模块
  infra/
    http/
      api.py              # FastAPI 应用（路由注册入口）
      voice_api.py        # Voice router（prefix="/voice"）
    voice/                # VoicePort 实现（TTS/STT）
    transports/           # Web / CLI / QQ transport
docs/                     # 架构文档、API 参考、PRD
test/                     # pytest 测试
```

React + TypeScript + Vite 前端不放在本仓库内；请在同级独立仓库 `../LuoYing-Frontend/` 维护。

## 关键约定

### 前端边界

本仓库只维护后端 API、VoicePort、Web transport 和后端测试。Live2D、Vite 代理、浏览器语音交互、前端组件和前端构建配置都属于 `../LuoYing-Frontend/`。

### VoicePort 架构

后端 `VoicePort` 定义在 `src/luoying_bot/infra/voice/`。前端 API 客户端在 `../LuoYing-Frontend/src/` 下。Voice router 的 `prefix="/voice"` 已是完整路径，`include_router()` 时**不要**再加 `prefix="/api"`（前端开发代理会处理路径重写）。

### API 路由注册

`api.py` 中 `include_router()` 调用时：
- Voice router：无需额外 prefix（已有 `prefix="/voice"`）
- 其他 router：若需 prefix，确保与 Vite 代理 rewrite 规则一致（`/api` 前缀由代理 stripped）

后端代理端口：`8000`（**不是 `18000`**）。

## 常用命令

```bash
uv sync
uv run luoying-web
uv run luoying-cli
uv run luoying-qq
uv run pytest
uv run ruff check src scripts test
uv run pyright
```

## 修改原则

- 优先遵循现有架构边界和本地代码风格。
- 保持改动范围克制，避免无关重构。
- 修改共享能力、用户可见行为或跨入口逻辑时，补充或更新相关测试。
- 不要提交 `.env`、本地数据、缓存、虚拟环境或生成产物。
- 涉及配置、依赖、部署、端口或外部服务行为变化时，在 PR 中明确说明影响范围和风险。

## 深入文档

- [docs/web_frontend_api.md](docs/web_frontend_api.md) — Web API 完整参考
- [docs/kb_architecture_report.md](docs/kb_architecture_report.md) — 知识库架构
- [docs/knowledge_base_integration.md](docs/knowledge_base_integration.md) — KB 接入指南
