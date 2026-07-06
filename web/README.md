# 珞樱 Web 前端

珞樱机器人的 Web 界面，基于 React + TypeScript + Vite 构建。支持聊天、图片/文件上传、工作区文件管理，以及语音交互（STT/TTS）。

## 环境要求

- Node.js 22+
- npm 10+（或 pnpm / bun）

## 快速开始

```bash
cd web
npm install
npm run dev
```

然后打开 http://127.0.0.1:5173 。

> 前端开发服务器通过 Vite 代理将 `/api/*` 请求转发到 `http://127.0.0.1:8000`（后端地址），确保 LuoYing 后端已启动。

## 常用命令

| 命令 | 说明 |
| --- | --- |
| `npm run dev` | 启动开发服务器（热更新） |
| `npm run build` | 类型检查 + 生产构建 |
| `npm run test` | 运行所有测试（Vitest） |
| `npm run test:watch` | 监听模式运行测试 |
| `npm run lint` | 代码检查（Oxlint） |
| `npm run preview` | 预览生产构建产物 |

## 项目结构

```
src/
├── api/              # API 客户端封装（Axios）
├── components/       # UI 组件
│   ├── ChatPanel.tsx
│   ├── Live2DPanel.tsx
│   ├── WorkspaceTree.tsx
│   └── ...
├── live2d/           # Live2D 角色上下文与控制器接口
│   ├── Live2DContext.tsx
│   └── Live2DController.ts
├── pages/            # 页面级组件
│   └── HomePage.tsx
├── __tests__/        # 单元测试（Vitest + Testing Library）
│   ├── test_api_client.test.ts
│   ├── test_AudioPlayer.test.tsx
│   ├── test_Live2DContext.test.tsx
│   └── test_VoiceButton.test.tsx
├── App.tsx
├── main.tsx
└── index.css         # Tailwind CSS 入口 + CSS 变量定义
```

## API 代理

开发环境下，Vite 将 `/api/*` 请求代理到后端（默认 `http://127.0.0.1:8000`）。代理规则定义在 `vite.config.ts`：

```ts
server: {
  proxy: {
    '/api': {
      target: 'http://127.0.0.1:8000',
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api/, ''),
    },
  },
},
```

生产部署时，前端构建产物由后端 FastAPI 托管，或配置 Nginx 反向代理到同一后端实例。

## 测试

单元测试使用 Vitest + Testing Library，入口配置在 `vitest.config.ts`（通过 `/// <reference types="vitest/config" />` 引用）。运行：

```bash
npm run test
```

## 类型检查

TypeScript 配置分三层：

- `tsconfig.json` — 项目引用根配置
- `tsconfig.app.json` — 应用代码（`src/`）
- `tsconfig.node.json` — Vite 配置文件（`vite.config.ts`）

构建时 `npm run build` 先运行 `tsc -b` 进行类型检查，再执行 Vite 打包。

## 外部依赖

| 依赖 | 用途 |
| --- | --- |
| React 19 | UI 框架 |
| Tailwind CSS v4 | 样式 |
| react-markdown + remark-gfm | Markdown 渲染 |
| @tailwindcss/vite | Tailwind Vite 插件 |
| vitest + @vitest/browser | 单元测试（浏览器模式） |
| @playwright/test | E2E 测试 |