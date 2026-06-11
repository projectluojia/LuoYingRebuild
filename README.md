# LuoYing

<div align="center">

<pre>
 __                          __      __  __                     
/  |                        /  \    /  |/  |                    
$$ |       __    __   ______$$  \  /$$/ $$/  _______    ______  
$$ |      /  |  /  | /      \$$  \/$$/  /  |/       \  /      \ 
$$ |      $$ |  $$ |/$$$$$$  |$$  $$/   $$ |$$$$$$$  |/$$$$$$  |
$$ |      $$ |  $$ |$$ |  $$ | $$$$/    $$ |$$ |  $$ |$$ |  $$ |
$$ |_____ $$ \__$$ |$$ \__$$ |  $$ |    $$ |$$ |  $$ |$$ \__$$ |
$$       |$$    $$/ $$    $$/   $$ |    $$ |$$ |  $$ |$$    $$ |
$$$$$$$$/  $$$$$$/   $$$$$$/    $$/     $$/ $$/   $$/  $$$$$$$ |
                                                      /  \__$$ |
                                                      $$    $$/ 
                                                       $$$$$$/  

</pre>
</div>

**LuoYing**（珞樱）是一个面向 QQ、Web 与 CLI 的多端 Agent 机器人框架。它把不同平台的消息统一成平台无关的内部模型，再通过命令系统、业务服务、长期记忆和可调用 Skill 组织成一条可维护的对话处理链路。

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](#环境要求)
[![许可证](https://img.shields.io/badge/license-Apache--2.0-green)](./LICENSE)
[![OpenAI compatible](https://img.shields.io/badge/LLM-OpenAI--compatible-7c3aed)](#模型配置)

LuoYing 的目标不是只做一个固定功能的聊天机器人，而是提供一个适合二次开发的 Agent 应用骨架：平台接入、会话调度、工具调用、文件工作区、长期记忆、提醒与备忘录等能力都尽量放在清晰的边界内。

## 特性

- **多端入口**：支持 QQ OneBot WebSocket、FastAPI Web API 和 CLI 调试入口。
- **统一消息模型**：通过 `UniMessage`、`MessageSegment`、`ChatContext` 屏蔽平台差异。
- **混合处理链路**：确定性命令、快捷回复、业务服务、ReAct 风格 Agent 与 Skill 协同工作。
- **会话调度**：同一会话串行处理，跨会话并发处理。
- **长期能力**：提醒事项、备忘录、用户资料、Memobase 长期记忆、用户提示词偏好。
- **文件工作区**：上传文档、读取常见文件、生成脚本、运行 Python、下载工作区文件。
- **多模态输入**：支持图片上传、QQ 图片下载、图片理解、OCR 与截图分析。
- **外部信息**：天气查询、Tavily / DuckDuckGo 搜索兜底、arXiv 论文检索。
- **Web API**：提供普通 `/chat` 与实验性 SSE `/chat/stream`。
- **兼容模型服务**：可接入 DeepSeek、DashScope、OpenAI 或其他 OpenAI-compatible 服务。

## 项目状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| QQ 入口 | 日常可用 | 主链路，支持群聊、私聊白名单、OneBot 事件、图片、文件与部分群管理能力。 |
| Web 入口 | 可用，持续演进 | 支持聊天、SSE、图片/文件上传、工作区文件树和文件下载；认证仍是简化实现。 |
| CLI 入口 | 可用 | 适合本地调试 Agent、Skill、流式输出和文件工作区。 |
| Agent / Skill | 可用 | 使用 OpenAI-compatible API；部分 Skill 需要额外 API Key。 |
| 长期记忆 | 可用 | 短期上下文保存在进程内；长期记忆通过 Memobase 接入。 |
| 数据持久化 | 混合实现 | 备忘录、提醒、用户资料等默认使用本地 JSON / SQLite / 目录文件。 |
| 测试与 CI | 计划中 | 当前主要依赖手动 smoke test，欢迎补充 pytest 与 CI。 |

## 环境要求

- Python 3.11+
- 一个 OpenAI-compatible Chat Completions 服务
- 可选：OneBot v11 兼容实现，用于 QQ 入口
- 可选：Memobase，用于长期记忆
- 可选：Tavily、和风天气、图片理解/编程模型等外部服务

## 快速开始

```bash
git clone https://github.com/projectluojia/LuoYingRebuild.git
cd LuoYingRebuild

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
export PYTHONPATH=src
```

Windows PowerShell：

```powershell
$env:PYTHONPATH = "src"
```

### 模型配置

编辑 `.env`，至少配置主模型：

```env
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=deepseek-chat
LLM_TEMPERATURE=1.0
```

如果要使用文件工作区、代码生成、图片理解或截图分析能力，还需要配置编程/多模态模型：

```env
CODER_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
CODER_API_KEY=your_api_key
CODER_MODEL=qwen3-max
CODER_TEMPERATURE=0.2
```

当 `OPENAI_API_KEY` 为空时，主模型适配器会返回本地占位回复，方便做启动检查；真实对话和 Agent 能力仍需要有效模型。

### 启动 Web 入口

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

### 启动 CLI 入口

```bash
PYTHONPATH=src python -m luoying_bot.main_cli_stream
```

指定会话和用户信息：

```bash
PYTHONPATH=src python -m luoying_bot.main_cli_stream \
  --session-id local-dev \
  --user-id cli-user \
  --user-name local-user
```

输入 `exit`、`quit`、`q`、`退出` 或 `再见` 结束会话。

### 启动 QQ 入口

在 `.env` 中配置 OneBot 与机器人信息：

```env
WS_URL=ws://127.0.0.1:3001
WS_TOKEN=
BOT_QQ=your_bot_qq
BOT_NAME=珞樱
SPECIFIC_GROUP_IDS=group_id_1,group_id_2
QQ_PRIVATE_USER_IDS=user_id_1,user_id_2
OPS=admin_user_id_1,admin_user_id_2
```

启动：

```bash
PYTHONPATH=src python -m luoying_bot.main_qq
```

QQ 群聊默认只处理被机器人提及的消息。QQ 私聊默认使用白名单；如果 `QQ_PRIVATE_USER_IDS` 为空，则不会回复 QQ 私聊。

## Docker

构建并运行默认 QQ 入口：

```bash
docker build -t luoying .
docker run --rm --env-file .env -v "$PWD/data:/app/data" luoying
```

运行 Web 入口：

```bash
docker run --rm --env-file .env \
  -e WEB_HOST=0.0.0.0 \
  -p 8000:8000 \
  -v "$PWD/data:/app/data" \
  luoying python -m luoying_bot.main_web
```

生产或准生产 QQ 部署建议使用 Docker Compose：OneBot 实现、LuoYing、可选 Memobase、可选 embedding 服务和持久化卷放在同一套编排里。

## 长期记忆

LuoYing 使用 Memobase 作为长期记忆后端。应用层会先把平台用户 ID 映射为稳定 UUID，再调用 Memobase，因为新版 Memobase API 要求用户 ID 是 UUID。

LuoYing 侧配置：

```env
MEMOBASE_PROJECT_URL=http://127.0.0.1:8019
MEMOBASE_API_KEY=secret
MEMOBASE_MAX_CONTEXT_TOKENS=1000
MEMOBASE_WRITE_SYNC=false
```

自托管 Memobase 可以搭配本地 embedding 服务。仓库提供了一个诊断脚本，用来检查 Memobase 健康状态、embedding 维度、用户创建、聊天写入、flush 和 context 读取：

```bash
python3 scripts/diagnose_memobase.py \
  --memobase-url http://127.0.0.1:8019 \
  --memobase-key secret \
  --embedding-url http://127.0.0.1:8080/v1 \
  --user-id 2564664062 \
  --output /tmp/memobase_diag.json
```

旧的 `data/user_memory/*.txt` 用户画像文件不会被 Memobase 实现读取。

## 配置说明

完整模板见 [`.env.example`](./.env.example)。

### 基础配置

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `VERSION` | `v2.4.0` | 版本展示值。 |
| `BOT_QQ` | `3949843218` | QQ 机器人账号。 |
| `BOT_NAME` | `珞樱` | 机器人显示名，用于消息归一化。 |
| `HELP` | 博客链接 | `/help` 返回的帮助链接。 |
| `LOG` | 博客链接 | `/help` 返回的开发日志链接。 |

### 模型配置

| 变量 | 说明 |
| --- | --- |
| `OPENAI_BASE_URL` | 主 Agent 使用的 OpenAI-compatible API 地址。 |
| `OPENAI_API_KEY` | 主 Agent API Key。 |
| `OPENAI_MODEL` | 主 Agent 模型名。 |
| `LLM_TEMPERATURE` | 主 Agent 温度。 |
| `OPENAI_ENABLE_THINKING` | 是否向兼容服务传递 thinking 开关。 |
| `CODER_BASE_URL` | 文件工作区、代码生成、图片理解模型 API 地址。 |
| `CODER_API_KEY` | 文件工作区、代码生成、图片理解模型 API Key。 |
| `CODER_MODEL` | 文件工作区、代码生成、图片理解模型名。 |
| `CODER_TEMPERATURE` | 编程模型温度。 |

### QQ 配置

| 变量 | 说明 |
| --- | --- |
| `WS_URL` | OneBot WebSocket 地址。 |
| `WS_TOKEN` | OneBot 鉴权 token。 |
| `OPS` | 管理员用户 ID，逗号分隔。 |
| `SPECIFIC_GROUP_IDS` | 允许响应的 QQ 群号，逗号分隔。 |
| `QQ_PRIVATE_USER_IDS` | 允许私聊的 QQ 用户 ID，逗号分隔。 |
| `TRIGGER_PREFIX` | 命令触发前缀。 |

### 数据配置

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATA_DIR` | `./data` | 运行时数据根目录。 |
| `MEMO_DIR` | `./data/memo` | 用户备忘录目录。 |
| `QUICK_REPLY_FILE` | `./data/quick_replies.json` | 快捷回复配置。 |
| `USER_DB_FILE` | `./data/userdatabase.json` | 用户绑定资料。 |
| `REMINDER_DB_FILE` | `./data/reminders.json` | 提醒事项。 |
| `USER_PROMPT_SETTINGS_FILE` | `./data/user_prompt_settings.json` | 用户提示词偏好。 |
| `SCRIPT_WORKSPACE_DIR` | `./data/scripts` | 每个用户独立的文件/脚本工作区。 |

### 可选外部服务

| 变量 | 说明 |
| --- | --- |
| `MEMOBASE_PROJECT_URL` | Memobase Cloud 或自托管地址。 |
| `MEMOBASE_API_KEY` | Memobase 项目 token。 |
| `MEMOBASE_MAX_CONTEXT_TOKENS` | 注入提示词的长期记忆上下文 token 上限。 |
| `MEMOBASE_WRITE_SYNC` | 写入记忆后是否等待 Memobase 处理完成。 |
| `QWEATHER_API_KEY` | 和风天气 API Key。 |
| `WEATHER_BASE_URL` | 天气接口地址。 |
| `TAVILY_API_KEY` | Tavily 搜索 API Key；未配置时会尝试 DuckDuckGo HTML 兜底。 |
| `IMAGE_API_KEY` / `IMAGE_BASE_URL` / `IMAGE_MODEL` | 预留图片生成配置。 |

### 运行限制

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PYTHON_SCRIPT_TIMEOUT_SEC` | `20` | 文件工作区中 Python 脚本运行超时时间。 |
| `MEMORY_MAX_MESSAGES_PER_THREAD` | `80` | 单会话短期上下文最大消息数。 |
| `AGENT_SKILL_TIMEOUT_SEC` | `360` | 单个 Skill 调用超时。 |
| `AGENT_TOTAL_TIMEOUT_SEC` | `6000` | 单次 Agent 回复总超时。 |
| `MAX_CONCURRENT_MESSAGE_TASKS` | `200` | 消息处理全局并发上限。 |

## Web API

完整协议见 [docs/web_frontend_api.md](./docs/web_frontend_api.md)。

常用端点：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查。 |
| `GET` | `/` | 内置 Web 页面。 |
| `GET` | `/conversations` | 列出当前 Web 用户的对话。 |
| `GET` | `/conversations/{thread_id}/messages` | 读取指定对话的模型上下文视图。 |
| `PATCH` | `/conversations/{thread_id}/archive` | 归档对话。 |
| `PATCH` | `/conversations/{thread_id}/restore` | 恢复归档对话。 |
| `DELETE` | `/conversations/{thread_id}` | 删除对话。 |
| `POST` | `/chat` | 非流式聊天。 |
| `POST` | `/chat/stream` | 实验性 SSE 流式聊天。 |
| `POST` | `/uploads/images` | 上传图片，最大 10 MB。 |
| `POST` | `/uploads/files` | 上传普通文件，最大 25 MB。 |
| `GET` | `/workspace/tree` | 获取当前 Web 用户工作区文件树。 |
| `GET` | `/download/{user_id}/{file_path}` | 下载工作区文件。 |

示例：

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo","text":"你好，介绍一下你自己","image_ids":[],"file_ids":[]}'
```

## 命令

QQ 入口默认启用命令系统。Web 入口当前优先走 Agent，默认关闭命令派发。

| 命令 | 场景 | 说明 |
| --- | --- | --- |
| `/help` | 通用 | 返回帮助与开发日志链接。 |
| `/version` | 通用 | 返回版本信息。 |
| `/clear` | 通用 | 清除当前会话短期记忆。 |
| `/thread` / `/thread_info` | QQ | 查看当前对话 ID、标题、时间和摘要。 |
| `/bind` / `/upd` / `/withdraw` | 通用 | 管理用户绑定资料。 |
| `/prompt*` | 通用 | 管理用户提示词偏好。 |
| `/tree` | QQ 私聊 | 查看当前用户脚本工作区文件树。 |
| `/refresh_list` / `/random_one` | QQ 群聊 | 刷新成员缓存或随机抽取群成员。 |
| `/title` / `/rmtitle` | QQ 群聊 | 管理群头衔。 |
| `/emoji*` / `/dice` | QQ | 表情反应、表情代码测试和骰子 CQ 码。 |
| `/ban` / `/unban` | 管理员 | 全局阻塞或解除阻塞用户。 |
| `/whole_ban` / `/dis_whole_ban` | 管理员 QQ 群聊 | 开启或关闭全员禁言。 |

## Agent 技能

| Skill | 平台 | 能力 |
| --- | --- | --- |
| `reminder` | QQ / Web / CLI | 创建、查看和删除提醒事项。 |
| `memo` | QQ / Web / CLI | 读写、搜索、更新和删除备忘录。 |
| `user_memory` | QQ / Web / CLI | 在用户明确要求时读取、写入或清空长期记忆。 |
| `weather` | QQ / Web / CLI | 查询天气。 |
| `web_search` | QQ / Web / CLI | 通过 Tavily 或 DuckDuckGo 兜底搜索网页。 |
| `arxiv` | QQ / Web / CLI | 检索 arXiv 论文。 |
| `time` | QQ / Web / CLI | 查询当前时间。 |
| `fortune` | QQ / Web / CLI | 生成每日运势。 |
| `image_agent` | QQ / Web / CLI | 图片描述、OCR、多图比较、截图分析。 |
| `file_workspace_agent` | QQ / Web / CLI | 读取文档、管理工作区文件、生成并运行 Python 脚本。 |
| `qq_context_info` | QQ | 查询 QQ 群、成员和用户绑定上下文。 |

## 架构概览

```text
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
  - 同一会话串行处理
  - 不同会话并发处理
     |
     v
EventHandler
  - 运行状态
  - 快捷回复
  - 命令派发
  - Agent 派发
     |
     v
Command / Skill / Service / Repo / External API
```

源码结构：

```text
src/luoying_bot/
├── application/
│   ├── agent/          # AgentService、SkillRegistry、Skill 实现
│   ├── commands/       # 命令系统
│   ├── jobs/           # 内置计划任务
│   ├── services/       # 应用服务层
│   ├── event_handler.py
│   └── message_processor.py
├── domain/             # 平台无关领域模型
├── infra/
│   ├── cli/            # CLI UI
│   ├── llm/            # OpenAI-compatible 模型适配
│   ├── repos/          # 本地持久化实现
│   ├── scheduler/      # 异步调度器
│   ├── transports/     # QQ / Web / CLI transport
│   └── web/            # FastAPI 应用和内置 Web 页面
├── ports/              # 抽象接口
├── bootstrap.py        # 依赖装配
├── config.py           # 环境变量配置
├── main_cli_stream.py
├── main_qq.py
└── main_web.py
```

## 运行时数据

默认运行时数据位于 `data/`，该目录已被 Git 忽略：

```text
data/
├── memo/                    # 用户备忘录
├── reminders.json           # 提醒事项
├── scripts/                 # 用户文件/脚本工作区
├── user_prompt_settings.json
└── userdatabase.json
```

文件工作区按用户隔离，例如：

```text
data/scripts/web-user/
data/scripts/<qq-user-id>/
```

Memobase 的长期记忆由 Memobase 部署保存，不再由 `data/user_memory` 维护。

## 开发

提交前建议至少运行：

```bash
PYTHONPATH=src python -m compileall src
PYTHONPATH=src python -m luoying_bot.main_cli_stream
PYTHONPATH=src python -m luoying_bot.main_web
curl http://127.0.0.1:8000/health
```

### 添加命令

1. 在 `src/luoying_bot/application/commands/` 下新增或修改命令模块。
2. 继承 `BaseCommand`。
3. 设置 `name`、`aliases`、权限和参数约束。
4. 实现 `validate()` 和 `execute()`。
5. 启动时 `CommandDispatcher.auto_register()` 会自动注册命令。

### 添加技能

1. 在 `src/luoying_bot/application/agent/skills/` 下新增模块。
2. 继承 `BaseSkill`。
3. 设置 `name`、`platform` 和 `description`。
4. 在 `run()` 中返回 `SkillResult`。
5. 启动时 `SkillRegistry.auto_register()` 会按当前 transport 平台注册可用 Skill。

### 添加新平台

1. 实现 `ports.transport.ChatTransport`。
2. 将平台事件转换为 `UniMessage` 和 `ChatContext`。
3. 在 `bootstrap.py` 中增加容器装配函数。
4. 尽量让平台差异停留在 transport 层，不要把平台专属逻辑写入 service 或 domain。

## 安全提示

- 不要提交 `.env`，其中包含 API Key 和平台 token。
- 文件工作区可以运行 Python 脚本，目前不是强沙箱。
- Web 入口当前使用固定匿名用户，不适合直接暴露到公网。
- 上传文件会写入 `SCRIPT_WORKSPACE_DIR`；图片上限 10 MB，普通文件上限 25 MB。
- 对话内容、图片、文档片段和生成摘要可能会发送给你配置的模型服务。
- QQ 集成依赖 OneBot 权限，请只授予确实需要的能力。

## 路线图

- 为 Web 入口补充真实认证、用户管理和权限控制。
- 稳定 `/chat/stream` 事件协议。
- 增加统一的非文本输出事件模型，覆盖文件、生成图片和任务状态。
- 为提醒、备忘录、快捷回复和提示词偏好提供可选数据库实现。
- 补充 pytest、类型检查和 GitHub Actions。
- 增加标准 Python 包配置，取消手动 `PYTHONPATH=src`。
- 完善 Memobase 部署文档，并提供示例 Compose 栈。

## 贡献

欢迎提交 Issue 和 Pull Request。建议变更保持小而清晰，并说明：

- 影响的入口：QQ、Web、CLI 或通用核心；
- 新增的环境变量、数据文件或 API 字段；
- 运行过的检查命令；
- 兼容性和迁移注意事项。

## 许可证

LuoYing 使用 [Apache License 2.0](./LICENSE) 开源。
