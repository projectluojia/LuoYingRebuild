#Warning: In this branch, vibe coding is frequently used.
# 珞樱 Luoying Bot V2 开发者参考文档

珞樱（Luoying）是一个面向 QQ 群聊场景的智能 Agent 机器人项目。
本项目由武汉大学人工智能学院相关场景驱动开发，当前版本采用了相对清晰的分层架构：传输层、应用层、能力层、基础设施层彼此解耦，并在自然语言处理上引入了主 Agent + Skill + 子 Agent 的能力编排模式。

与早期“规则回复 + 命令触发”为主的机器人不同，V2 更强调：

- 面向工程维护的模块化设计
- 指令系统与自然语言 Agent 并存
- 技能自动注册与统一调度
- 多轮记忆与群聊上下文感知
- 图片理解子 Agent
- 编程子 Agent
- 可恢复的提醒调度系统
- 兼容 Web 入口的统一事件处理模型

本仓库主要面向开发者阅读与二次开发，不是一个“只改配置即可直接部署全部功能”的傻瓜包。

------

## 1. 项目目标

本项目尝试解决的不是“做一个能聊天的 QQ bot”这么简单，而是构建一个：

- 能接入 QQ / Web 等多种输入源
- 能区分命令、闲聊、任务型请求
- 能自动选择技能或子 Agent 处理复杂任务
- 能在群聊环境下保持用户身份、会话、回复链等上下文
- 能持续扩展更多校园场景能力

的轻量级多能力 Agent 系统。

------

## 2. 当前能力概览

基于当前代码实现，项目已经具备以下核心能力：

### 指令系统

支持通过 `/xxx` 形式触发明确命令，例如：

- `/help`
- `/clear`
- `/repeat`
- `/bind`
- `/upd`
- `/withdraw`
- `/random_one`
- `/refresh_list`
- `/title`
- `/rmtitle`
- `/activate`
- `/deactivate`
- `/ban`
- `/unban`
- `/whole_ban`
- `/dis_whole_ban`
- `/attach`
- `/dice`
- `/version`

### Agent 自然语言能力

主 Agent 目前通过 ReAct 风格循环驱动，可根据用户消息自动选择 skill 执行，例如：

- 查询武汉天气
- 获取当前时间
- 今日运势
- 联网搜索
- 提醒事项管理
- 备忘录管理
- 群信息 / 群成员信息查询
- 图片理解
- 编程工作区操作

### 图片理解子 Agent

支持：

- 图片描述
- 图中文字提取
- 截图内容分析
- 多图比较
- 回复消息中的图片理解
- 指定第几张图片分析

### 编程子 Agent

支持：

- 列出用户脚本
- 读取脚本
- 创建脚本
- 覆盖脚本
- 删除脚本
- 运行 Python 脚本
- 将脚本发送到当前会话

### 数据与业务能力

支持：

- 用户资料 JSON 持久化
- 备忘录按用户存储
- 提醒任务持久化与恢复
- 群启用状态 / 封禁 / 复读模式等运行时控制

### 传输与接口

目前已实现：

- QQ OneBot WebSocket 输入输出适配
- 简单 Web API 聊天接口

------

## 3. 项目结构

当前主要目录如下：

```text
src/
├─ data/                         # 运行期数据目录
│  ├─ memo/                      # 用户备忘录
│  ├─ scripts/                   # 用户脚本工作区
│  ├─ quick_replies.json         # 快捷回复配置
│  ├─ reminders.json             # 提醒任务存储
│  └─ userdatabase.json          # 用户资料存储
│
└─ luoying_bot/
   ├─ application/               # 应用层
   │  ├─ agent/                  # 主 Agent 与 Skill 系统
   │  │  ├─ skills/              # 所有技能实现
   │  │  ├─ agent_service.py
   │  │  ├─ skill_base.py
   │  │  └─ skill_registry.py
   │  ├─ commands/               # 指令系统
   │  ├─ jobs/                   # 预留/任务相关
   │  ├─ services/               # 业务服务层
   │  └─ event_handler.py        # 统一事件入口
   │
   ├─ domain/                    # 领域模型
   │  ├─ context.py
   │  ├─ message.py
   │  └─ result.py
   │
   ├─ infra/                     # 基础设施层
   │  ├─ llm/                    # LLM 适配
   │  ├─ memory/                 # 会话记忆实现
   │  ├─ repos/                  # JSON 仓储实现
   │  ├─ scheduler/              # 调度器
   │  ├─ transports/             # 传输层适配
   │  └─ web/                    # Web API
   │
   ├─ ports/                     # 抽象接口层
   ├─ bootstrap.py               # 容器构建入口
   ├─ config.py                  # 配置中心
   ├─ constants.py               # 常量与系统提示词
   ├─ main_qq.py                 # QQ 入口
   └─ main_web.py                # Web 入口
```

