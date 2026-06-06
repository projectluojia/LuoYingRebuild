# 珞樱 Luoying

珞樱（Luoying）是一个面向校园与社群场景的多端 Agent 系统。它把 QQ、Web、CLI 等入口收到的消息统一转换为内部消息模型，再交给命令系统、业务服务和可调用 Skill 共同处理。

当前仓库最成熟的入口是 **QQ OneBot WebSocket**，同时提供了可运行的 **Web 聊天入口** 和 **CLI 调试入口**。项目仍在快速演进中，适合用作校园 Agent、社群机器人、多端聊天后端或 Agent 能力编排框架的基础。

> 本项目为闭源项目，仓库访问、代码使用、复制、分发与商用均以项目维护者的明确授权为准。

## 特性

- 多端入口：QQ OneBot WebSocket、Web HTTP/SSE、CLI。
- 统一消息模型：`UniMessage`、`MessageSegment`、`ChatContext`。
- 混合处理链路：确定性命令、业务服务、ReAct 风格 Agent 与 Skill 系统协同工作。
- 会话调度：同一会话串行处理，跨会话并发处理。
- 长期能力：提醒事项、备忘录、用户绑定资料、用户长期记忆、快捷回复。
- 文件工作区：上传文件、读取常见文档、生成脚本、运行 Python 脚本，并通过工作区文件树下载文件。
- 多模态输入：支持图片上传、QQ 图片下载与图片理解。
- 外部信息：天气查询、Tavily / DuckDuckGo 搜索兜底、arXiv 论文检索。
- Web API：非流式 `/chat` 与实验性流式 `/chat/stream`。
- 本地持久化：JSON 与文本文件存储，默认写入 `data/`。

## 项目状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| QQ 入口 | 可用 | 主链路，支持群聊、私聊白名单、OneBot 事件、图片、私聊文件、群管理相关能力。 |
| Web 入口 | 可用但仍在演进 | 已支持聊天、SSE 流式事件、图片/文件上传、工作区文件树与文件下载。认证目前是固定匿名用户。 |
| CLI 入口 | 可用 | 适合本地调试 Agent、Skill、流式输出和文件工作区。 |
| Agent / Skill | 可用 | 使用 OpenAI-compatible API，部分 Skill 依赖额外 API Key。 |
| 数据存储 | 简单可用 | 默认本地 JSON / 文本存储，还没有数据库迁移与多实例一致性方案。 |
| 测试 / CI | 待完善 | 当前仓库尚未配置自动化测试与 CI。 |

## 快速开始

### 1. 准备环境

要求：

- Python 3.11+
- 一个 OpenAI-compatible Chat Completions 服务；例如 DeepSeek、DashScope 兼容模式或其他兼容 OpenAI SDK 的服务。
- 如果运行 QQ 入口，需要 OneBot v11 兼容实现，并启用反向 WebSocket 或等价连接。

```bash
# 从内部代码仓库取得源码后进入项目目录
cd LuoYingRebuild

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

本仓库目前没有 `pyproject.toml` 安装配置，开发运行时请显式设置 `PYTHONPATH`：

```bash
export PYTHONPATH=src
```

Windows PowerShell：

```powershell
$env:PYTHONPATH = "src"
```

### 2. 配置模型

编辑 `.env`，至少填写：

```env
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_API_KEY=你的主模型 API Key
OPENAI_MODEL=deepseek-chat
```

如果要使用文件工作区 Agent 或图片理解能力，还需要配置编程/多模态模型：

```env
CODER_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
CODER_API_KEY=你的 API Key
CODER_MODEL=qwen3-max
```

没有配置 `OPENAI_API_KEY` 时，主模型实现会返回一个本地占位回复，方便做启动 smoke test；真实对话和多数 Agent 能力仍需要有效模型。

### 3. 启动 Web 入口

```bash
PYTHONPATH=src python -m luoying_bot.main_web
```

打开：

```text
http://127.0.0.1:8000
```

也可以直接使用 Uvicorn：

```bash
PYTHONPATH=src uvicorn luoying_bot.main_web:create_app --factory --host 127.0.0.1 --port 8000
```

### 4. 启动 CLI 入口

```bash
PYTHONPATH=src python -m luoying_bot.main_cli_stream
```

常用参数：

```bash
PYTHONPATH=src python -m luoying_bot.main_cli_stream \
  --session-id local-dev \
  --user-id cli-user \
  --user-name 本地用户
