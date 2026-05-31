# Web API

本文档描述 Web 入口暴露的 HTTP API 与流式事件协议。任何客户端都可以按本文档调用这些接口；具体页面实现不属于 API 契约的一部分。

API 分为两类：

- **稳定 API**：请求/响应结构与主要行为会尽量长期保持兼容。
- **实验性 API**：仍在试验阶段，事件字段、触发时机、语义细节可能变化；本文档只记录当前实现，不保证长期正确。

除特别说明外，请求和响应均使用 UTF-8。JSON 错误响应通常遵循 FastAPI 默认格式：

```json
{
  "detail": "错误原因"
}
```

## 稳定 API

### GET `/health`

服务健康检查。

响应：

```json
{
  "ok": "true"
}
```

### GET `/`

返回 Web 客户端 HTML 页面。

响应类型：`text/html`

### GET `/auth/me`

获取当前 Web 用户信息。

当前实现中 Web 用户是固定匿名用户。

响应：

```json
{
  "user_id": "web-user",
  "user_name": "网页用户",
  "email": null,
  "authenticated": false
}
```

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `user_id` | string | 当前用户 ID |
| `user_name` | string | 当前用户显示名 |
| `email` | string \| null | 邮箱；匿名用户为 `null` |
| `authenticated` | boolean | 是否已认证 |

### POST `/auth/logout`

登出当前 Web 用户。

当前实现中没有真实登录态，因此该接口只返回成功。

响应：

```json
{
  "ok": true
}
```

### POST `/uploads/images`

上传图片，并保存到当前用户脚本工作区的 `upload/` 目录。

请求类型：`multipart/form-data`

表单字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | file | 是 | 图片文件 |

限制：

- 最大 10MB。
- `Content-Type` 必须以 `image/` 开头。
- 支持扩展名：`.png`、`.jpg`、`.jpeg`、`.webp`、`.gif`、`.bmp`。
- 服务端会校验图片内容是否可识别。

响应：

```json
{
  "image_id": "upload/example.png",
  "file_name": "example.png",
  "content_type": "image/png",
  "size": 12345,
  "url": "/uploads/images/upload/example.png"
}
```

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `image_id` | string | 后续聊天请求中使用的图片引用 ID |
| `file_name` | string | 原始文件名 |
| `content_type` | string | 上传文件的 MIME 类型 |
| `size` | number | 文件大小，单位 byte |
| `url` | string | 图片访问 URL |

常见错误：

- `400`：不是图片、图片类型不支持、图片内容无效。
- `413`：图片超过 10MB。

### GET `/uploads/images/{image_id}`

读取已上传图片。

路径参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `image_id` | string | `/uploads/images` 返回的 `image_id` |

示例：

```text
GET /uploads/images/upload/example.png
```

响应类型：图片文件本体。

常见错误：

- `400`：图片引用无效、文件不存在或已失效。

### POST `/uploads/files`

上传普通文件，并保存到当前用户脚本工作区的 `upload/` 目录。

请求类型：`multipart/form-data`

表单字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | file | 是 | 任意普通文件 |

限制：

- 最大 25MB。
- 文件名会做安全化处理。
- 如果同名文件已存在，服务端会自动追加序号。

响应：

```json
{
  "file_id": "upload/data.csv",
  "file_name": "data.csv",
  "content_type": "text/csv",
  "size": 12345,
  "url": "/download/web-user/upload/data.csv"
}
```

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `file_id` | string | 后续聊天请求中使用的文件引用 ID |
| `file_name` | string | 原始文件名 |
| `content_type` | string | 上传文件的 MIME 类型 |
| `size` | number | 文件大小，单位 byte |
| `url` | string | 文件下载 URL |

常见错误：

- `413`：文件超过 25MB。

### GET `/workspace/tree`

获取当前 Web 用户脚本工作区的结构化文件树。前端右侧文件栏应优先使用该接口展示工作区状态，并对文件节点使用 `url` 字段下载。

响应：

```json
{
  "user_id": "web-user",
  "root": {
    "name": "web-user",
    "path": "",
    "type": "directory",
    "children": [
      {
        "name": "upload",
        "path": "upload",
        "type": "directory",
        "children": [
          {
            "name": "data.csv",
            "path": "upload/data.csv",
            "type": "file",
            "size": 12345,
            "modified_at": 1780156800.0,
            "url": "/download/web-user/upload/data.csv"
          }
        ]
      }
    ]
  }
}
```

节点字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | string | 文件或目录名 |
| `path` | string | 用户脚本工作区下的相对路径；根目录为空字符串 |
| `type` | `"directory"` \| `"file"` | 节点类型 |
| `children` | array | 目录子节点；仅目录节点包含 |
| `size` | number | 文件大小，单位 byte；仅文件节点包含 |
| `modified_at` | number \| null | 文件修改时间戳；仅文件节点包含 |
| `url` | string | 文件下载 URL；仅文件节点包含 |

### GET `/download/{user_id}/{file_path}`

下载当前用户脚本工作区中的文件。

路径参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `user_id` | string | 当前用户 ID；当前 Web 端通常是 `web-user` |
| `file_path` | string | 用户脚本工作区下的相对路径 |

示例：

```text
GET /download/web-user/upload/data.csv
GET /download/web-user/aaa/ccc.py
```

响应类型：文件本体。

常见错误：

