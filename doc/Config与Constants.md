# Config 与 Constants 开发文档

## 快速开始：了解配置与常量

在珞樱项目中，`config.py` 与 `constants.py` 分别承担两类不同职责：

- `config.py`：负责**集中读取运行配置**，通常来自环境变量 `.env`
- `constants.py`：负责存放**项目内固定不变的常量**，例如提示词、固定文本、预设列表等

二者的区别可以简单理解为：

- **Config 是“运行时可改”的**
- **Constants 是“代码里约定好的”**

---

## 一、config.py 详解

`config.py` 的核心作用，是把分散的环境变量统一读取出来，并封装成一个可以直接使用的设置对象。

### 文件结构

当前 `config.py` 主要包含三部分：

1. 导入依赖
2. 定义辅助函数 `_split_csv`
3. 定义 `Settings` 数据类，并在文件末尾实例化全局 `settings`

---

### 导入与初始化

文件开头如下：

```python
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
from dotenv import load_dotenv
load_dotenv()
```

这里做了几件事：

- `os.getenv(...)` 用于读取环境变量
- `dataclass` 用于把配置项组织成结构清晰的类
- `field(default_factory=...)` 用于处理列表类型默认值
- `Path` 用于统一表示文件路径
- `load_dotenv()` 会在程序启动时自动加载 `.env` 中的配置，使这些配置可以通过环境变量被读取到。

---

### `_split_csv` 辅助函数

实现如下：

```python
def _split_csv(value: str) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(',') if item.strip()]
```

它的作用是：

- 将形如 `"123,456,789"` 的字符串
- 转换为 `[`"123"`, `"456"`, `"789"`]`

这个函数主要用于读取环境变量中的“列表配置”，例如：

- 管理员列表 `OPS`
- 指定群号列表 `SPECIFIC_GROUP_IDS`
- 触发前缀列表 `TRIGGER_PREFIX`

例如：

```env
OPS=10001,10002,10003
```

会被解析成：

```python
["10001", "10002", "10003"]
```

该函数还能自动去掉多余空格，并忽略空项。

---

### `Settings` 数据类

项目使用了一个带 `slots=True` 的数据类：

```python
@dataclass(slots=True)
class Settings:
    ...
```

这表示：

- 这是一个专门用于承载配置的类
- 每个字段都对应一个配置项
- `slots=True` 可以减少实例的属性开销，也能避免随意动态添加新属性。

你可以把它理解为：**整个项目的统一配置入口**。

---

### 配置项分类说明

#### 1. WebSocket 与基础机器人信息

```python
ws_url: str = os.getenv('WS_URL', 'ws://127.0.0.1:3001')
ws_token: str = os.getenv('WS_TOKEN', '')
HELP: str = os.getenv('HELP', '拉取链接失败')
LOG: str = os.getenv('LOG', '拉取链接失败')
version: str = os.getenv('VERSION','unknown')
bot_qq: str = os.getenv('BOT_QQ', '3949843218')
bot_name: str = os.getenv('BOT_NAME', '珞樱')
```

这些配置的含义通常如下：

- `ws_url`：机器人连接的 WebSocket 地址
- `ws_token`：WebSocket 鉴权令牌
- `HELP`：帮助文档链接或帮助内容入口
- `LOG`：日志链接或日志入口
- `version`：当前程序版本号
- `bot_qq`：机器人 QQ 号
- `bot_name`：机器人名称。

其中：

- 如果环境变量不存在，就会使用右侧默认值
- 因此这套配置既支持开发环境直接运行，也支持部署时通过 `.env` 覆盖

---

#### 2. 主模型配置

```python
openai_base_url: str = os.getenv('OPENAI_BASE_URL', 'https://api.deepseek.com')
openai_api_key: str = os.getenv('OPENAI_API_KEY', '')
openai_model: str = os.getenv('OPENAI_MODEL', 'deepseek-chat')
llm_temperature: float = float(os.getenv('LLM_TEMPERATURE', '1.0'))
```

这些配置控制主对话模型：

- `openai_base_url`：模型服务接口地址
- `openai_api_key`：调用模型所需密钥
- `openai_model`：模型名称
- `llm_temperature`：生成温度，越高越发散，越低越稳定。

---

#### 3. 编程子 Agent 配置

```python
coding_base_url: str = os.getenv('CODER_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
coding_api_key: str = os.getenv('CODER_API_KEY', '')
coding_model: str = os.getenv('CODER_MODEL', 'qwen3-max')
coding_temperature: float = float(os.getenv('CODER_TEMPERATURE', '0.2'))
```

这些配置用于编程相关模型或子 Agent：

- `coding_base_url`：编程模型服务地址
- `coding_api_key`：编程模型密钥
- `coding_model`：编程模型名称
- `coding_temperature`：编程模型温度，一般设得更低，以提高稳定性。

---

#### 4. 图片模型配置

```python
image_base_url: str = os.getenv("IMAGE_BASE_URL", "")
image_api_key: str = os.getenv("IMAGE_API_KEY", "")
image_model: str = os.getenv("IMAGE_MODEL", "")
```

这些配置用于图片理解或图片相关模型：