```

输入 `exit`、`quit`、`q`、`退出` 或 `再见` 结束会话。

### 5. 启动 QQ 入口

先在 `.env` 中配置 OneBot WebSocket 与机器人信息：

```env
WS_URL=ws://127.0.0.1:3001
WS_TOKEN=
BOT_QQ=你的机器人 QQ
BOT_NAME=珞樱
SPECIFIC_GROUP_IDS=允许响应的群号1,允许响应的群号2
QQ_PRIVATE_USER_IDS=允许私聊的用户QQ1,允许私聊的用户QQ2
OPS=管理员QQ1,管理员QQ2
```

然后启动：

```bash
PYTHONPATH=src python -m luoying_bot.main_qq
```

QQ 群聊默认只响应被 @ 的消息；私聊默认使用白名单，`QQ_PRIVATE_USER_IDS` 为空时不回复任何 QQ 私聊。

## Docker

仓库提供了一个面向 QQ 入口的基础镜像：

```bash
docker build -t luoying .
docker run --rm --env-file .env -v "$PWD/data:/app/data" luoying
```

镜像默认命令是：

```bash
python -m luoying_bot.main_qq
```

如需运行 Web 入口，可以覆盖命令：

```bash
docker run --rm --env-file .env -e WEB_HOST=0.0.0.0 -p 8000:8000 -v "$PWD/data:/app/data" \
  luoying python -m luoying_bot.main_web
```

## 配置说明

完整模板见 [`.env.example`](./.env.example)。

### 基础配置

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `VERSION` | `v2.4.0` | 当前运行版本展示值。 |
| `BOT_QQ` | `3949843218` | QQ 机器人账号。 |
| `BOT_NAME` | `珞樱` | 机器人名称，用于消息归一化。 |
| `HELP` | 博客链接 | `/help` 返回的帮助链接。 |
| `LOG` | 博客链接 | `/help` 返回的开发日志链接。 |

### 模型配置

| 变量 | 说明 |
| --- | --- |
| `OPENAI_BASE_URL` | 主 Agent 使用的 OpenAI-compatible API 地址。 |
| `OPENAI_API_KEY` | 主 Agent API Key。 |
| `OPENAI_MODEL` | 主 Agent 模型名。 |
| `LLM_TEMPERATURE` | 主 Agent 默认温度。 |
| `OPENAI_ENABLE_THINKING` | 是否向兼容服务传递 thinking 开关。 |
| `CODER_BASE_URL` | 文件工作区 Agent / 图片理解使用的兼容 API 地址。 |
| `CODER_API_KEY` | 文件工作区 Agent / 图片理解 API Key。 |
| `CODER_MODEL` | 文件工作区 Agent / 图片理解模型名。 |
| `CODER_TEMPERATURE` | 编程模型温度。 |

### QQ 配置

| 变量 | 说明 |
| --- | --- |
| `WS_URL` | OneBot WebSocket 地址。 |
| `WS_TOKEN` | OneBot 鉴权 token。 |
| `OPS` | 管理员用户 ID，逗号分隔。 |
| `SPECIFIC_GROUP_IDS` | 允许响应的 QQ 群号，逗号分隔。 |
| `QQ_PRIVATE_USER_IDS` | 允许私聊的 QQ 用户 ID，逗号分隔。 |
| `TRIGGER_PREFIX` | 命令触发前缀配置；当前命令处理主要识别 `/`。 |

### Web 配置

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WEB_HOST` | `127.0.0.1` | Web 服务监听地址；容器内对外暴露时通常设为 `0.0.0.0`。 |
| `WEB_PORT` | `8000` | Web 服务端口。 |

