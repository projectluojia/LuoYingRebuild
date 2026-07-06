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
docs/                     # 架构文档、API 参考、PRD
```

React + TypeScript + Vite 前端不放在本仓库内；请在同级独立仓库 `../LuoYing-Frontend/` 维护。

## 关键约定

### 前端边界

本仓库只维护后端 API、VoicePort、Web transport 和后端测试。Live2D、Vite 代理、浏览器语音交互、前端组件和前端构建配置都属于 `../LuoYing-Frontend/`。

### VoicePort 架构

后端 `VoicePort` 定义在 `src/luoying_bot/infra/voice/`。前端 API 客户端在 `../LuoYing-Frontend/src/` 下。Voice router 的 `prefix="/voice"` 已是完整路径，`include_router()` 时**不要**再加 `prefix="/api"`（前端开发代理会处理路径重写）。

### API 路由注册

`api.py` 中 `include_router()` 调用时：
- Voice router：无需额外 prefix（已有 `prefix="/voice"`）
- 其他 router：若需 prefix，确保与 Vite 代理 rewrite 规则一致（`/api` 前缀由代理 stripped）

后端代理端口：`8000`（**不是 `18000`**）。

## 深入文档

- [docs/web_frontend_api.md](docs/web_frontend_api.md) — Web API 完整参考
- [docs/prd_web_voice_live2d.md](docs/prd_web_voice_live2d.md) — Phase 1–4 PRD 及实现状态
- [docs/kb_architecture_report.md](docs/kb_architecture_report.md) — 知识库架构
- [docs/knowledge_base_integration.md](docs/knowledge_base_integration.md) — KB 接入指南