- `image_base_url`：图片模型服务地址
- `image_api_key`：图片模型密钥
- `image_model`：图片模型名称。

---

#### 5. 天气与搜索服务配置

```python
qweather_api_key: str = os.getenv('QWEATHER_API_KEY', '')
weather_base_url: str = os.getenv('WEATHER_BASE_URL', 'https://pn6yvyt6je.re.qweatherapi.com/v7/weather/now')
tavily_api_key: str = os.getenv('TAVILY_API_KEY', '')
```

这些配置通常用于外部能力接入：

- `qweather_api_key`：和风天气 API 密钥
- `weather_base_url`：天气接口地址
- `tavily_api_key`：联网搜索服务密钥。

---

#### 6. 数据文件与目录配置

```python
data_dir: Path = Path(os.getenv('DATA_DIR', './data'))
memo_dir: Path = Path(os.getenv('MEMO_DIR', './data/memo'))
quick_reply_file: Path = Path(os.getenv('QUICK_REPLY_FILE', './data/quick_replies.json'))
user_db_file: Path = Path(os.getenv('USER_DB_FILE', './data/userdatabase.json'))
reminder_db_file: Path = Path(os.getenv('REMINDER_DB_FILE', './data/reminders.json'))
```

这些配置用于指定本地持久化文件与目录：

- `data_dir`：项目数据根目录
- `memo_dir`：备忘录目录
- `quick_reply_file`：快捷回复数据文件
- `user_db_file`：用户数据库文件
- `reminder_db_file`：提醒事项数据库文件。

注意：这些字段使用 `Path` 而不是普通字符串，这样在后续代码中做路径拼接会更方便、更安全。

---

#### 7. 脚本工作区配置

```python
script_workspace_dir: Path = Path(os.getenv('SCRIPT_WORKSPACE_DIR', './data/scripts'))
python_script_timeout_sec: int = int(os.getenv('PYTHON_SCRIPT_TIMEOUT_SEC', '15'))
script_send_chunk_size: int = int(os.getenv('SCRIPT_SEND_CHUNK_SIZE', '1200'))
script_max_output_chars: int = int(os.getenv('SCRIPT_MAX_OUTPUT_CHARS', '12000'))
```

这些配置与脚本子 Agent 有关：

- `script_workspace_dir`：脚本工作区目录
- `python_script_timeout_sec`：Python 脚本运行超时时间
- `script_send_chunk_size`：脚本发送时的分块大小
- `script_max_output_chars`：脚本运行输出最大字符数。

这些限制通常是出于：

- 安全考虑
- 消息长度限制
- 防止脚本运行输出过长导致刷屏

---

#### 8. 列表型配置

```python
ops: List[str] = field(default_factory=lambda: _split_csv(os.getenv('OPS', '')))
specific_group_ids: List[str] = field(default_factory=lambda: _split_csv(os.getenv('SPECIFIC_GROUP_IDS', '')))
trigger_prefix: List[str] = field(default_factory=lambda: _split_csv(os.getenv('TRIGGER_PREFIX', '/,!')))
```

这些配置是列表，而不是单个字符串：

- `ops`：管理员用户 ID 列表
- `specific_group_ids`：启用机器人的指定群号列表
- `trigger_prefix`：命令触发前缀列表，例如 `/` 和 `!`。实际上是一个保留字段。

这里使用 `field(default_factory=...)` 的原因是：

- 列表属于可变对象
- 若直接写 `[]` 作为默认值，可能带来共享默认值问题
- 因此必须使用 `default_factory` 动态生成。

---

### 全局实例 `settings`

文件末尾还有：

```python
settings = Settings()
```

这表示程序启动时会立即创建一个全局配置对象。其他模块只需要：

```python
from luoying_bot.config import settings
```

就可以直接读取配置，而不需要重复调用 `os.getenv(...)`。

这也是当前项目推荐的配置访问方式。

---

## 二、constants.py 详解

`constants.py` 的作用，是集中存放那些**不会频繁变化、且在程序各处都会被复用的固定内容**。

它的内容大致可以分为以下几类：

1. 运势相关常量
2. 通知与快捷回复常量
3. 系统提示词常量
4. 子 Agent 提示词常量
5. 风控词配置

---

### 1. 运势相关常量

#### FORTUNE_LEVELS

```python
FORTUNE_LEVELS = [
    "大凶",
    ...,
    "大吉"
]
```

这是一个运势等级列表，按从凶到吉排列。可用于：

- 每日运势结果映射
- 随机抽取运势等级
- 根据下标生成文案。

#### FORTUNE_DO

```python
FORTUNE_DO = {
    1: {"title": "发朋友圈", "do": "分享是种美德", "not_do": "忘记屏蔽同事"},
    ...
}
```

这是一个字典，键是编号，值是一个三字段对象：

- `title`：事项标题
- `do`：适宜做这件事时的解释
- `not_do`：不宜做这件事时的解释。

它通常用于“宜/忌”功能的文案拼装。

---

### 2. 通知与快捷回复常量

#### NOTIFYS

```python
NOTIFYS = [
    "🌸",
    "(轻轻戳回去)",
    ...
]
```

