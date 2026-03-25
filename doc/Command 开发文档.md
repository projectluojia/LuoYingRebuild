# Command 指令开发文档

## 快速开始：创建一个简单的指令

为珞樱添加新指令是十分方便的。

### 新建文件

请先在以下目录中新建一个 Python 文件：

```
./luoying_bot/application/commands/your_command.py
```

后续所有 Command 开发代码都将在这个文件中完成。

需要注意的是：

- 所有 Command **必须**放置在 `./luoying_bot/application/commands/` 目录下
- 如果不放在该目录中，系统将无法正常完成 Command 的自动发现与指令注入

### 导入必要模块

在 `your_command.py` 中，首先导入以下内容：

```python
from __future__ import annotations
from luoying_bot.application.commands.base import BaseCommand
from luoying_bot.domain.result import Reply
```

其中：

- `from __future__ import annotations` 不是必须的，但**强烈建议保留**。这样可以更方便地使用尚未定义的类型名，也能减少部分类型注解带来的问题。
- `BaseCommand` Command 的基类。你编写的 Command **必须继承**它
- `Reply` 表示 Command 执行后返回的结果对象。

### 定义新的 Command 类

首先，定义一个新的 Command 类：

```python
class YourCommand(BaseCommand):
    pass
```

类名本身不会直接暴露给 Agent，因此不是系统运行的关键字段。

不过为了保证代码的可读性与可维护性，仍然**强烈建议**：

- 使用有明确意义的英文命名
- 使用***大驼峰命名法**

这个类**必须继承自 `BaseCommand`**，否则系统无法将其识别为合法 Command。

接下来，你必须在类中实现以下这个**类属性**：

```python
class YourCommand(BaseCommand):
    name = "\six_seven"
```

这个 `name` 字段是一个**字符串**，含义是指令的**触发名称**。例如，如果按上面的例子定义了触发名称，那么你就可以在群聊中通过：`@珞樱 \six_seven` 来触发这个指令。

### 空实现 `validate` 函数

无论你的指令是否需要参数，你都必须实现一个 `async def validate(...)` 函数。

这个函数的用途是验证参数格式是否符合**你自己设定**的规则。

如果你的指令不需要参数——就像这个示例这样——那么按照如下进行空实现即可：

```python
class YourCommand(BaseCommand):
    name = "\six_seven"
    async def validate(self, args): return args
```

如果你的指令需要参数，那么请参考本文后面的内容。

### 实现 `execute` 函数

每个 Command 都必须实现一个抽象方法：`async def execute(...)`。

它是 Command 的核心运行入口。

示例代码如下：

```python
from __future__ import annotations
from luoying_bot.application.commands.base import BaseCommand
from luoying_bot.domain.result import Reply

class YourCommand(BaseCommand):
    name = "\six_seven"
    async def validate(self, args): return args
	async def execute(self, context, args):
        return Reply(
            text="""刘夫妻🫳🫴小子🧒正在和刘琦先生🧑🏫闹矛盾💥🗣️刘夫妻小子最近在波波播课📱说了这个你和其他的六十七孩子有矛盾吗🤬是的✅你有吗你认为谁是六七真的的代表🤵MR六七还是六十七KID🤔🤔🤔"""
        )
```

可以发现：指令返回的内容**必须是一个 `Reply`** 对象。

以上指令的详细运行效果：

```
用户：@珞樱 \six_seven
珞樱：@用户 刘夫妻🫳🫴小子🧒正在和刘琦先生🧑🏫闹矛盾💥🗣️刘夫妻小子最近在波波播课📱说了这个你和其他的六十七孩子有矛盾吗🤬是的✅你有吗你认为谁是六七真的的代表🤵MR六七还是六十七KID🤔🤔🤔
```

## Command 相关类详解

### BaseCommand

实现如下：