------

## 4. 架构说明

### 4.1 总体分层

本项目整体可以理解为如下分层：

- `domain`：纯领域对象，表达统一消息、上下文、回复等概念
- `ports`：抽象接口，定义传输、存储、记忆、LLM 等能力边界
- `infra`：接口实现层，例如 WebSocket QQ 适配器、JSON 仓储、内存记忆
- `application/services`：业务服务层，负责提醒、备忘录、用户信息、运行时状态等
- `application/commands`：命令系统
- `application/agent`：主 Agent、skill 注册与执行
- `application/event_handler.py`：统一消息入口，串起快捷回复、命令、Agent 等行为

### 4.2 启动流程

以 QQ 主入口 `main_qq.py` 为例，启动逻辑大致如下：

1. 调用 `build_qq_container()` 构建应用容器
2. 建立 QQ WebSocket 连接
3. 恢复历史提醒任务
4. 注册内置定时事件
5. 启动调度器
6. 持续接收平台消息
7. 将消息交给 `EventHandler` 统一处理

也就是说，整个系统是围绕一个 `AppContainer` 组织起来的。

### 4.3 容器装配

`bootstrap.py` 负责装配以下对象：

- `QQWsTransport`
- `GroupRuntime`
- `UserService`
- `ReminderService`
- `BuiltinScheduleService`
- `MemoService`
- `QuickReplyService`
- `ScriptWorkspaceService`
- `InMemoryConversationMemory`
- `OpenAICompatibleChatModel`
- `CommandDispatcher`
- `SkillRegistry`
- `AgentService`
- `EventHandler`

这让项目具备比较明显的“依赖集中装配”特点，后续替换实现时比较方便。

------

## 5. 消息处理链路

`EventHandler` 是整个系统的统一入口。

一个 QQ 事件进入后，大致会按以下顺序处理：

1. 检查上下文是否存在
2. 检查用户是否被封禁
3. 检查当前群是否启用
4. 特判戳一戳通知
5. 提取普通文本 / LLM 文本
6. 匹配快捷回复
7. 检查是否 `@机器人`
8. 若是 `/命令`，进入命令分发器
9. 若当前群处于复读模式，则直接复读
10. 其他情况进入主 Agent

这条链路非常重要，因为你之后无论扩展什么能力，最终都要考虑它应该接在这里的哪个分支上。

------

## 6. 主 Agent 设计

### 6.1 执行模式

`AgentService` 目前采用的是一个简化版 ReAct 循环：

- 读取可用技能摘要
- 读取当前线程的历史记忆
- 把当前用户消息包装成结构化文本
- 要求模型只能输出两种 JSON：
  - 调用某个 skill
  - 给出最终回答
- 每一步只允许做一件事
- 将每一步 action / observation 记入 scratchpad
- 最终得到 answer 或走 fallback

### 6.2 为什么这么设计

这套设计比“直接让模型自己说自己要调什么工具”更受控，主要优点是：

- skill 边界更清晰
- 便于调试中间过程
- 便于扩展新能力
- 失败时能 fallback 为普通自然语言回答
- 主 Agent 与 skill 实现解耦

### 6.3 当前主 Agent 的局限

基于当前实现，有几点需要开发者注意：

- skill 调度依赖模型输出严格 JSON
- JSON 不合法时，会进入 observation 重试
- `max_steps` 默认为 20，复杂任务可能较慢
- 记忆当前为内存实现，重启后丢失
- 主 Agent 输出风格高度受 `constants.py` 中系统提示词影响

------

## 7. Skill 系统

### 7.1 自动注册

`SkillRegistry` 会自动扫描：

```python
luoying_bot.application.agent.skills
```

目录下的所有模块，并注册继承 `BaseSkill` 的类。

这意味着你新增 skill 的基本步骤是：

1. 在 `application/agent/skills/` 下新建一个 `.py`
2. 定义一个继承 `BaseSkill` 的类
3. 实现 `name`、`description`、`run()`
4. 保证模块可被 import

启动后即可自动注册，无需手动改总表。

