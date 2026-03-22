\# 后端工程落地流程图



> 目标：在现有项目基础上，按 \\\*\\\*Python 3.12 + WebSocket + WebRTC + 前端本地渲染 Live2D\\\*\\\* 的方案，逐步落地 1 对 1 AI 音视频通话后端。



\## 流程图



```mermaid

flowchart TD

\&#x20;   A\\\[明确目标与约束\\\\n1对1 / WebRTC / WebSocket / Python3.12 / WSL无摄像头 / 前端本地渲染Live2D] --> B\\\[确认现有项目接入点\\\\nmain\\\_web.py / infra.web.api / bootstrap.py / EventHandler]

\&#x20;   B --> C\\\[定义整体架构\\\\n控制面: HTTP + WebSocket\\\\n媒体面: WebRTC]

\&#x20;   C --> D\\\[定义领域模型与运行时状态\\\\nCallSession / PeerState / AvatarState / EventEnvelope]

\&#x20;   D --> E\\\[设计API契约\\\\n创建会话 / 查询状态 / 关闭会话 / Offer / ICE / Text输入 / Health]

\&#x20;   E --> F\\\[设计WebSocket事件协议\\\\nassistant.text.\\\* / assistant.speaking.\\\* / avatar.\\\* / webrtc.\\\* / system.\\\*]

\&#x20;   F --> G\\\[实现 application/services/call\\\_service.py\\\\n通话状态机 / 会话管理 / 事件编排]

\&#x20;   G --> H\\\[实现 application/services/avatar\\\_state\\\_service.py\\\\n情绪 / speaking / viseme / motion 输出]

\&#x20;   H --> I\\\[实现 infra/realtime/webrtc\\\_peer.py\\\\nPeerConnection / SDP / ICE / Track挂载]

\&#x20;   I --> J\\\[实现 infra/realtime/tracks/placeholder\\\_video.py\\\\nWSL无摄像头占位视频轨]

\&#x20;   J --> K\\\[实现 infra/web/realtime\\\_api.py\\\\nREST + WebSocket 接口]

\&#x20;   K --> L\\\[在 bootstrap.py 中装配新服务\\\\n挂入 main\\\_web.py 应用工厂]

\&#x20;   L --> M\\\[打通现有 Agent / 文本链路\\\\n用户文本 -> UniMessage/EventHandler/Agent -> assistant.text 事件]

\&#x20;   M --> N\\\[联调前端\\\\n网页/EXE 收到文本、状态、Live2D控制事件]

\&#x20;   N --> O\\\[联调 WebRTC 视频轨\\\\n验证浏览器/客户端可看到占位视频]

\&#x20;   O --> P\\\[补齐测试与运维能力\\\\n健康检查 / 日志 / 超时清理 / TURN / 鉴权]

\&#x20;   P --> Q\\\[MVP完成\\\\n可创建会话、建立WebRTC、接收文本与Live2D控制信息]

```



\## 分阶段说明



\### Phase 1：接入点与契约先行

\- 先确认新能力只扩展 Web 入口，不影响现有 QQ 链路。

\- 先定 API 和事件协议，再写实现，避免前后端反复改口。



\### Phase 2：状态机与服务骨架

\- 优先完成 `CallSession`、会话管理、连接管理。

\- 先把“创建会话 -> 查询状态 -> 关闭会话”跑通。



\### Phase 3：WebRTC 打通

\- 接入 Python WebRTC 框架。

\- 先实现 `offer/answer` 与 `ICE` 交换。

\- 优先使用占位视频轨保证 WSL 可测。



\### Phase 4：AI 与 Live2D 控制输出

\- 将文本输入接入现有消息/Agent 体系。

\- 输出：

&#x20; - `assistant.text.start/delta/final`

&#x20; - `assistant.speaking.start/stop`

&#x20; - `avatar.state`

&#x20; - `avatar.expression`

&#x20; - `avatar.motion`

&#x20; - `avatar.viseme`



\### Phase 5：联调与生产化

\- 与网页/EXE 前端联调。

\- 完成异常恢复、鉴权、健康检查、日志、TURN 策略。

\- 最终形成可部署 MVP。



\## 最小完成标准



满足以下条件即可认为后端 MVP 可交付：



1\. 能创建和销毁 1 对 1 AI 通话会话。

2\. 前端能通过 WebSocket 收到实时文本和状态事件。

3\. 前端能通过 WebRTC 收到后端占位视频轨。

4\. 前端能收到驱动 Live2D 的结构化控制信息。

5\. 在 WSL 无摄像头环境中可完成基础联调。