### 数据与工作区

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATA_DIR` | `./data` | 运行时数据根目录。 |
| `USER_MEMORY_DIR` | `./data/user_memory` | 用户长期记忆。 |
| `MEMO_DIR` | `./data/memo` | 用户备忘录。 |
| `QUICK_REPLY_FILE` | `./data/quick_replies.json` | 群聊快捷回复配置。 |
| `USER_DB_FILE` | `./data/userdatabase.json` | 用户绑定资料。 |
| `REMINDER_DB_FILE` | `./data/reminders.json` | 提醒事项。 |
| `USER_PROMPT_SETTINGS_FILE` | `./data/user_prompt_settings.json` | 用户提示词偏好。 |
| `SCRIPT_WORKSPACE_DIR` | `./data/scripts` | 每个用户独立的文件/脚本工作区。 |

### 可选外部服务

| 变量 | 说明 |
| --- | --- |
| `QWEATHER_API_KEY` | 和风天气 API Key；未配置时天气 Skill 会提示不可用。 |
| `WEATHER_BASE_URL` | 天气接口地址，默认查询武汉实时天气。 |
| `TAVILY_API_KEY` | Tavily 搜索 API Key；未配置时会尝试 DuckDuckGo HTML 兜底。 |
| `IMAGE_API_KEY` / `IMAGE_BASE_URL` / `IMAGE_MODEL` | 预留图片生成配置，当前主链路尚未正式接入图片生成 Skill。 |

### 运行限制

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PYTHON_SCRIPT_TIMEOUT_SEC` | `20` | 文件工作区中 Python 脚本运行超时时间。 |
| `MEMORY_MAX_MESSAGES_PER_THREAD` | `80` | 单会话短期上下文最大消息数。 |
| `AGENT_SKILL_TIMEOUT_SEC` | `360` | 单个 Skill 调用超时。 |
| `AGENT_TOTAL_TIMEOUT_SEC` | `6000` | 单次 Agent 回复总超时。 |
| `MAX_CONCURRENT_MESSAGE_TASKS` | `200` | 消息处理全局并发上限。 |

## Web API

详细协议见 [`docs/web_frontend_api.md`](./docs/web_frontend_api.md)。

常用端点：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查。 |
| `GET` | `/` | 返回内置 Web 页面。 |
| `GET` | `/conversations` | 列出当前 Web 用户对话线程。 |
| `GET` | `/conversations/{thread_id}/messages` | 读取指定对话的模型上下文视图。 |
| `PATCH` | `/conversations/{thread_id}/archive` | 归档对话。 |
| `PATCH` | `/conversations/{thread_id}/restore` | 恢复归档对话。 |
| `DELETE` | `/conversations/{thread_id}` | 彻底删除对话。 |
| `POST` | `/chat` | 非流式聊天。 |
| `POST` | `/chat/stream` | 实验性 SSE 流式聊天。 |
| `POST` | `/uploads/images` | 上传图片，最多 10MB。 |
| `POST` | `/uploads/files` | 上传普通文件，最多 25MB。 |
| `GET` | `/uploads/images/{image_id}` | 读取已上传图片。 |
| `GET` | `/workspace/tree` | 获取当前 Web 用户工作区文件树。 |
| `GET` | `/download/{user_id}/{file_path}` | 下载工作区文件。 |