### 7.2 当前已有 skill

根据当前代码，主要包括：

- `ReminderSkill`
- `WeatherSkill`
- `WebSearchSkill`
- `MemoSkill`
- `GroupInfoSkill`
- `CodingAgentSkill`
- `ImageAgentSkill`

其中后两个本质上已经不是“简单工具 skill”，而是“skill 封装了一个子 Agent”。

------

## 8. 指令系统

### 8.1 自动注册机制

命令系统和 skill 很像，`CommandDispatcher` 会自动扫描：

```python
luoying_bot.application.commands
```

目录下的命令类并注册。

### 8.2 适合用命令的场景

命令系统适合：

- 参数格式明确
- 行为高度确定
- 不希望依赖模型理解
- 希望响应更快更稳定

例如：

- 绑定资料
- 更新资料
- 管理员操作
- 开关模式
- 查看版本
- 清空会话记忆

### 8.3 适合用 Agent 的场景

自然语言 Agent 更适合：

- 模糊表达
- 多步任务
- 用户不愿记命令
- 图像 / 搜索 / 推理类请求

项目同时保留两套入口，是一个很合理的工程折中。

------

## 9. 图片理解子 Agent

`ImageAgentSkill` 是当前比较有特色的一块。

### 9.1 支持来源

它会同时尝试收集：

- 当前消息中的图片
- 用户回复的那条消息中的图片

并且只保留一层 reply，不会无限递归展开。

### 9.2 支持能力

当前可用的工具包括：

- `list_current_images`
- `describe_images`
- `answer_about_images`

### 9.3 实现特点

图片能力并不是主 Agent 自己直接看图，而是：

1. 主 Agent 决定调用 `image_agent`
2. `ImageAgentSkill` 收集图片
3. 通过 OneBot 获取原图路径，必要时压缩
4. 再把任务交给单独的 LangChain 子 Agent

### 9.4 开发注意事项

- 回复消息图片理解依赖平台能正确返回被回复消息
- 本地图片路径依赖 OneBot `get_image`
- 大图会走压缩逻辑
- 目前系统提示词和多图决策逻辑对模型行为影响很大

------

## 10. 编程子 Agent

`CodingAgentSkill` 面向“用户自己的脚本工作区”。

### 10.1 工作区模型

每个用户在：

```text
data/scripts/<user_id>/
```

下拥有自己的文件空间。

### 10.2 支持操作

通过 LangChain tool 暴露给子 Agent 的包括：

- `list_scripts`
- `read_script`
- `create_script`
- `overwrite_script`
- `delete_script`
- `run_python_script`
- `send_script`

### 10.3 安全设计

脚本服务 `ScriptWorkspaceService` 做了路径约束：

- 不允许绝对路径
- 不允许 `..`
- 不允许越界到用户目录之外

所以这是一个“受限工作区”设计，而不是给模型整机文件访问权限。

### 10.4 当前边界

- 只支持直接运行 `.py`
- 不支持安装依赖
- 不支持 shell 命令
- 不支持访问外部网络
- 发送脚本依赖传输层上传文件能力

------

## 11. 数据存储

当前项目的数据层以 JSON 为主，属于轻量实现。

### 用户资料

```
src/data/userdatabase.json
```

### 提醒事项

```
src/data/reminders.json
```

### 快捷回复

```
src/data/quick_replies.json
```

### 用户备忘录

```
src/data/memo/
```

通常为一个用户一个文件。

### 用户脚本工作区

```
src/data/scripts/<user_id>/
```

### 优缺点

优点：

- 易读
- 易调试
- 无需数据库依赖
- 适合早期开发和小规模部署

缺点：

- 并发能力一般
- 原子性有限
- 不适合大规模场景
- 长期来看应考虑迁移数据库或 KV 存储

------

## 12. 提醒与调度系统

### 12.1 组成

提醒能力由以下部分配合完成：

- `ReminderService`
- `JsonReminderRepo`
- `AsyncScheduler`

### 12.2 运行特性

系统启动时会：

- 从 `reminders.json` 恢复任务
- 注册内置定时任务
- 启动调度器

### 12.3 内置计划事件

当前内置逻辑包括：

- 每日早安 / 天气播报
- 每日睡觉提醒

### 12.4 开发注意事项

如果你后续想加更多计划事件，建议统一放到 `BuiltinScheduleService` 里，不要散落在入口脚本里硬写。

------

## 13. QQ 传输层

