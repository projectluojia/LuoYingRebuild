# 珞樱 Luoying Bot V2.0.0

珞樱（Luoying）是一个面向 QQ 群聊场景构建的智能 Agent 机器人项目，也提供了可用于调试与扩展的 Web 入口。项目以“命令系统 + 自然语言 Agent + Skill / 子 Agent”混合架构为核心，强调可维护、可扩展、可二次开发，而不是单纯的规则回复机器人。

V2.0.0 标志着珞樱从早期快照迭代进入一个更完整、可持续演进的正式版本阶段：

- 保留命令式交互，适合稳定、明确、低歧义操作
- 保留自然语言 Agent，适合模糊表达、多步任务与技能编排
- 使用统一的消息模型与事件处理链路
- 支持提醒、备忘录、群信息、天气、联网搜索、图片理解、脚本工作区等能力
- 后端已完成一轮结构优化，包括消息处理并发化、统一预算控制、结构化日志、`ServiceHub` 注入、快捷回复文件化等改进

本仓库主要面向开发者、维护者和二次开发者阅读，不是“只改配置即可一键部署全部功能”的傻瓜包。

---

## 1. 项目定位

珞樱并不只是一个“能在群里说话”的 QQ bot。它更接近一个轻量级、多能力、面向具体场景持续生长的 Agent 系统。

它试图解决的问题包括：

- 接入 QQ / Web 等不同输入源
- 区分命令、闲聊、任务型请求
- 在群聊环境中保留用户、会话、回复链等上下文
- 通过 Skill 或子 Agent 处理复杂任务
- 在保证扩展性的同时，让后端结构保持清晰

如果你想做的是：

- 一个可持续迭代的校园场景 Agent
- 一个带命令系统的群聊机器人框架
- 一个适合研究 QQ / Web 双入口统一消息处理模型的项目

那么这个仓库是一个比较合适的起点。

---

## 2. 核心能力概览

### 2.1 指令系统

项目支持通过 `/xxx` 形式触发明确命令，适合高确定性任务。根据当前 README，现有指令包括：

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

### 2.2 自然语言 Agent

主 Agent 采用受控的 ReAct 风格循环，可根据用户请求自动选择 Skill 或直接回复。目前 README 中列出的能力包括：

- 查询武汉天气
- 获取当前时间
- 今日运势
- 联网搜索
- 提醒事项管理
- 备忘录管理
- 群信息 / 群成员信息查询
- 图片理解
- 编程工作区操作

### 2.3 图片理解子 Agent

图片理解能力支持：

- 图片描述
- 图中文字提取
- 截图内容分析
- 多图比较
- 回复消息中的图片理解
- 指定第几张图片分析

### 2.4 编程子 Agent

编程能力围绕“用户脚本工作区”展开，支持：

- 列出用户脚本
- 读取脚本
- 创建脚本
- 覆盖脚本
- 删除脚本
- 运行 Python 脚本
- 将脚本发送到当前会话

### 2.5 数据与运行时能力

项目当前还包含：

- 用户资料 JSON 持久化
- 备忘录按用户存储
- 提醒任务持久化与恢复
- 群启用状态、封禁、复读模式等运行时控制

### 2.6 接入方式

当前已实现：

- QQ OneBot WebSocket 输入输出适配
- 简单 Web API 聊天接口

---

## 3. V2.0.0 相比早期版本的重要变化

V2.0.0 不再只是快照版本的延续，而是把此前多轮后端整理正式落到了主线架构中。根据后端优化方案，当前版本新增或强化了以下能力：

- 引入 `MessageProcessor`，实现“跨会话并发、会话内串行”的消息处理模型
- `AgentService` 去除共享可变状态，并增加统一的 Skill 超时控制与总预算控制
- 新增结构化日志，便于按 `req / thread / msg / user / conv` 追踪问题
- `QuickReplyService` 支持从配置文件读取规则
- 会话记忆增加数量上限，避免无限增长
- `ChatTransport` 进一步收口平台相关能力，例如 mention 格式化
- 引入 `ServiceHub` 统一管理服务注入，减少 magic dict 带来的不透明依赖
- QQ 与 Web 入口进一步统一到新的消息处理链路中

这些变化的直接收益是：

