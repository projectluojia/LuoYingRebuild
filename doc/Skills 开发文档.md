# Skills 开发文档

## 快速开始：开发一个新的Skill

珞樱提供了较为方便的扩展机制，你可以通过新增 Skill 的方式，为系统添加新的能力。

开发一个新的 Skill，通常分为以下几个步骤：

1. 在指定目录下新建 Skill 文件
2. 导入必要模块
3. 定义 Skill 类及其基本信息
4. 实现 `run` 方法
5. 让系统在启动时自动注册该 Skill

下面按顺序说明。

### 新建文件

请先在以下目录中新建一个 Python 文件：

```
./luoying_bot/application/agent/skills/your_skill.py
```

后续所有 Skill 开发代码都将在这个文件中完成。

需要注意的是：

- 所有 Skill **必须**放置在 `./luoying_bot/application/agent/skills/` 目录下
- 如果不放在该目录中，系统将无法正常完成 Skill 的自动发现与指令注入

### 导入必要模块

在 `your_skill.py` 中，首先导入以下内容：

```python
from __future__ import annotations
from luoying_bot.application.agent.skill_base import BaseSkill, SkillRequest, SkillResult
from luoying_bot.domain.context import Platform
```

其中：

- `from __future__ import annotations`
  不是必须的，但**强烈建议保留**。这样可以更方便地使用尚未定义的类型名，也能减少部分类型注解带来的问题。
- `BaseSkill`
  Skill 的基类。你编写的 Skill **必须继承**它。
- `SkillRequest`
  表示 Agent 调用 Skill 时传入的请求对象。
- `SkillResult`
  表示 Skill 执行后返回给 Agent 的结果对象。
- `Platform`
  平台枚举类，用于声明当前 Skill 支持哪些平台。

### 定义新的 Skill 类

首先，定义一个新的 Skill 类：

```python
class YourSkill(BaseSkill):
    pass
```

类名本身不会直接暴露给 Agent，因此不是系统运行的关键字段。
不过为了保证代码的可读性与可维护性，仍然**强烈建议**：

- 使用有明确意义的英文命名
- 使用**大驼峰命名法**

这个类**必须继承自 `BaseSkill`**，否则系统无法将其识别为合法 Skill。

接下来，你需要在类中实现以下几个**类属性**：

```python
class YourSkill(BaseSkill):
    name = "your_skill"
    platform = [Platform.QQ, Platform.WEB]
    description = (
        "这是一个XXX Skill"
        "功能主要是……"
        "在XXX的时机调用"
        "payload必须带有……"
    )
```

这些字段的含义如下：

- `name`
  一个**字符串**，表示 Skill 的唯一标识符。
  该值在注册与管理 Skill 时会被使用，因此必须保证唯一，且不能为空。
- `platform`
  一个由 `Platform` 枚举值组成的**列表**，表示该 Skill 在哪些平台下可用。
  自动注册时，系统会根据当前平台与这个列表动态决定是否加载该 Skill。
- `description`
  一个**字符串**，用于向 Agent 描述该 Skill 的用途、适用时机以及 `payload` 格式。
  这个字段非常重要，因为 Agent 会参考它来判断是否调用该 Skill。
  建议做到：
  - 不要过长
  - 但必须足够清晰
  - 尤其要写明 `payload` 的字段格式与含义

### 实现一个简单的 `run` 函数

每个 Skill 都必须实现一个抽象方法：`async def run(...)`。
它是 Skill 的核心运行入口。

示例代码如下：

```python
from __future__ import annotations
from luoying_bot.application.agent.skill_base import BaseSkill, SkillRequest, SkillResult
from luoying_bot.domain.context import Platform

class YourSkill(BaseSkill):
    name = "add_skill"
    platform = [Platform.QQ,Platform.WEB]
    description = (
        "这是一个大数加法 Skill"
        "功能主要是大数加法"
        "在需要大数计算的时机调用"
        "payload必须带有num_1:int = [第一个数字] num_2:int = [第二个数字]"
    )

    async def run(self, req: SkillRequest) -> SkillResult:
        payload = req.payload
        num_1 = payload.get('num_1')
        num_2 = payload.get('num_2')

        if not num_1 or not num_2:
            return SkillResult(text="出现错误，数字不能为空")

        if (not isinstance(num_1, int | float)) or (not isinstance(num_2, int | float)):
            return SkillResult(text="出现错误，输入不是数字")

        return SkillResult(text=f"两个数字的和为：{num_1 + num_2}")
```

从这个例子中可以看到：

- Agent 传给 Skill 的参数可以直接通过 `req.payload` 获取
- `payload` 通常是一个字典
- 你需要自行从中解析参数、校验参数，并完成具体业务逻辑
- 最终**必须返回一个 `SkillResult` 对象**

另外，示例中的 `description` 已经对 `payload` 做了明确说明，这是一种非常推荐的写法。
只要你的 `description` 写得清楚，大多数模型都能较稳定地构造出正确的调用参数。

## Skill 相关类详解

### SkillRequest

实现如下：

```python
@dataclass(slots=True)
class SkillRequest:
    message: UniMessage
    context: ChatContext
    payload: Dict[str, Any] = field(default_factory=dict)
```

`SkillRequest` 是一个数据类，表示一次 Skill 调用时的完整请求信息。

