# AGENTS.md

本文件适用于整个仓库，供 Codex、Claude 和其他自动化 agent 参考。协作规范以 [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md) 和 [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md) 为基准；如果本文件与 `.github` 下文档冲突，以 `.github` 为准。

## 协作语言

本仓库的所有协作内容必须使用中文，包括 Issue、PR 标题、PR 正文、提交信息和 review 讨论。agent 的说明、总结、提交信息建议和 PR 描述也应使用中文。

## 工作流程

所有更新都应通过新建分支并提交 PR 的方式合入：

1. 从最新目标分支拉取代码。
2. 新建语义清晰的工作分支。
3. 在工作分支完成修改并提交。
4. 推送工作分支到远端。
5. 新建 PR，并按模板填写中文说明。
6. 通过 review 后再合入目标分支。

禁止直接向 `main` 或其他长期维护分支提交业务改动。

## 分支与提交

分支名应简短说明改动目的，推荐格式：

```text
feat/中文或英文简述
fix/中文或英文简述
docs/中文或英文简述
refactor/中文或英文简述
test/中文或英文简述
other/中文或英文简述
```

提交信息必须使用以下格式：

```text
类型: 中文内容
```

允许的类型：

- `feat`：新增功能
- `fix`：修复问题
- `docs`：文档更新
- `refactor`：重构代码，不改变外部行为
- `test`：新增或调整测试
- `other`：其他类型

示例：

```text
feat: 支持 QQ 输出前脱除 Markdown
fix: 修复私聊文件下载失败
docs: 同步 agent 协作规范
```

## PR 与 Review

PR 标题和正文必须使用中文，并按 `.github/PULL_REQUEST_TEMPLATE.md` 填写。PR 应说明：

- 本次改动解决的问题或新增能力
- 主要改动内容
- 验证方式
- 影响范围
- 风险或需要 reviewer 注意的地方

review 时重点检查：

- 是否来自新建分支
- PR 和 Issue 是否使用中文
- 提交信息是否符合 `类型: 中文内容`
- 改动范围是否清晰、克制
- 是否说明验证方式
- 是否引入配置、依赖或部署影响

## 项目边界

珞樱（LuoYing）是一个多入口 AI 助手机器人，支持 QQ OneBot、FastAPI Web API 和 CLI。

本仓库只维护 Python 后端、后端 API、VoicePort、Web transport、知识库能力和后端测试。React + TypeScript + Vite 前端、Live2D、Vite 代理、浏览器语音交互、前端组件和前端构建配置都属于同级独立仓库 `../LuoYing-Frontend/`。

## 项目结构

```text
src/luoying_bot/
  main_web.py                         # Web 入口
  main_cli_stream.py                  # CLI 入口
  main_qq.py                          # QQ OneBot 入口
  domain/                             # 核心领域模型
  application/                        # 消息处理、命令、服务、Agent / Skill
  capabilities/knowledge_base/        # 知识库能力
  infra/
    http/                             # FastAPI router 与 HTTP API
    voice/                            # VoicePort 实现
    transports/                       # Web / CLI / QQ transport
docs/                                 # 架构文档、API 参考、知识库说明
test/                                 # pytest 测试
```

## 关键技术约定

### VoicePort 与路由

后端 `VoicePort` 定义在 `src/luoying_bot/infra/voice/`。Voice router 的 `prefix="/voice"` 已是完整路径，`include_router()` 时不要再加 `prefix="/api"`；前端开发代理会处理路径重写。

后端默认端口是 `8000`，不是 `18000`。

### API 路由注册

`src/luoying_bot/infra/http/api.py` 中注册 router 时：

- Voice router：无需额外 prefix。
- 其他 router：若需 prefix，确保与前端 Vite 代理 rewrite 规则一致。
- `/api` 前缀由代理 stripped，不应在后端 Voice router 上重复叠加。

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

涉及知识库时可参考：

```bash
uv run python test/kb/run_kb_harness.py
```

## 修改原则

- 优先遵循现有架构边界和本地代码风格。
- 保持改动范围克制，避免无关重构。
- 修改共享能力、用户可见行为或跨入口逻辑时，补充或更新相关测试。
- 不要提交 `.env`、本地数据、缓存、虚拟环境或生成产物。
- 涉及配置、依赖、部署、端口或外部服务行为变化时，在 PR 中明确说明影响范围和风险。

## 深入文档

- [README.md](README.md) — 项目介绍、启动方式和配置说明
- [docs/web_frontend_api.md](docs/web_frontend_api.md) — Web API 参考
- [docs/kb_architecture_report.md](docs/kb_architecture_report.md) — 知识库架构
- [docs/knowledge_base_integration.md](docs/knowledge_base_integration.md) — 知识库接入指南