这是一个通知回复候选列表，用于：

- 被戳一戳时的随机回复
- 简短互动消息
- 增强角色感。

#### quick_replies

```python
quick_replies = [
  {"trigger": "早", "reply": "..."},
  ...
]
```

这是一个快捷回复表，每项通常包含：

- `trigger`：触发词
- `reply`：回复内容。

适用于：

- 高频固定问候
- 简单关键词响应
- 不需要进入主 Agent 的快速交互

---

### 3. 平台系统提示词常量

#### QQ_GROUP_SYSTEM_PROMPT

这是 QQ 群聊场景下的系统提示词，主要定义了：

- 角色身份
- 性格设定
- 输出风格
- 行为限制
- 特定敏感内容的拒答要求
- 图片场景下优先调用 `image_agent` skill 的策略。

它的作用可以理解为：

**给主 Agent 规定“你是谁、你怎么说话、你不能做什么”。**

#### WEB_SYSTEM_PROMPT

这个常量和上面的结构几乎一致，但明确说明了运行平台是 WEB 端。

也就是说：

- QQ 端和 Web 端共用大部分角色设定
- 但会在平台说明、输入来源等细节上做区分

这种做法可以避免把所有平台逻辑混在一个提示词里。

---

### 4. Agent 行为控制提示词

#### REACT_INSTRUCTION

这是一个非常关键的常量，用来约束主 Agent 的 ReAct 行为。它明确规定：

- 是否需要调用技能
- 每次只能做一件事
- 只能输出两种 JSON 结构之一
- 有足够信息时必须直接回答。

它本质上是：

**给模型的“行动协议”**。

如果没有这类常量，模型就更容易输出杂乱内容，或者在工具调用与最终回答之间格式失控。

---

### 5. 子 Agent 提示词常量

当前文件中定义了多个子 Agent 专用提示词：

#### CODING_AGENT_SYSTEM_PROMPT

用于脚本工作区管理子 Agent，重点约束：

- 只能在用户工作区内操作文件
- 不能执行任意 shell 命令
- 不能访问系统敏感资源
- 危险代码、恶意代码必须拒绝
- 成功或失败时要清晰说明结果。

#### IMAGE_AGENT_SYSTEM_PROMPT

用于图片理解子 Agent，重点约束：

- 多图要整体处理
- 必须基于工具结果作答
- 看不清要明确说明
- 用户问题不同，对应优先调用不同图片工具。

#### ARXIV_AGENT_SYSTEM_PROMPT

用于 arXiv 检索子 Agent，重点约束：

- 优先通过工具查询论文
- 提到 arXiv ID 时优先精确检索
- 用户要求最新论文时要注意排序字段
- 总结结果时要包含标题、作者、发布时间等关键信息。

然而，目前实际上尚未实现 arXiv 子 Agent 功能。故而这实际上是保留项。

---

### 6. 风控配置

#### risk_control

```python
risk_control = [
   {"content":"😅","level":"sensitive"}, 
   {"content":"pornhub","level":"danger"},
   ...
]
```

这是一个简单的风控词表，每项一般包含：

- `content`：目标内容
- `level`：风险等级。

它可以用于：

- 输出拦截
- 风险审计
- 内容分级处理

---

## 三、Config 与 Constants 的区别

### Config 适合放什么？

适合放：

- API Key
- URL
- 模型名
- 文件路径
- 运行参数
- 管理员列表
- 群号白名单

这些内容的特点是：

- 不同部署环境可能不同
- 未来很可能修改
- 适合通过 `.env` 覆盖

### Constants 适合放什么？

适合放：

- 固定文案
- 固定提示词
- 枚举列表
- 风控词表
- 角色设定
- 预设回复模板

这些内容的特点是：

- 更偏“程序内部约定”
- 不是部署环境差异
- 一般直接写在代码里

---

## 四、推荐使用方式

### 读取配置

推荐这样使用配置：

```python
from luoying_bot.config import settings
```

不要在业务代码中到处手写：

```python
os.getenv(...)
```

否则会导致：

- 配置来源分散
- 默认值不统一
- 后期维护困难

---

### 读取常量

推荐这样使用常量：

```python
from luoying_bot.constants import QQ_GROUP_SYSTEM_PROMPT, FORTUNE_LEVELS
```

不要在业务逻辑中到处复制提示词或固定文案。

否则容易导致：

- 同一份提示词出现多个版本
- 文案修改时漏改
- 项目结构混乱

---

## 五、开发建议

### 关于 config.py

建议保持以下原则：

1. 所有环境变量统一在这里读取
2. 所有默认值统一在这里声明
3. 路径尽量使用 `Path`
4. 列表配置优先通过辅助函数解析
5. 业务模块只读取 `settings`，不要重复解析环境变量

### 关于 constants.py

建议保持以下原则：

1. 只放固定内容，不放运行逻辑
2. 提示词按用途分块管理
3. 常量命名尽量清晰统一
4. 若内容很长，可考虑按模块拆分，例如：
   - `prompts.py`
   - `fortune_constants.py`
   - `risk_control_constants.py`

当 `constants.py` 变得很长时，拆分文件通常会更清晰。