它包含以下字段：

- `message`
  本轮对话中用户发送的消息，类型为 `UniMessage`。
  如果你的 Skill 需要读取用户原始消息内容，可以使用这个对象。
  但**不要修改它**，因为它可能是引用语义。
- `context`
  本轮对话的上下文信息，类型为 `ChatContext`。
  可以用于获取平台、会话、用户等相关上下文数据，从而提供更好的服务。
- `payload`
  Agent 直接传递给 Skill 的参数，通常是一个字典。
  一般情况下，你需要从这里读取 Skill 所需的结构化输入。
  如果你已经在 `description` 中清晰说明了 `payload` 格式，那么模型大多数时候都能正确构造它。

### SkillResult

实现如下：

```python
@dataclass(slots=True)
class SkillResult:
    text: str
    data: dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

`SkillResult` 是 Skill 的返回结果类型，用于把执行结果交还给 Agent。

字段说明如下：

- `text`
  纯文本结果，会直接展示给大模型。
  这是最常用、也最推荐返回的字段。
- `data`
  结构化数据。如果返回了这个字段，Agent 将看到其 JSON 化后的内容。
  适合在需要返回机器可解析信息时使用。
- `metadata`
  预留字段，通常暂时不需要使用。即使返回也不会影响当前系统功能。

一般来说：

- `text` 和 `data` 可以只返回其一
- 也可以同时返回
- 但**强烈建议至少返回 `text`**

### BaseSkill

实现如下：

```python
class BaseSkill(ABC):
    name: str = ''
    description: str = ''
    platform = []

    def __init__(self, services: dict):
        self.services = services

    @abstractmethod
    async def run(self, req: SkillRequest) -> SkillResult:
        ...
```

`BaseSkill` 是所有 Skill 的基类。任何自定义 Skill 都必须继承它。

#### 类属性

- `name: str`
  Skill 的唯一标识符，必须为**非空字符串**。
  系统会在 Skill 注册、查找和管理时使用该名称，因此必须保证唯一。
- `description: str`
  Skill 的功能描述，必须为**非空字符串**。
  Agent 在决定调用哪个 Skill 时，会参考这个描述。
  建议使用简洁、明确的语言，写清楚：
  - Skill 的功能
  - 适用时机
  - `payload` 的格式要求
- `platform`
  一个由 `Platform` 枚举值组成的列表，用于声明该 Skill 在哪些平台可用。
  默认值为空列表。系统会根据当前运行平台与该字段动态过滤可用 Skill。

#### 初始化方法

```python
def __init__(self, services: dict):
```

参数说明：

- `services`
  一个字典，里面存放了运行时注入的各类服务实例。
  这些服务通常已经由应用框架统一完成初始化和管理，例如：
  - 用户服务
  - 提醒服务
  - 备忘录服务
  - 其他公共工具服务

在 Skill 内部，你可以通过 `self.services` 获取这些服务，以实现更复杂的功能，例如：

- 数据持久化
- 使用脚本工作区
- 访问其他系统模块

常见使用方式如下：

```python
service = self.services.get("service_name")
```

通常情况下，开发者**不需要重写 `__init__` 方法**，直接在 `run` 中使用 `self.services` 即可。

#### 抽象方法

```python
@abstractmethod
async def run(self, req: SkillRequest) -> SkillResult:
```

这是每个 Skill **必须实现的核心方法**，也是 Skill 的业务逻辑入口。

说明如下：

- **参数**：`req: SkillRequest`
  表示本次调用的请求信息，包含用户消息、上下文和 Agent 传入参数等内容。
- **返回值**：`SkillResult`
  必须返回一个 `SkillResult` 实例，表示本次 Skill 执行结果。
- **异步要求**：
  该方法必须是 `async` 方法，以支持非阻塞 IO 操作。

在 `run` 方法中，你通常需要完成以下工作：

1. 从 `req.payload` 中提取参数
2. 对参数进行必要校验
3. 执行业务逻辑（如计算、查询、处理、调用外部服务等）
4. 构造并返回 `SkillResult`

通常建议：

- 至少返回 `text`
- 需要结构化数据时再额外返回 `data`

#### 自动注册机制

任何继承自 `BaseSkill`，并且正确定义了 `name` 与 `description` 的类，在应用启动时都会被框架自动发现并注册，无需手动导入。

注册时，系统会结合：

- 当前运行平台
- Skill 的 `platform` 属性

进行匹配。只有匹配成功的 Skill，才会被实际加载到系统中。

## Service 使用

`services` 是 Skill 与系统其他能力交互的重要入口。

在运行时，框架会把已经初始化好的服务对象统一注入到 Skill 中，开发者可以在 `run` 方法里通过 `self.services` 获取对应服务。

一个常见的使用方式如下：

```python
async def run(self, req: SkillRequest) -> SkillResult:
    user_service = self.services.get("user_service")
    ...
```

使用建议：

- 优先通过 `self.services.get(...)` 获取服务，避免直接假设某个服务一定存在
- 对获取失败的情况做好判空处理
- 不建议在 Skill 内部重复创建本应由框架统一管理的服务实例
- Skill 应尽量只关注自身业务逻辑，把通用能力交给 `services` 提供

关于 Service 的详细信息，请查看 `Service创建与使用.md`