- 慢技能、慢模型不再轻易拖死整个主循环
- 日志更可追踪，排障成本更低
- 新增命令、技能、服务时，结构更稳定
- 平台解耦程度更高，更利于继续扩展

---

## 4. 项目结构

目录结构如下：

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
   │  ├─ services/               # 业务服务层
   │  ├─ message_processor.py    # 消息处理调度
   │  └─ event_handler.py        # 统一事件入口
   │
   ├─ domain/                    # 领域模型
   ├─ infra/                     # 基础设施层
   │  ├─ llm/
   │  ├─ memory/
   │  ├─ repos/
   │  ├─ scheduler/
   │  ├─ transports/
   │  └─ web/
   │
   ├─ ports/                     # 抽象接口层
   ├─ bootstrap.py               # 容器装配入口
   ├─ config.py                  # 配置中心
   ├─ constants.py               # 常量与系统提示词
   ├─ service_hub.py             # 统一服务注入中心
   ├─ logging_setup.py           # 日志初始化
   ├─ main_qq.py                 # QQ 入口
   └─ main_web.py                # Web 入口
```

不同仓库提交之间目录细节可能略有差异，但整体分层思路应保持一致。

---

## 5. 架构概览

### 5.1 分层思路

项目整体可理解为以下几层：

- `domain`：统一消息、上下文、回复等领域对象
- `ports`：抽象接口，定义传输、记忆、存储等边界
- `infra`：接口实现，例如 QQ 适配器、JSON 仓储、内存记忆、Web API
- `application/services`：提醒、备忘录、用户信息、运行时控制等业务服务
- `application/commands`：指令系统
- `application/agent`：主 Agent、Skill 注册与执行
- `application/message_processor.py`：消息并发/串行调度
- `application/event_handler.py`：统一消息入口

### 5.2 启动流程

以 QQ 入口为例，一个典型启动流程大致为：

1. 调用 `build_qq_container()` 构建容器
2. 初始化传输层与运行时服务
3. 恢复提醒任务
4. 注册内置计划事件
5. 启动异步调度器
6. 启动消息接收循环
7. 由 `MessageProcessor` 调度到 `EventHandler`
8. 根据消息类型分发到快捷回复、命令系统或主 Agent

### 5.3 容器装配

当前架构强调“集中装配，分层调用”。常见装配对象包括：

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
- `MessageProcessor`
- `ServiceHub`

这种方式的好处是：

- 依赖关系更清楚
- 更容易替换实现
- 更容易调试与测试
- 更适合继续往后做平台扩展与模块拆分

---

## 6. 消息处理链路

`EventHandler` 是业务入口，`MessageProcessor` 是处理调度入口。当前推荐心智模型如下：

1. 传输层接收平台消息
2. 转成统一 `UniMessage`
3. 交给 `MessageProcessor`
4. `MessageProcessor` 保证：
   - 不同会话可并发处理
   - 同一会话内部保持串行，避免记忆乱序
5. `EventHandler` 继续执行业务判断：
   - 检查上下文
   - 检查封禁与群启用状态
   - 处理特殊平台事件
   - 处理快捷回复
   - 判断是否为命令
   - 判断是否进入复读模式
   - 其他情况交给主 Agent

这条链路决定了你以后新增能力时，应该插在什么位置，以及它会不会影响整条系统链路。

---

## 7. 主 Agent 设计

### 7.1 执行模式

`AgentService` 使用受控 ReAct 风格循环。核心思路是：

- 从当前平台筛出可用 Skill
- 读取当前线程的记忆
- 将用户消息包装为结构化输入
- 要求模型只输出两类 JSON：
  - 调用某个 Skill
  - 给出最终回答
- 将每步 action / observation 写入 scratchpad
- 最终得到 answer，或者触发 fallback

### 7.2 V2.0.0 的新增约束

当前版本建议注意这些后端控制：

- 单个 Skill 有统一超时限制
- 一次 Agent 运行有总预算限制
- 会话记忆有上限，不再无限增长
- 结构化日志可追踪单次请求的执行路径

这些限制并不是“削弱能力”，而是为了让系统在真实群聊环境中更稳定。

---

## 8. Skill 系统

### 8.1 自动注册

`SkillRegistry` 会自动扫描 `luoying_bot.application.agent.skills` 目录下的模块，并注册继承 `BaseSkill` 的合法 Skill。

开发一个新 Skill 的基本步骤通常是：

1. 在 `application/agent/skills/` 下新建 `.py`
2. 继承 `BaseSkill`
3. 定义唯一 `name`
4. 写清楚 `description`
5. 实现 `run(req: SkillRequest) -> SkillResult`
6. 保证模块能被正常 import

### 8.2 当前技能形态

根据现有 README，项目已有的主要 Skill 包括：

- `ReminderSkill`
- `WeatherSkill`
- `WebSearchSkill`
- `MemoSkill`
- `GroupInfoSkill`
- `CodingAgentSkill`
- `ImageAgentSkill`

其中后两个本质上已经不是“简单工具”，而是“Skill 封装子 Agent”。

### 8.3 开发建议

- `description` 要尽量写清楚使用时机和参数格式
- 需要 IO 的 Skill 尽量保持纯异步
- 通用逻辑尽量下沉到 `services`
- 不要在 Skill 里自行重复创建框架本已管理的服务实例

---

## 9. 指令系统

### 9.1 适合什么场景

命令系统适合：

- 参数格式明确
- 行为高度确定
- 不希望依赖模型理解
- 希望响应更快更稳定

例如：

- 绑定资料
- 更新资料
- 管理员操作
- 模式开关
- 清空会话记忆
- 查看版本

### 9.2 自动注册

命令系统与 Skill 类似，`CommandDispatcher` 会自动扫描 `luoying_bot.application.commands` 目录中的命令类并注册。

### 9.3 当前架构建议

在 V2.0.0 中，命令与 Skill 建议统一使用 `ServiceHub` 获取依赖，而不要继续散落使用不透明的 magic dict。这会让：

- IDE 类型提示更友好
- 重构更安全
- 依赖关系更明确

---

## 10. 图片理解子 Agent

图片理解是当前比较有特色的一块能力。

### 10.1 支持来源

系统会尝试收集：

- 当前消息中的图片
- 用户回复消息中的图片

当前只展开一层 reply，不会无限递归展开。

### 10.2 支持能力

图片子 Agent 目前可覆盖：

- 图片描述
- 提取文字
- 多图比较
- 回答与图片有关的问题

### 10.3 实现思路

主 Agent 不直接看图，而是：

1. 判断需要调用 `image_agent`
2. `ImageAgentSkill` 收集图片
3. 由平台接口拉取图片资源并做必要处理
4. 再把任务交给图片子 Agent

这让图片相关复杂度不会污染主 Agent 的主链路。

---

## 11. 编程子 Agent

`CodingAgentSkill` 面向“用户自己的脚本工作区”。

### 11.1 工作区模型

每个用户拥有独立脚本目录：

```text
data/scripts/<user_id>/
```

### 11.2 支持操作

典型操作包括：

- `list_scripts`
- `read_script`
- `create_script`
- `overwrite_script`
- `delete_script`
- `run_python_script`
- `send_script`

### 11.3 安全边界

脚本工作区服务会进行路径约束：

- 不允许绝对路径
- 不允许 `..`
- 不允许越界到用户目录之外

当前边界仍包括：

- 仅直接运行 `.py`
- 不支持任意 shell 命令
- 不支持访问系统敏感资源
- 默认不以“整机控制器”身份运行

---

## 12. 数据存储与运行时数据

当前项目仍以轻量 JSON 存储为主，适合中小规模使用与开发期调试。

常见数据位置包括：

- `data/userdatabase.json`：用户资料
- `data/reminders.json`：提醒事项
- `data/quick_replies.json`：快捷回复规则
- `data/memo/`：用户备忘录
- `data/scripts/<user_id>/`：用户脚本工作区

### 12.1 优点

- 易读
- 易调试
- 无需数据库依赖
- 对小团队和单机部署友好

### 12.2 局限

- 并发能力一般
- 原子性有限
- 不适合大规模场景
- 长期来看适合迁移到 SQLite / PostgreSQL / KV 存储

---

## 13. 提醒与调度系统

提醒能力当前由以下部分协作完成：

- `ReminderService`
- `JsonReminderRepo`
- `AsyncScheduler`
- `BuiltinScheduleService`

### 13.1 运行特性

系统启动时通常会：

- 从 `reminders.json` 恢复任务
- 注册内置计划事件
- 启动调度器

### 13.2 内置计划事件

当前内置逻辑包括：

- 每日早安 / 天气播报
- 每日睡觉提醒

### 13.3 V2.0.0 的改进点

你应优先把所有计划事件统一收口到调度服务中，而不是散落在入口脚本里。这样：

- 更好维护
- 更容易观察调度状态
- 更便于以后加入 misfire 策略、执行状态记录、运行日志等增强能力

---

## 14. QQ 传输层

`QQWsTransport` 是当前 QQ 平台适配器。

它负责：

- 连接 OneBot WebSocket
- 收发原始事件
- 调用 OneBot action
- 将 QQ 消息转换为统一 `UniMessage`
- 处理 CQ 码 / 数组消息段
- 拉取被回复消息
- 下载图片
- 发送文本
- 发送文件
- 执行戳一戳等平台动作

### 14.1 当前架构方向

V2.0.0 更强调“平台能力下沉”。业务层不应到处散落 QQ 语义，而应尽量通过 transport 暴露统一能力，例如：

- mention 格式化
- 平台特定消息能力
- 文件发送
- 平台动作

这会让后续接 Web、其他 IM 平台时轻松很多。

---

## 15. Web 入口

`main_web.py` 与 `infra/web/api.py` 提供了一个简单 Web 接口，用于调试与后续扩展。

当前接口形态可理解为：

- `POST /chat`

典型请求体：

```json
{
  "session_id": "test-session",
  "user_id": "123456",
  "user_name": "网页用户",
  "text": "你好"
}
```

典型返回体：

```json
{
  "reply": "你好呀"
}
```

在当前版本里，Web 入口更适合：

- 本地调试 Agent
- 做前端页面前的接口预留
- 测试统一消息处理模型

---

## 16. 环境要求

建议环境：

- Python 3.11+
- Windows / Linux
- 可访问对应 LLM API
- 若启用 QQ 机器人，需要 OneBot WebSocket 服务端

当前 README 提到的主要依赖包括：

- fastapi
- uvicorn
- websockets
- httpx
- pydantic
- Pillow
- python-dotenv
- langchain
- langchain-openai

建议以仓库中的 `requirements.txt` 为准。

---

## 17. 安装

建议先创建虚拟环境：

```bash
python -m venv .venv
```

激活后安装依赖：

```bash
pip install -r requirements.txt
```

如果你使用 conda，也可以自行按环境需求创建等价环境。

---

## 18. 配置

项目通过 `.env` 读取配置，统一入口位于：

```python
src/luoying_bot/config.py
```

### 18.1 基础配置

```env
WS_URL=ws://127.0.0.1:3001
BOT_QQ=3949843218
BOT_NAME=珞樱
VERSION=V2.0.0
HELP=
LOG=
```

### 18.2 主模型配置

```env
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_API_KEY=
OPENAI_MODEL=deepseek-chat
LLM_TEMPERATURE=1.0
```

### 18.3 编程子 Agent 配置

```env
CODER_BASE_URL=https://api.deepseek.com
CODER_API_KEY=
CODER_MODEL=deepseek-reasoner
CODER_TEMPERATURE=0.2
```

### 18.4 图片能力配置

```env
IMAGE_BASE_URL=
IMAGE_API_KEY=
IMAGE_MODEL=
```

### 18.5 天气 / 搜索

```env
QWEATHER_API_KEY=
WEATHER_BASE_URL=https://pn6yvyt6je.re.qweatherapi.com/v7/weather/now
TAVILY_API_KEY=
```

### 18.6 数据目录

```env
DATA_DIR=./data
MEMO_DIR=./data/memo
QUICK_REPLY_FILE=./data/quick_replies.json
USER_DB_FILE=./data/userdatabase.json
REMINDER_DB_FILE=./data/reminders.json
SCRIPT_WORKSPACE_DIR=./data/scripts
```

### 18.7 运行限制

在完成后端优化后，建议保留或补充这类限制项：

```env
PYTHON_SCRIPT_TIMEOUT_SEC=15
SCRIPT_SEND_CHUNK_SIZE=1200
SCRIPT_MAX_OUTPUT_CHARS=12000
MEMORY_MAX_MESSAGES_PER_THREAD=80
AGENT_SKILL_TIMEOUT_SEC=360
AGENT_TOTAL_TIMEOUT_SEC=6000
MAX_CONCURRENT_MESSAGE_TASKS=200
```

### 18.8 权限 / 群开关 / 触发前缀

```env
OPS=
SPECIFIC_GROUP_IDS=
TRIGGER_PREFIX=/,!
```

---

## 19. 启动方式

### 19.1 启动 QQ 机器人

```bash
cd src
python -m luoying_bot.main_qq
```

### 19.2 启动 Web API

```bash
uvicorn src.luoying_bot.main_web:create_app --factory --host 0.0.0.0 --port 8000
```

如果你的模块路径组织或启动脚本不同，可按实际仓库结构调整。

---

## 20. 开发指南

### 20.1 新增一个 Command

基本步骤：

1. 在 `application/commands/` 下新建文件
2. 定义一个继承 `BaseCommand` 的类
3. 设置命令名
4. 实现 `validate()` 与 `execute()`
5. 启动后由 `CommandDispatcher` 自动注册

适合场景：

- 参数明确
- 行为确定
- 希望响应稳定快速

### 20.2 新增一个 Skill

基本步骤：

1. 在 `application/agent/skills/` 下新建模块
2. 继承 `BaseSkill`
3. 定义唯一 `name`
4. 写清楚 `description`
5. 实现 `run(req: SkillRequest) -> SkillResult`

建议：

- `description` 写清楚触发时机与参数格式
- IO 逻辑尽量使用异步实现
- 通用业务尽量放进 `services`
- Skill 尽量只管业务，而不是顺手承担基础设施职责

### 20.3 新增 Quick Reply

快捷回复适合：

- 高频固定问候
- 简短关键词响应
- 不需要进入主 Agent 的轻量交互

当前推荐把规则维护在：

```text
data/quick_replies.json
```

一条典型规则通常形如：

```json
{
  "trigger": "早",
  "reply": "早呀～"
}
```

### 20.4 新增业务服务

当一个能力已经不只是“简单查一下”，建议先封装到 `application/services/`，再由命令或 Skill 调用，而不是把业务代码堆在命令类 / Skill 类中。

### 20.5 替换存储实现

当前项目默认是 JSON 实现。
如果未来迁移数据库，建议优先保持 `services` 层接口稳定，再去替换 `infra/repos` 层。

### 20.6 替换模型供应商

当前 LLM 接入通常位于：

- `infra/llm/openai_chat.py`
- 各子 Agent 内部的模型初始化逻辑

如果要替换模型供应商：

- 主 Agent：优先改统一 LLM 适配层
- 子 Agent：优先改各 Skill 内部对应初始化逻辑

---

## 21. 已知特点与注意事项

- 当前系统提示词仍然会显著影响主 Agent 与子 Agent 输出风格
- 默认记忆实现如果仍使用内存型方案，重启后会丢失
- JSON 存储适合轻量场景，不适合高并发大规模部署
- Web 端目前更接近调试入口，而不是完整产品形态
- 图片 / 回复链能力会受到平台协议实现质量影响

V2.0.0 不再是快照版，但它依然是一个持续演进中的工程项目，而不是“已经彻底平台无关、完全产品化、完整安全审计完成”的通用框架。

---

## 22. 推荐阅读顺序

如果你第一次接手这个项目，推荐按以下顺序阅读代码：

1. `config.py`
2. `main_qq.py`
3. `bootstrap.py`
4. `application/message_processor.py`
5. `application/event_handler.py`
6. `application/commands/`
7. `application/agent/agent_service.py`
8. `application/agent/skills/`
9. `application/services/`
10. `infra/transports/qq_ws_transport.py`

这样会更快建立整体心智模型。

---

## 23. 致谢

感谢所有参与需求提出、测试、催更、赞助、使用与反馈的人。

一个群聊机器人能走到 Agent 架构这一步，从来不是“把模型接上就完了”，而是无数边界问题、脏活累活、异常情况、平台限制和真实使用反馈一点点磨出来的。

如果你正在继续维护它，也欢迎你把它做得更稳、更清晰、更好扩展。
