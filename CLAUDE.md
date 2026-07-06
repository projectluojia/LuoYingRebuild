# CLAUDE.md

珞樱（LuoYing）是一个多入口 AI 助手机器人，支持 QQ OneBot、FastAPI Web API、CLI。

## 项目结构

```
src/luoying_bot/          # Python 后端（主业务逻辑）
  app.py                  # 入口
  domain/                 # 核心领域模型（MessageSegment、ChatContext 等）
  infra/
    http/
      api.py              # FastAPI 应用（路由注册入口）
      voice_api.py        # Voice router（prefix="/voice"）
    voice/                # VoicePort 实现（TTS/STT）
  services/               # Agent、ReAct、Skill 系统
web/                      # React 前端（React + TypeScript + Vite）
  src/
    live2d/               # Live2D 虚拟形象（Controller 接口、PIXI 实现、Context）
    voice/                # 前端语音（录音、TTS 播放、WebSocket）
    api/                  # Axios API 客户端
docs/                     # 架构文档、API 参考、PRD
```

## 关键约定

### Live2D 控制器接口

所有 Live2D 实现必须满足 `src/live2d/Live2DController.ts` 接口（`loadModel`, `setExpression`, `startLipSync`, `stopLipSync`, `onTap`, `destroy`）。`web/src/live2d/Live2DContext.tsx` 通过 `NullController` 优雅降级——无需空值判断。

`PixiLive2DController.ts` 使用动态 `import('pixi-live2d-display')` 避免模块级 WebGL 初始化错误，**禁止使用顶层静态 import**。

### VoicePort 架构

后端 `VoicePort` 定义在 `src/luoying_bot/infra/voice/`。前端 API 客户端在 `web/src/api/voice.ts`。Voice router 的 `prefix="/voice"` 已是完整路径，`include_router()` 时**不要**再加 `prefix="/api"`（Vite 代理已处理路径重写）。

### API 路由注册

`api.py` 中 `include_router()` 调用时：
- Voice router：无需额外 prefix（已有 `prefix="/voice"`）
- 其他 router：若需 prefix，确保与 Vite 代理 rewrite 规则一致（`/api` 前缀由代理 stripped）

### 前端环境变量

| 变量 | 说明 |
|------|------|
| `VITE_LIVE2D_MODEL_URL` | Live2D 模型 `.model3.json` 地址 |
| `VITE_ENABLE_LIVE2D` | `true` 时启用 Live2D 面板 |
| `VITE_WS_URL` | WebSocket 连接地址（默认同域） |

后端代理端口：`8000`（**不是 `18000`**）。

## 深入文档

- [docs/web_frontend_api.md](docs/web_frontend_api.md) — Web API 完整参考
- [docs/prd_web_voice_live2d.md](docs/prd_web_voice_live2d.md) — Phase 1–4 PRD 及实现状态
- [docs/kb_architecture_report.md](docs/kb_architecture_report.md) — 知识库架构
- [docs/knowledge_base_integration.md](docs/knowledge_base_integration.md) — KB 接入指南