- `400`：用户标识无效、文件路径无效、文件路径越界。
- `403`：无权下载该用户文件。
- `404`：文件不存在。

### POST `/chat`

发送一次非流式聊天请求。

该接口的请求/响应结构稳定；模型具体回复内容不承诺稳定。

请求：

```json
{
  "session_id": "web-session",
  "text": "你好",
  "image_ids": [],
  "file_ids": []
}
```

字段说明：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | string | 否 | `"web-session"` | 会话 ID；相同 ID 会共享对话上下文 |
| `text` | string | 是 | 无 | 用户文本 |
| `image_ids` | string[] | 否 | `[]` | 已上传图片 ID，最多 8 个 |
| `file_ids` | string[] | 否 | `[]` | 已上传文件 ID，最多 8 个 |

响应：

```json
{
  "reply": "你好呀。"
}
```

常见错误：

- `400`：引用的图片或文件不存在、无效或已失效。
- `503`：Web Agent 尚未启动完成。

## 实验性 API

### POST `/chat/stream`

发送一次流式聊天请求。

该接口通过 `POST` 请求提交聊天输入，并以 `text/event-stream` 格式返回事件流。客户端可以使用支持读取响应流的 HTTP 客户端消费该接口。

事件名称、字段、触发时机仍属于实验性协议。

请求体与 `/chat` 相同：

```json
{
  "session_id": "web-session",
  "text": "请写一个脚本",
  "image_ids": [],
  "file_ids": []
}
```

响应类型：

```text
text/event-stream
```

每个事件格式：

```text
event: 事件名
data: JSON字符串

```

当前可能出现的事件如下。

#### `start`

表示服务端已接收请求，并为本次请求建立流式通道。

```json
{
  "request_uid": "7a9b..."
}
```

#### `track`

中间状态事件。用于展示 Agent 正在做什么。

```json
{
  "kind": "agent_action",
  "text": "正在调用技能...",
  "metadata": {}
}
```

当前常见 `kind`：

| kind | 说明 |
| --- | --- |
| `agent_action` | 主 Agent 中间步骤 |
| `workspace_debug` | 文件工作区 Agent 调试步骤 |
| `file` | 兼容旧文件发送链路的文件变更提示 |

当 `kind` 为 `file` 时，表示工作区文件可能发生变化。客户端应把它视为刷新 `/workspace/tree` 的信号；`metadata` 中仍可能携带兼容旧前端的可下载文件信息：

```json
{
  "kind": "file",
  "text": "文件已生成：aaa/ccc.py",
  "metadata": {
    "file_name": "ccc.py",
    "path": "aaa/ccc.py",
    "url": "/download/web-user/aaa/ccc.py",
    "size": 33
  }
}
```

#### `file`

文件生成或发送事件。该事件保留为兼容旧 transport 行为；新前端应把它视为工作区文件变更信号，然后重新请求 `/workspace/tree`，而不是只追加一个下载卡片。

```json
{
  "file": "/absolute/path/to/ccc.py",
  "file_name": "ccc.py",
  "user_id": "web-user",
  "path": "aaa/ccc.py",
  "size": 33,
  "url": "/download/web-user/aaa/ccc.py"
}
```

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `file` | string | 服务端本地绝对路径；客户端不应依赖该字段下载 |
| `file_name` | string | 文件名 |
| `user_id` | string | 文件所属用户 |
| `path` | string | 用户脚本工作区内的相对路径 |
| `size` | number | 文件大小，单位 byte |
| `url` | string | 下载 URL |

#### `text_start`

表示助手回复正文开始输出。

```json
{}
```

#### `text_delta`

助手回复正文片段。

客户端应按接收顺序拼接 `text` 字段。

```json
{
  "text": "你好"
}
```

#### `text_end`

表示助手回复正文流式输出结束。

```json
{}
```

#### `script_result`

脚本运行结果事件。当前主要由文件工作区 Agent 运行 Python 脚本时触发。

```json
{
  "result": {
    "type": "script_result",
    "file_path": "hello.py",
    "args": "",
    "returncode": 0,
    "stdout": "hello\n",
    "stderr": "",
    "timeout": false
  }
}
```

该事件仍在调整中，客户端不应假设所有字段长期稳定。

#### `final`

最终完整回复。

客户端可以使用 `text_delta` 增量渲染正文，也可以在收到 `final` 后使用 `reply` 获得完整文本。

```json
{
  "reply": "完整回复文本"
}
```

#### `error`

流式处理过程中出现错误。

```json
{
  "error": "ValueError: ..."
}
```

#### `done`

流式请求结束。无论成功或失败，服务端最终都会尽量发送该事件。

```json
{}
```

## 客户端调用建议

- 优先使用 `/chat/stream` 获得更好的中间状态与正文流式体验。
- 仍需要最简单集成时，可以使用 `/chat`。
- 发送图片前先调用 `/uploads/images`，然后把返回的 `image_id` 放入 `image_ids`。
- 发送普通文件前先调用 `/uploads/files`，然后把返回的 `file_id` 放入 `file_ids`。
- 展示工作区文件时优先使用 `/workspace/tree`，文件下载只使用文件节点的 `url` 字段，不依赖服务端本地绝对路径。
- 对 `/chat/stream` 的未知事件应忽略，保留向前兼容空间。
- 收到 `track(kind="file")` 或 `file` 事件时，客户端应刷新 `/workspace/tree`。这两个事件可能同时出现，客户端应对刷新做防抖。