示例：

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo","text":"你好，介绍一下你自己","image_ids":[],"file_ids":[]}'
```

## 命令

命令在 QQ 入口中默认启用，Web 入口当前关闭命令系统，优先走 Agent。命令参数格式为 `--key value`，部分参数提供短别名。

| 命令 | 场景 | 说明 |
| --- | --- | --- |
| `/help` | 通用 | 返回帮助与开发日志链接。 |
| `/version` | 通用 | 返回当前版本。 |
| `/clear` | 通用 | 清除当前会话短期记忆。 |
| `/thread` / `/thread_info` | QQ 群聊 / QQ 私聊 | 返回当前对话 ID、标题、时间与总结。 |
| `/bind --college ... --year ... --department ... [--name ...]` | 通用 | 绑定用户资料。 |
| `/upd [--college ... --department ... --year ... --name ...]` | 通用 | 更新用户资料。 |
| `/withdraw` | 通用 | 删除用户绑定资料。 |
| `/prompt` | 通用 | 查看当前提示词偏好。 |
| `/prompt_style --style ...` | 通用 | 设置基础风格。 |
| `/prompt_trait --trait ... --level ...` | 通用 | 设置额外风格强度。 |
| `/prompt_reset` | 通用 | 重置提示词偏好。 |
| `/prompt_help` | 通用 | 查看提示词偏好命令帮助。 |
| `/tree` | QQ 私聊 | 查看当前用户脚本工作区文件树。 |
| `/refresh_list` | QQ 群聊 | 刷新群成员缓存。 |
| `/random_one` | QQ 群聊 | 随机抽取一位群成员。 |
| `/title --title ...` | QQ 群聊 | 设置当前用户群头衔。 |
| `/rmtitle` | QQ 群聊 | 清除当前用户群头衔。 |
| `/emoji --code ...` | QQ 群聊 | 给当前消息添加表情反应。 |
| `/emoji_range --left ... --right ...` | QQ 群聊 | 批量测试表情代码，范围最多 20 个。 |
| `/emoji_list` | 通用 | 返回 QQ 表情代码文档链接。 |
| `/dice` | 通用 | 发送 QQ 骰子 CQ 码。 |
| `/ban --id ...` | 管理员 | 全局阻塞指定用户消息。 |
| `/unban --id ...` | 管理员 | 取消阻塞指定用户。 |
| `/whole_ban` | 管理员 QQ 群聊 | 开启全员禁言。 |
| `/dis_whole_ban` | 管理员 QQ 群聊 | 关闭全员禁言。 |

## Agent Skills

Agent 会根据用户意图选择 Skill。已注册的主要 Skill：

| Skill | 平台 | 能力 |
| --- | --- | --- |
| `reminder` | QQ / Web / CLI | 创建、查看、删除一次性、每日重复或周期提醒。 |
| `memo` | QQ / Web / CLI | 读写、搜索、更新、删除用户备忘录。 |
| `user_memory` | QQ / Web / CLI | 读取与维护当前用户长期记忆。 |
| `weather` | QQ / Web / CLI | 查询武汉天气。 |
| `web_search` | QQ / Web / CLI | 联网搜索，优先 Tavily，失败时尝试 DuckDuckGo HTML。 |
| `arxiv` | QQ / Web / CLI | 查询 arXiv 论文并返回原文链接。 |
| `time` | QQ / Web / CLI | 查询当前时间。 |
| `fortune` | QQ / Web / CLI | 根据用户与日期生成每日运势。 |
| `image_agent` | QQ / Web / CLI | 图片描述、OCR、多图比较、截图分析。 |
| `file_workspace_agent` | QQ / Web / CLI | 读取文档、管理工作区文件、生成脚本、运行 Python 脚本。 |
| `qq_context_info` | QQ | 查询 QQ 群资料、成员信息和用户绑定资料。 |

## 架构概览

```text
平台入口
  QQ / Web / CLI
      |
      v
ChatTransport
      |
      v
UniMessage + ChatContext
      |
      v
MessageProcessor
  - 会话内串行
  - 跨会话并发
      |
      v
EventHandler
  - 运行状态 / 白名单 / 风控
  - 快捷回复
  - 命令派发
  - Agent 调用
      |
      v
