\# AI Live2D 音视频通话后端 API 设计文档（v1）



\## 1. 背景



当前项目已经具备：



\- 统一的 `AppContainer` 装配方式。

\- 以 `EventHandler` 为核心的统一消息处理链路。

\- 轻量 Web 入口 `POST /chat`，可将 Web 文本包装为统一 `UniMessage` 并进入既有业务链路。



本次扩展的目标不是替换现有聊天能力，而是在现有项目基础上补充 \*\*AI 1 对 1 实时音视频通话后端能力\*\*，并为后续前端（网页 / exe）接入做好稳定 API 契约。



\---



\## 2. 本次已确认的目标



\### 2.1 产品目标



1\. 项目本体运行在服务器上。

2\. 用户在本地通过 \*\*网页或 exe 前端\*\* 访问。

3\. 用户与 AI 进行 \*\*1 对 1 音视频通话\*\*。

4\. \*\*优先实现视频通话能力\*\*。

5\. 用户最终看到的是 \*\*前端本地渲染的 Live2D 形象\*\*，而不是后端直接渲染 Live2D 画面。

6\. 后端负责输出 \*\*驱动 Live2D 的控制信息\*\*。

7\. 前端测试阶段 \*\*能看到文字即可\*\*，不强求完整 UI/视觉效果。



\### 2.2 技术约束



1\. 完全使用 \*\*Python 3.12\*\*。

2\. 使用 \*\*WebRTC\*\* 作为实时媒体协议。

3\. 实时控制通道使用 \*\*WebSocket\*\*。

4\. 仅实现 \*\*1 对 1\*\* 场景，不做多人房间。

5\. 需要支持在 \*\*WSL 无物理摄像头\*\* 环境中完成后端联调与验证。

6\. 只做后端，不在本次范围内实现前端 Live2D 页面。



\### 2.3 架构目标



1\. 保持当前项目的分层方式：`application/services` 负责业务编排，`infra` 负责协议和实现适配，`infra/web` 负责暴露 HTTP / WebSocket 接口。

2\. 不破坏现有 `POST /chat` 文本链路。

3\. 新增接口要同时服务于 \*\*网页前端\*\* 和 \*\*本地 exe 前端\*\*。

4\. API 要为后续 Live2D、TTS、字幕、情绪驱动、嘴型驱动预留扩展位。



\---



\## 3. 本次不做的内容



1\. 不实现正式的前端页面。

2\. 不实现多人会议 / 群通话。

3\. 不要求后端实时渲染 Live2D 视频画面。

4\. 不依赖物理摄像头采集。

5\. 不在 v1 中优先处理复杂生产环境下的 TURN 运维细节。

6\. 不在 v1 中强制实现完整语音打断、AEC、复杂混音等高级媒体能力。



\---



\## 4. 设计原则



\### 4.1 控制面与媒体面分离



后端通信拆为两层：



\- \*\*控制面（Control Plane）\*\*：HTTP + WebSocket

&#x20; - 会话创建 / 销毁

&#x20; - 状态同步

&#x20; - 信令补充

&#x20; - 字幕、文本、错误、调试事件

&#x20; - Live2D 驱动事件

\- \*\*媒体面（Media Plane）\*\*：WebRTC

&#x20; - 音频轨

&#x20; - 视频轨

&#x20; - 可选 DataChannel



\### 4.2 前端渲染 Live2D，后端输出控制信息



后端不负责渲染 Live2D 模型本身，而是输出：



\- `emotion`

\- `speaking`

\- `viseme`

\- `motion`

\- `gesture`

\- `subtitle`



这样网页和 exe 都可以基于同一协议接入。



\### 4.3 先打通视频链路，再逐步接入真实表现层



v1 优先保证：



\- 会话可建立

\- WebRTC 可协商

\- 视频轨可显示

\- 文本与状态事件可到前端

\- WSL 无摄像头也能测试



因此服务端视频轨允许先使用 \*\*虚拟视频源\*\*（占位视频帧 + 状态文字），后续再替换为更真实的表现层来源。



\### 4.4 保持与既有业务链路兼容



文本输入、字幕输出、AI 回复仍然应尽量复用现有统一消息模型和 Agent 体系，避免形成两套完全分裂的业务逻辑。