```python
class BaseCommand(ABC):

    name: str = ''
    aliases: list[str] = []
    op_required: bool = False
    args_requried: bool = False
    required_args: dict[str, list[str]] = {}
    optional_args: dict[str, list[str]] = {}


    def __init__(self, services: dict):
        self.services = services

    def _build_alias_map(self) -> dict[str, str]:
        alias_map: dict[str, str] = {}
        for canonical, aliases in {**self.required_args, **self.optional_args}.items():
            alias_map[canonical] = canonical
            for alias in aliases: alias_map[alias] = canonical
        return alias_map
    
    def _parse_args(self, args: list[str] | None) -> dict[str, str]:
        if not self.args_requried:
            return {}
        if len(args) % 2 != 0: raise ValueError(f'参数数量应为偶数，但收到 {len(args)} 个参数')
        alias_map = self._build_alias_map(); normalized: dict[str, str] = {}
        for raw_key, value in zip(args[::2], args[1::2]):
            if raw_key not in alias_map: raise ValueError(f'未知参数: {raw_key}')
            canonical = alias_map[raw_key]
            if canonical in normalized: raise ValueError(f'参数重复：{canonical}')
            normalized[canonical] = value
        missing = [key for key in self.required_args if key not in normalized]
        if missing: raise ValueError(f'缺少必需参数: {", ".join(missing)}')
        return normalized
    
    @abstractmethod
    async def validate(self, args: dict[str, str]) -> dict[str, str]: ...

    @abstractmethod
    async def execute(self, context: ChatContext, args: dict[str, str]) -> Reply: ...

    async def process(self, context: ChatContext, args: Optional[list[str]]) -> Reply:
        if self.op_required and context.user.user_id not in self.services.get('ops', []):
            return Reply(text='权限不足')
        parsed = await self.validate(self._parse_args(args))
        return await self.execute(context, parsed)
```

`BaseSkill` 是所有 Skill 的基类。任何自定义 Skill 都必须继承它。

#### 类属性

- `name: str` 指令的**唯一标识符**，也是指令的触发名称，必须以 `\` 开头，例如 `\help` 、 `\ban`。如果重复会引起错误。
- `aliase` 一个由**字符串组成的列表**。代表该指令的别称，可以为空或不实现。不可以重复。同样必须以 `\` 开头。
- `op_required: bool` 一个布尔值，表示该指令是否需要管理员权限才能执行，默认不需要。关于管理员权限，可以在环境变量中设置或在 `config.py` 中设置默认值。详见 `Config与Constants.md`
- `args_requried: bool` 一个布尔值，表示该指令是否需要接受参数。默认不接受参数。
- `required_args: dict[str, list[str]]` 一个字典，声明该指令所有的必需参数及其别名（简称）。别名（简称）在同一指令内不可以重复。
- `optional_args: dict[str, list[str]]` 一个字典，声明该指令所有的非必需参数及其别名（简称）。别名（简称）在同一指令内不可以重复。

如果 `args_requried` 设为 `False` ，则不需要实现 `required_args` 和 `optional_args`。

参数应该是严格的**一参数一值**，即一个参数名对应一个唯一值。

`required_args` 和 `optional_args` 的详细实现结构：

```python
required_args={
    "--year": ["-y","-Y"],
    "--college": ["-c","-C"],
}
optional_args={
    "--name": ["-n","-N"],
}
```

以上代码分别定义了两个必需参数`--year` 和 `--college` ，一个非必需参数 `--name`。分别都有两个简写别名。

#### 初始化方法

- `services`
  一个字典，里面存放了运行时注入的各类服务实例。
  这些服务通常已经由应用框架统一完成初始化和管理，例如：
  - 用户服务
  - 提醒服务
  - 备忘录服务
  - 其他公共工具服务

在 Command 内部，你可以通过 `self.services` 获取这些服务，以实现更复杂的功能，例如：

- 数据持久化
- 使用脚本工作区
- 访问其他系统模块

常见使用方式如下：

```python
service = self.services.get("service_name")
```

通常情况下，开发者**不需要重写 `__init__` 方法**，直接在 `execute` 中使用 `self.services` 即可。

#### _build_alias_map 与 _parse_args
`_build_alias_map` 与 `_parse_args` 是两个基类已经实现好的方法。在绝大多数情况下都不需要关心他们的用处。

如果你想了解他们的功能：

- `_build_alias_map` 主要用于构造参数别名到参数主名的映射，方便后续进行查找和替换。

- `_parse_args` 主要用于初步验证参数的以下内容：

  - 如果不需要参数，返回空字典
  - 如果收到的参数数量和值数量不匹配，即并不是**一参数对应一值**，抛出一个 `ValueError(f'参数数量应与值数量相等，但收到 {len(args)} 个内容块')`
  - 调用 `_build_alias_map` ，建立映射
  - 验证是否传递了未知的参数
  - 验证是否传递了重复的参数
  - 验证是否缺失了必需参数

  该函数结束后，会将参数字典中所有的以别名形式呈现的参数键值全部替换为全名。

#### process 函数

同上，你也不需要了解其详细实现细节。

如果你想了解：

- 首先，这个函数会检查该指令是否需要管理员权限，同时检查指令发送人是否是管理员。
- 如果不是，则拦截指令的执行。
- 随后，将传入的原始参数经过 `_parse_args` $\Longrightarrow$ `validate` 变为处理后的参数字典。
- 调用 `execute` 执行指令。

#### 抽象方法

指令基类声明了两个抽象方法：`validate` 和 `execute`

`validate` 传入了两个参数：`self` 和 `args: dict[str, str]`。后者是一个字典，键（key）是参数名，值（value）是参数值。二者都是 `str` 类型。例如：

```python
{
    "--name":"熊大"
    "--college":"狗熊岭"
    "--year":"2007"
}
```

以上是一个示例参数字典。

键所代表的参数名已经经过了处理，所有传入的别名都已经被替换为全名。故而你只需要获取全名即可，这方便了你的开发。

你不必担心必需参数不存在，或出现未定义的参数。前面的流程已经帮你处理好并拦截了这一切。

正如前面所说，`validate` 方法用于验证用户传入的参数是否符合你的**自定义规则**。

例如，你要求 `--year` 必须是正整数，则可以这样实现：

```python
async def validate(self, args):
    if not args['--year'].isdigit(): 
        raise ValueError('--year 必须是正整数')
    return args