`QQWsTransport` 是当前 QQ 平台适配器。

### 13.1 主要职责

- 连接 OneBot WebSocket
- 收发原始事件
- 调用 OneBot action
- 将 QQ 消息转换为统一 `UniMessage`
- 处理 CQ 码 / 数组消息段
- 拉取被回复消息
- 下载图片
- 发送文本
- 发送文件
- 戳一戳等平台动作

### 13.2 重要细节

项目目前已经处理了“回复消息可见性”这一点：

- 当前消息会保留 reply segment
- 被回复消息会被抓取并构造成 `reply_message`
- 但回复链只展开一层

这对图片场景和上下文理解很关键。

### 13.3 适配器意义

有了这层适配，你以后要接其他平台时，理论上只需要：

- 实现新的 transport
- 保持输出 `UniMessage`
- 复用上层 event handler / command / agent 逻辑

------

## 14. Web 入口

`main_web.py` + `infra/web/api.py` 提供了一个简单 Web 接口。

当前接口形态为：

- `POST /chat`

请求体：

```json
{
  "session_id": "test-session",
  "user_id": "123456",
  "user_name": "网页用户",
  "text": "你好"
}
```

返回体：

```json
{
  "reply": "你好呀"
}
```

这个 Web 入口目前更适合：

- 本地调试 Agent
- 为后续前端页面预留接口
- 测试统一事件模型

从代码注释和实现完整度来看，它目前属于可用但偏轻量的实验接口。

------

## 15. 环境要求

当前项目依赖见 `requirements.txt`：

- fastapi
- uvicorn
- websockets
- httpx
- pydantic
- Pillow
- python-dotenv
- langchain
- langchain-openai

建议环境：

- Python 3.11+
- Windows / Linux 均可
- 可访问对应 LLM API
- 若启用 QQ 机器人，需要 OneBot WebSocket 服务端

------

## 16. 安装

建议先创建虚拟环境：

```bash
python -m venv .venv
```

激活后安装依赖：

```bash
pip install -r requirements.txt
```

------

## 17. 配置

项目通过 `.env` 读取配置，配置入口位于：

```python
src/luoying_bot/config.py
```

### 主要配置项

#### QQ / 基础信息

```env
WS_URL=ws://127.0.0.1:3001
BOT_QQ=3949843218
BOT_NAME=珞樱
VERSION=dev
HELP=
LOG=
```

#### 主 LLM

```env
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_API_KEY=
OPENAI_MODEL=deepseek-chat
LLM_TEMPERATURE=1.0
```

#### 编程子 Agent 模型

```env
CODER_BASE_URL=https://api.deepseek.com
CODER_API_KEY=
CODER_MODEL=deepseek-reasoner
CODER_TEMPERATURE=0.2
```

#### 图片能力模型

```env
IMAGE_BASE_URL=
IMAGE_API_KEY=
IMAGE_MODEL=
```

说明：当前图片子 Agent 实际仍主要使用 `OPENAI_*` 配置，而不是完全独立走 `IMAGE_*` 配置，后续可以考虑统一或彻底拆开。

#### 天气 / 搜索

```env
QWEATHER_API_KEY=
WEATHER_BASE_URL=https://pn6yvyt6je.re.qweatherapi.com/v7/weather/now
TAVILY_API_KEY=
```

#### 数据目录

```env
DATA_DIR=./data
MEMO_DIR=./data/memo
QUICK_REPLY_FILE=./data/quick_replies.json
USER_DB_FILE=./data/userdatabase.json
REMINDER_DB_FILE=./data/reminders.json
SCRIPT_WORKSPACE_DIR=./data/scripts
```

#### 脚本运行控制

```env
PYTHON_SCRIPT_TIMEOUT_SEC=15
SCRIPT_SEND_CHUNK_SIZE=1200
SCRIPT_MAX_OUTPUT_CHARS=12000
```

#### 权限 / 群开关 / 触发前缀

```env
OPS=
SPECIFIC_GROUP_IDS=
TRIGGER_PREFIX=/,!
```

------

## 18. 启动方式

### 启动 QQ 机器人

```bash
python -m src.luoying_bot.main_qq
```

如果你的环境变量与模块路径配置不同，也可以在仓库根目录下自行调整启动方式。

### 启动 Web API

需要自行用 uvicorn 包一层，例如：

```bash
uvicorn src.luoying_bot.main_web:create_app --factory --host 0.0.0.0 --port 8000
```