\---



\## 5. 与当前项目架构的映射



建议新增模块如下：



\### 5.1 application 层



\#### `application/services/call\_service.py`

职责：



\- 创建 / 查询 / 关闭通话会话

\- 维护 1 对 1 会话状态机

\- 维护前端连接与 AI 连接状态

\- 驱动 WebRTC peer 生命周期

\- 将用户文本/媒体事件路由到 AI 处理链路

\- 向前端广播字幕、状态、错误事件



\#### `application/services/avatar\_state\_service.py`

职责：



\- 统一生成 Live2D 控制信息

\- 输出情绪、说话状态、动作建议、viseme 等结构化事件

\- 保持与具体前端 Live2D SDK 解耦



\#### `application/services/realtime\_session\_store.py`

职责：



\- 保存运行期通话状态

\- 保存当前 peer、连接、字幕缓存、最近状态

\- 可先做内存实现，后续再考虑持久化



\### 5.2 infra 层



\#### `infra/realtime/webrtc\_peer.py`

职责：



\- 封装 Python WebRTC 框架（建议使用 `aiortc`）

\- 处理 offer / answer

\- 处理 ICE candidate

\- 挂载音频轨 / 视频轨 / DataChannel



\#### `infra/realtime/tracks/placeholder\_video.py`

职责：



\- 在 WSL 无摄像头环境中生成可视化占位视频轨

\- 视频画面中包含文字信息：如连接状态、当前字幕、时间戳等



\#### `infra/realtime/signaling\_models.py`

职责：



\- 定义请求 / 响应模型

\- 定义事件 envelope



\### 5.3 web 层



\#### `infra/web/realtime\_api.py`

职责：



\- 暴露通话管理 API

\- 暴露 WebRTC 信令 API

\- 暴露 WebSocket 实时事件 API



\#### `main\_web.py`

职责：



\- 保持原先创建 FastAPI app 的方式

\- 在工厂中同时挂载原有 `/chat` 与新增 realtime API



\---



\## 6. 后端总体交互模型



\### 6.1 典型交互顺序



1\. 前端调用 `POST /api/v1/calls` 创建通话。

2\. 前端建立 `WebSocket /api/v1/calls/{call\_id}/ws`。

3\. 前端创建 `RTCPeerConnection`，生成 offer。

4\. 前端调用 `POST /api/v1/calls/{call\_id}/webrtc/offer` 提交 offer。

5\. 后端创建 AI peer，返回 answer。

6\. 双方通过 WebSocket 或 HTTP 补充 ICE candidate。

7\. WebRTC 音视频轨联通。

8\. 后端持续通过 WebSocket 推送：

&#x20;  - 文本字幕

&#x20;  - AI speaking 状态

&#x20;  - Live2D 控制信息

&#x20;  - 错误 / 调试信息

9\. 前端本地渲染 Live2D，并播放音频 / 显示视频 / 文本。

10\. 任一方结束时调用 `DELETE /api/v1/calls/{call\_id}` 或发送 `call.close` 事件。



\---



\## 7. API 设计（v1）



统一前缀：`/api/v1`



\---



\### 7.1 创建通话会话



\*\*POST\*\* `/api/v1/calls`



\#### 请求体



```json

{

&#x20; "user\_id": "u\_123",

&#x20; "user\_name": "Alice",

&#x20; "client\_type": "web",

&#x20; "mode": "video",

&#x20; "avatar\_mode": "live2d"

}

```



\#### 字段说明



\- `user\_id`：业务用户 ID

\- `user\_name`：显示名

\- `client\_type`：`web` / `desktop`

\- `mode`：`video` / `audio`（v1 默认走 `video`）

\- `avatar\_mode`：`live2d`（保留扩展）



\#### 响应体



```json

{

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "session\_id": "sess\_01HXYZ",

&#x20; "status": "created",

&#x20; "ws\_url": "/api/v1/calls/call\_01HXYZ/ws",

&#x20; "webrtc": {

&#x20;   "offer\_url": "/api/v1/calls/call\_01HXYZ/webrtc/offer",

&#x20;   "ice\_url": "/api/v1/calls/call\_01HXYZ/webrtc/ice"

&#x20; },

&#x20; "capabilities": {

&#x20;   "text": true,

&#x20;   "audio": true,

&#x20;   "video": true,

&#x20;   "live2d\_events": true,

&#x20;   "placeholder\_video": true

&#x20; }

}

```