Command / Agent / Service / Repo
```

目录结构：

```text
src/luoying_bot/
├── application/
│   ├── agent/          # AgentService、SkillRegistry、Skill 实现
│   ├── commands/       # 命令系统
│   ├── jobs/           # 内置计划任务
│   ├── services/       # 业务服务层
│   ├── event_handler.py
│   └── message_processor.py
├── domain/             # 平台无关领域模型
├── infra/
│   ├── cli/            # CLI TUI
│   ├── llm/            # OpenAI-compatible 模型适配
│   ├── repos/          # JSON / 文本持久化
│   ├── scheduler/      # 异步计划任务
│   ├── transports/     # QQ / Web / CLI transport
│   └── web/            # FastAPI Web API 与内置静态页面
├── ports/              # 抽象接口
├── bootstrap.py        # 容器装配
├── config.py           # 环境变量读取
├── main_cli_stream.py
├── main_qq.py
└── main_web.py
```

## 数据存储

默认运行时数据位于 `data/`，该目录已在 `.gitignore` 中忽略：

```text
data/
├── memo/                    # 用户备忘录
├── reminders.json           # 提醒事项
├── scripts/                 # 用户文件与脚本工作区
├── user_memory/             # 用户长期记忆
├── user_prompt_settings.json
└── userdatabase.json
```

文件工作区按用户隔离，例如：

```text
data/scripts/web-user/
data/scripts/<qq-user-id>/
```

## 安全提示

- `.env` 包含 API Key 和平台 token，不要提交到仓库。
- 文件工作区可以运行 Python 脚本，当前不是强沙箱。请只在可信部署环境中开放该能力。
- Web 端当前使用固定匿名用户 `web-user`，没有真实登录鉴权，不适合直接暴露到公网。
- 上传文件会落入 `SCRIPT_WORKSPACE_DIR`；图片上限 10MB，普通文件上限 25MB。
- 对话内容、图片和文件摘要可能被发送给你配置的模型服务，请遵守对应供应商的数据政策。
- QQ 入口会按配置读取群成员、消息、图片、私聊文件链接等 OneBot 能力，请谨慎配置机器人权限。

## 开发指南

### 本地检查

当前没有测试套件，提交前建议至少运行：

```bash
PYTHONPATH=src python -m compileall src
PYTHONPATH=src python -m luoying_bot.main_cli_stream
PYTHONPATH=src python -m luoying_bot.main_web
```

Web API smoke test：

```bash
curl http://127.0.0.1:8000/health
```

### 添加命令

1. 在 `src/luoying_bot/application/commands/` 下新增或修改命令模块。
2. 继承 `BaseCommand`，设置 `name`、`aliases`、权限与参数约束。
3. 实现 `validate()` 和 `execute()`。
4. QQ 容器启动时会通过 `CommandDispatcher.auto_register()` 自动注册。

### 添加 Skill

1. 在 `src/luoying_bot/application/agent/skills/` 下新增 Skill。
2. 继承 `BaseSkill`，设置 `name`、`platform`、`description`。
3. 在 `run()` 中返回 `SkillResult`。
4. `SkillRegistry.auto_register()` 会按当前 transport 平台自动注册可用 Skill。

### 添加新平台

1. 实现 `ports.transport.ChatTransport`。
2. 将平台事件转换为 `UniMessage` 和 `ChatContext`。
3. 在 `bootstrap.py` 中增加容器装配函数。
4. 尽量让平台差异停留在 transport 层，不要把平台专属逻辑写入 service 或 domain。

## 路线图

- 为 Web 入口补齐真实认证、会话管理和权限控制。
- 将 `/chat/stream` 事件协议稳定化。
- 增加统一的非文本输出事件模型，覆盖文件、图片生成、任务状态等结果。
- 将本地 JSON / 文本存储升级为可选数据库实现。
- 补齐 pytest 测试、类型检查和 GitHub Actions CI。
- 增加标准 Python 包配置，取消手动 `PYTHONPATH=src` 的要求。
- 正式接入图片生成 Skill。

## 内部协作

本项目当前按闭源项目维护。内部变更建议保持小而清晰，并说明：

- 解决的问题或新增能力。
- 影响的平台入口：QQ、Web、CLI 或通用核心。
- 是否新增环境变量、数据文件或 API 字段。
- 你运行过的检查命令。

当前项目处在架构收口阶段，新增功能时请优先复用既有的 `Command`、`Skill`、`Service`、`Repo`、`Transport` 边界。

## License

本仓库为闭源项目，未授予开源许可证。除非项目维护者另行书面授权，外部使用者不拥有复制、修改、再分发或商用授权。