```

或者，你希望 `--department` 和 `--college` 参数必须成对出现：

```python
async def validate(self, args):
    if ('--department' in args) ^ ('--college' in args): 
        raise ValueError('--department 和 --college 参数必须成对出现')
	return args        
```

请注意，如果发现参数不符合你的规则，你**必须抛出异常**来结束函数。

在函数结束，验证通过的时候，你**必须原封不动的返回`args`**，以便 `process` 将其传递给 `execute`。

`execute` 是指令的执行核心。

说明如下：

- **参数**：

  - `context: ChatContext` 是用户本次指令请求的上下文信息

    可以用于获取平台、会话、用户等相关上下文数据，从而提供更好的服务。

  - `args` 一个参数字典，建立了从参数名到用户传入值的映射。如果想要获得参数可以直接使用 `.get("--argname")` 来获取。

- **返回值**：

  - 必须返回一个 `Reply` 实例。
  - 如果指令执行出错，必须抛出异常。

- **异步要求**：

  - 该方法必须是 `async` 方法，以支持非阻塞 IO 操作。

在 `execute` 方法中，你通常需要完成以下工作：

1. 从 `args` 中提取参数
2. 对参数进行必要校验
3. 执行业务逻辑（如计算、查询、处理、调用外部服务等）
4. 构造并返回 `Reply`
5. 出错时抛出异常，写明异常原因。

#### 自动注册机制

任何继承自 `BaseCommand`，并且正确定义了 `name` 的类，在应用启动时都会被框架自动发现并注册，无需手动导入。

如果你进行的是 Web 端开发，不建议发起指令注册。

#### 异常处理

大多数情况下，类内抛出的异常会作为输出内容被返回给用户。

## Service 使用

`services` 是 Command 与系统其他能力交互的重要入口。

在运行时，框架会把已经初始化好的服务对象统一注入到 Command 中，开发者可以在 `run` 方法里通过 `self.services` 获取对应服务。

一个常见的使用方式如下：

```python
async def execute(self, context, args) -> Reply:
    ops = self.services.get("ops", [])
    ...
```

这个例子从服务中获取了管理员ID列表，可用于判断指令是否对管理员生效

使用建议：

- 优先通过 `self.services.get(...)` 获取服务，避免直接假设某个服务一定存在
- 对获取失败的情况做好判空处理
- 不建议在 Command 内部重复创建本应由框架统一管理的服务实例
- Command 应尽量只关注自身业务逻辑，把通用能力交给 `services` 提供

关于 Service 的详细信息，请查看 `Service创建与使用.md`