\#### 用途



\- 初始化一个 1 对 1 AI 通话会话

\- 给前端返回后续 WebSocket / WebRTC 的接入地址



\---



\### 7.2 查询通话状态



\*\*GET\*\* `/api/v1/calls/{call\_id}`



\#### 响应体



```json

{

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "status": "active",

&#x20; "user": {

&#x20;   "user\_id": "u\_123",

&#x20;   "user\_name": "Alice"

&#x20; },

&#x20; "assistant": {

&#x20;   "id": "assistant",

&#x20;   "state": "idle"

&#x20; },

&#x20; "transport": {

&#x20;   "websocket": "connected",

&#x20;   "webrtc": "connected"

&#x20; },

&#x20; "media": {

&#x20;   "audio": "connected",

&#x20;   "video": "connected"

&#x20; },

&#x20; "created\_at": "2026-03-22T00:00:00Z"

}

```



\#### 用途



\- 支持前端重连与状态恢复

\- 支持调试面板查询



\---



\### 7.3 关闭通话



\*\*DELETE\*\* `/api/v1/calls/{call\_id}`



\#### 响应体



```json

{

&#x20; "ok": true,

&#x20; "status": "closed"

}

```



\#### 用途



\- 主动结束通话

\- 清理 server 侧 peer、任务和缓存状态



\---



\### 7.4 提交 WebRTC Offer



\*\*POST\*\* `/api/v1/calls/{call\_id}/webrtc/offer`



\#### 请求体



```json

{

&#x20; "type": "offer",

&#x20; "sdp": "v=0..."

}

```



\#### 响应体



```json

{

&#x20; "type": "answer",

&#x20; "sdp": "v=0..."

}

```



\#### 用途



\- 前端创建 `RTCPeerConnection` 后，将 offer 交给后端

\- 后端创建 AI peer 并返回 answer



\---



\### 7.5 交换 ICE Candidate



\*\*POST\*\* `/api/v1/calls/{call\_id}/webrtc/ice`



\#### 请求体



```json

{

&#x20; "candidate": "candidate:...",

&#x20; "sdpMid": "0",

&#x20; "sdpMLineIndex": 0

}

```



\#### 响应体



```json

{

&#x20; "ok": true

}

```



\#### 说明



v1 允许先使用 HTTP 提交 ICE；后续可迁移为全部通过 WebSocket 实时交换。



\---



\### 7.6 前端文本输入（补充接口）



\*\*POST\*\* `/api/v1/calls/{call\_id}/text`



\#### 请求体



```json

{

&#x20; "text": "你好，请介绍一下你自己"

}

```



\#### 响应体



```json

{

&#x20; "accepted": true

}

```



\#### 用途



\- 在前端尚未实现完整语音输入前，可先通过文本驱动 AI 回复

\- 适合 WSL、本地联调、自动化测试

\- 后端收到文本后可继续复用既有统一消息链路



\---



\### 7.7 健康检查



\*\*GET\*\* `/api/v1/realtime/health`



\#### 响应体



```json

{

&#x20; "ok": true,

&#x20; "python": "3.12",

&#x20; "webrtc": "ready"

}

```



\#### 用途



\- 便于部署验证

\- 便于前端启动前快速探测



\---



\## 8. WebSocket 事件设计（v1）



\### 8.1 WebSocket 地址



\*\*GET\*\* `/api/v1/calls/{call\_id}/ws`



\### 8.2 统一 envelope



所有 WebSocket 消息统一为：



```json

{

&#x20; "event": "assistant.text.delta",

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "timestamp": 1770000000,

&#x20; "data": {}

}

```



字段说明：



\- `event`：事件类型

\- `call\_id`：通话 ID

\- `timestamp`：事件时间戳

\- `data`：事件负载



\---



\### 8.3 前端 -> 后端事件



\#### `user.text`