------

## 19. 开发指南

### 19.1 新增一个命令

步骤：

1. 在 `application/commands/` 下新建文件
2. 定义一个继承 `BaseCommand` 的类
3. 设置 `name`
4. 实现 `validate()` 与 `execute()`
5. 保证构造函数继承父类逻辑可用
6. 启动后由 `CommandDispatcher.auto_register()` 自动注册

适合场景：

- 明确、快速、低歧义的操作

------

### 19.2 新增一个 skill

步骤：

1. 在 `application/agent/skills/` 下新建模块
2. 继承 `BaseSkill`
3. 定义唯一 `name`
4. 写清楚 `description`
5. 实现 `run(req: SkillRequest) -> SkillResult`

建议：

- `description` 要写具体，方便主 Agent 正确决策
- 参数格式最好写进说明里
- 返回尽量结构化，必要时同时给 `text` 与 `data`

------

### 19.3 新增业务服务

如果一个能力已经不只是“简单查询”，建议先沉到 `application/services/` 中封装业务逻辑，再由命令或 skill 调用，而不是在命令类 / skill 类里堆业务代码。

这样更便于：

- 单元测试
- 重用
- 后续替换存储实现

------

### 19.4 替换存储实现

当前仓储是 JSON 实现。
如果想迁移数据库，建议从 `ports` 层定义新的抽象开始，或直接替换 `infra/repos` 下对应实现，再尽量保持 `services` 层接口不变。

------

### 19.5 替换模型供应商

当前 LLM 接入位于：

- `infra/llm/openai_chat.py`
- LangChain 子 Agent 中的 `ChatOpenAI(...)`

如果要替换：

- 主 Agent：改 `OpenAICompatibleChatModel`
- 子 Agent：改 skill 中的 `ChatOpenAI` 初始化逻辑

------

## 20. 已知特点与注意事项

### 20.1 当前默认强依赖系统提示词

`constants.py` 中的提示词较长、角色设定较强，会显著影响主 Agent 与子 Agent 输出风格。

如果你想把项目改成更通用的 Agent 框架，第一件事往往是拆分这些 prompt。

### 20.2 记忆目前是内存记忆

当前 `InMemoryConversationMemory` 重启即丢失。
如果你希望真正跨重启保留上下文，需要自行实现持久化 memory。

### 20.3 JSON 存储适合轻量场景

现阶段用于个人机器人、小群测试没问题，但如果将来多群高频使用，建议尽早迁移。

### 20.4 Web 端仍偏轻量

当前 Web 接口更像调试入口，不是完整前后端产品。

### 20.5 图片 / 回复逻辑依赖平台实现

OneBot 对回复消息、图片文件路径、消息段格式的支持情况，会直接影响系统表现。

------

## 21. 未来可改进方向

从当前代码看，比较自然的演进方向包括：

- 引入持久化会话记忆
- 将 JSON 仓储迁移到 SQLite / PostgreSQL
- 拆分更严格的权限系统
- 为 skill 增加显式 schema 校验
- 给 reminder / memo / script 等服务补测试
- 让 Web 入口具备完整前端页面
- 更彻底地分离图片模型与主模型配置
- 引入更稳定的日志与监控机制
- 为 event handler 增加更细粒度的 middleware 设计

------

## 22. 开发者建议阅读顺序

如果你是第一次接手这个项目，推荐按以下顺序阅读：

1. `config.py`
2. `main_qq.py`
3. `bootstrap.py`
4. `application/event_handler.py`
5. `application/commands/`
6. `application/agent/agent_service.py`
7. `application/agent/skills/`
8. `application/services/`
9. `infra/transports/qq_ws_transport.py`

这样你会比较快建立整体心智模型。

------

## 23. 免责声明

本项目当前更适合作为：

- 个人 / 小团队开发中的校园场景 Agent 项目
- QQ 机器人系统重构实践
- 命令系统 + Agent 混合架构样例
- 图片 / 编程子 Agent 集成实验

而不是一个已经彻底产品化、平台无关、具备完整安全审计的通用框架。

使用前请根据自己的部署环境、平台协议、模型供应商和权限需求进行必要调整。

------

## 24. 致谢

感谢所有参与需求提出、测试、催更、赞助和提供真实使用反馈的人。
一个群聊机器人能走到 Agent 架构这一步，从来不是“模型一接就行”，而是大量脏活累活、边界问题和使用场景一点点磨出来的。

---