```json

{

&#x20; "event": "user.text",

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "timestamp": 1770000000,

&#x20; "data": {

&#x20;   "text": "你好"

&#x20; }

}

```



\#### `webrtc.ice`



```json

{

&#x20; "event": "webrtc.ice",

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "timestamp": 1770000000,

&#x20; "data": {

&#x20;   "candidate": "candidate:...",

&#x20;   "sdpMid": "0",

&#x20;   "sdpMLineIndex": 0

&#x20; }

}

```



\#### `call.close`



```json

{

&#x20; "event": "call.close",

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "timestamp": 1770000000,

&#x20; "data": {}

}

```



\---



\### 8.4 后端 -> 前端事件



\#### 通话状态类



\##### `call.state.changed`



```json

{

&#x20; "event": "call.state.changed",

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "timestamp": 1770000000,

&#x20; "data": {

&#x20;   "status": "active"

&#x20; }

}

```



\##### `assistant.speaking.start`



```json

{

&#x20; "event": "assistant.speaking.start",

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "timestamp": 1770000000,

&#x20; "data": {}

}

```



\##### `assistant.speaking.stop`



```json

{

&#x20; "event": "assistant.speaking.stop",

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "timestamp": 1770000000,

&#x20; "data": {}

}

```



\---



\#### 文本 / 字幕类



\##### `assistant.text.start`



```json

{

&#x20; "event": "assistant.text.start",

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "timestamp": 1770000000,

&#x20; "data": {

&#x20;   "message\_id": "msg\_001"

&#x20; }

}

```



\##### `assistant.text.delta`



```json

{

&#x20; "event": "assistant.text.delta",

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "timestamp": 1770000000,

&#x20; "data": {

&#x20;   "message\_id": "msg\_001",

&#x20;   "text": "你好，"

&#x20; }

}

```



\##### `assistant.text.final`



```json

{

&#x20; "event": "assistant.text.final",

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "timestamp": 1770000000,

&#x20; "data": {

&#x20;   "message\_id": "msg\_001",

&#x20;   "text": "你好，我已经接入实时通话。"

&#x20; }

}

```



\---



\#### Live2D 驱动类



\##### `avatar.state`



```json

{

&#x20; "event": "avatar.state",

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "timestamp": 1770000000,

&#x20; "data": {

&#x20;   "speaking": true,

&#x20;   "emotion": "calm",

&#x20;   "energy": 0.42

&#x20; }

}

```



\##### `avatar.expression`



```json

{

&#x20; "event": "avatar.expression",

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "timestamp": 1770000000,

&#x20; "data": {

&#x20;   "name": "happy",

&#x20;   "weight": 0.8,

&#x20;   "duration\_ms": 1200

&#x20; }

}

```



\##### `avatar.motion`



```json

{

&#x20; "event": "avatar.motion",

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "timestamp": 1770000000,

&#x20; "data": {

&#x20;   "name": "greet",

&#x20;   "priority": "normal"

&#x20; }

}

```



\##### `avatar.viseme`



```json

{

&#x20; "event": "avatar.viseme",

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "timestamp": 1770000000,

&#x20; "data": {

&#x20;   "viseme": "A",

&#x20;   "strength": 0.76

&#x20; }

}

```



\---



\#### 错误 / 调试类



\##### `system.notice`



```json

{

&#x20; "event": "system.notice",

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "timestamp": 1770000000,

&#x20; "data": {

&#x20;   "message": "connected"

&#x20; }

}

```



\##### `system.error`



```json

{

&#x20; "event": "system.error",

&#x20; "call\_id": "call\_01HXYZ",

&#x20; "timestamp": 1770000000,

&#x20; "data": {

&#x20;   "code": "webrtc\_setup\_failed",

&#x20;   "message": "peer init failed"

&#x20; }

}

```



\---



\## 9. Live2D 控制信息设计建议



为了避免与具体前端 SDK 强耦合，后端只输出抽象控制信息，不输出特定 SDK 指令。



\### 9.1 建议输出字段



\- `speaking`: `true/false`

\- `emotion`: `neutral/calm/happy/excited/sad/thinking/...`

\- `energy`: `0\~1`

\- `motion`: 如 `idle/greet/nod/think`

\- `gesture`: 如 `wave/point/shrug`

\- `viseme`: 如 `A/E/I/O/U/closed`

\- `subtitle`: 当前显示文本



\### 9.2 设计原因



1\. 前端可在网页与 exe 中复用同一协议。

2\. 后续可替换 Live2D SDK 而不影响后端。

3\. 即使前端暂未接好 Live2D，也可以先显示文字和状态。



\---



\## 10. WSL 无摄像头测试策略



\### 10.1 核心策略



后端生成 \*\*占位视频轨\*\*，不依赖物理摄像头。



\### 10.2 占位视频内容建议



视频帧内容可包括：



\- `AI VIDEO PLACEHOLDER`

\- `CALL ID`

\- 当前时间

\- 连接状态

\- 最近一条字幕

\- speaking 状态



\### 10.3 联调收益



1\. 能验证 WebRTC 视频链路是否畅通。

2\. 能在无摄像头机器、WSL、CI 环境中工作。

3\. 后续可逐步替换为：

&#x20;  - 静态头像视频流

&#x20;  - 服务端合成动画

&#x20;  - 或继续坚持前端渲染 Live2D，仅保留占位轨用于诊断



\### 10.4 文本驱动测试



即便还没有麦克风 / ASR：



\- 前端仍可通过 `POST /api/v1/calls/{call\_id}/text`

\- 或通过 `user.text` WebSocket 事件

\- 来驱动 AI 输出文本、状态和控制事件



\---



\## 11. v1 后端落地分阶段建议



\### Phase 1：协议与会话骨架



\- 定义 Pydantic 模型

\- 定义 call session state

\- 暴露创建 / 查询 / 关闭接口

\- 打通 WebSocket 生命周期



\### Phase 2：WebRTC 信令



\- 集成 Python WebRTC 库

\- 实现 offer / answer

\- 实现 ICE 交换

\- 创建占位视频轨



\### Phase 3：AI 文本与事件联动



\- 将文本输入接入现有业务链路

\- 输出 `assistant.text.\*`

\- 输出 `assistant.speaking.\*`

\- 输出 `avatar.state`



\### Phase 4：Live2D 控制增强



\- 输出 emotion / motion / viseme

\- 规范时间戳和节流策略

\- 为前端动画驱动稳定化



\### Phase 5：生产化补强



\- 鉴权与会话过期

\- 错误恢复

\- 监控日志

\- TURN / NAT 方案

\- 压测与资源控制



\---



\## 12. 后端工程落地流程图



```mermaid

flowchart TD

&#x20;   A\[梳理产品目标与约束] --> B\[确定 1 对 1 WebSocket + WebRTC + Live2D 驱动方案]

&#x20;   B --> C\[设计 API 协议与事件模型]

&#x20;   C --> D\[设计 CallSession 与状态机]

&#x20;   D --> E\[在 application/services 实现 CallService]

&#x20;   E --> F\[在 infra/realtime 封装 WebRTC Peer]

&#x20;   F --> G\[实现 WSL 可用的占位视频轨]

&#x20;   G --> H\[在 infra/web 暴露 REST + WebSocket 接口]

&#x20;   H --> I\[接入现有 Agent / 文本链路]

&#x20;   I --> J\[输出 assistant.text 与 avatar.\* 事件]

&#x20;   J --> K\[完成网页/EXE 前端联调]

&#x20;   K --> L\[补齐鉴权、监控、TURN、异常恢复]

```



\---



\## 13. 建议的最小可交付结果（MVP）



MVP 完成后，应满足：



1\. 能创建一个 AI 通话会话。

2\. 前端能通过 WebSocket 获取状态与文本事件。

3\. 前端能通过 WebRTC 拉到后端占位视频轨。

4\. 前端能收到用于驱动 Live2D 的结构化事件。

5\. 在 WSL 无摄像头环境中可完成本地联调。

6\. 不影响既有 `/chat` 文本接口的使用。



\---



\## 14. 后续扩展方向



1\. 接入 TTS 音频轨。

2\. 接入实时 ASR。

3\. 更精细的情绪 / 嘴型 / 动作映射。

4\. 更丰富的前端设备能力协商。

5\. 生产环境 TURN / 鉴权 / 录制能力。





