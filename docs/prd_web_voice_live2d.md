## Problem Statement

LuoYing has a mature backend API with SSE streaming, conversation management, file uploads, and a rich agent/skill system — but no dedicated frontend. The current `GET /` returns a bare JSON health response. Users who want a web-based chat experience must write their own client against the raw API. There is also no voice interaction capability: the message model, transport abstraction, and config layer contain zero audio/speech/TTS/ASR support. Finally, there is no visual presence for the bot — no avatar or animated character — which limits how engaging the web experience can be.

## Solution

Build a modern, standalone web frontend (`web/` directory, React + TypeScript + Vite) that connects to the existing backend API, styled after the project's reference design language (pink–blue–white palette, directional shadows, game-UI aesthetic). Include a collapsible Live2D panel with a well-defined controller interface for future model loading, lip-sync, and expression control. Add backend voice ports and stub implementations so the architecture is ready for TTS/ASR integration without touching any existing code paths.

Everything is purely additive: no existing Python modules, API routes, domain models, or QQ transport behavior are modified.

## User Stories

1. As a web user, I want to open the LuoYing URL in my browser and see a modern chat interface, so that I can talk to the AI without writing curl commands.
2. As a web user, I want my messages to stream in token-by-token via SSE, so that I get immediate feedback while the AI is thinking.
3. As a web user, I want to see a sidebar listing my past conversations, so that I can switch between topics.
4. As a web user, I want to create a new conversation, so that I can start a fresh topic without losing old ones.
5. As a web user, I want to archive a conversation from the sidebar, so that I can declutter without permanently losing history.
6. As a web user, I want to delete a conversation, so that I can permanently remove unwanted threads.
7. As a web user, I want to restore an archived conversation, so that I can revisit old threads.
8. As a web user, I want to upload images in the chat, so that the AI can understand and respond to visual content.
9. As a web user, I want to upload files in the chat, so that the AI can read documents, spreadsheets, and code.
10. As a web user, I want uploaded images to display inline in the chat, so that I can see what I sent without downloading.
11. As a web user, I want to see a workspace file tree panel, so that I can browse files the AI has generated for me.
12. As a web user, I want to download files from the workspace tree, so that I can save the AI's output locally.
13. As a web user, I want the AI's replies to render Markdown (headings, code blocks, lists, tables), so that structured content is readable.
14. As a web user, I want to see agent action status updates while the AI works, so that I know it hasn't stalled.
15. As a web user, I want a collapsible Live2D panel on the right side of the chat, so that I can see an animated character or hide it for more chat space.
16. As a web user, I want the Live2D panel to show a placeholder when no model is loaded, so that the UI doesn't break before models are configured.
17. As a developer, I want a `Live2DController` TypeScript interface (`loadModel`, `setExpression`, `startLipSync`, `stopLipSync`, `onTap`), so that future Live2D integration has a stable contract.
18. As a web user, I want a microphone button in the chat input area, so that I can initiate voice input when the backend supports it.
19. As a web user, I want the microphone button to be hidden or disabled when the backend reports voice is unavailable, so that I'm not confused by a non-functional button.
20. As a web user, I want the frontend to check `GET /voice/config` on load, so that it knows whether to enable voice features.
21. As a developer, I want `POST /voice/stt` and `POST /voice/tts` API routes that delegate to a `VoicePort` abstraction, so that any TTS/ASR provider can be swapped in later.
22. As a developer, I want a `StubVoiceAdapter` that returns `available() = False`, so that the system works out of the box without a voice service configured.
23. As a developer, I want an `audio` segment type in `MessageSegment` alongside the existing text/image/file types, so that voice messages can flow through the conversation pipeline.
24. As a web user, I want the chat interface to use the LuoYing design language (pink `#ff91a4` accent, blue `#4aa9ff` interactive elements, white translucent panels, directional shadows), so that the web experience feels like it belongs to the same product.
25. As a web user, I want hover effects on interactive elements to use smooth cubic-bezier easing and lift-shadow transitions, consistent with the reference design.
26. As a web user, I want the layout to be responsive and centered with a max-width container, so that it looks good on different screen sizes.
27. As a web user, I want a dark/light theme toggle or an auto theme based on system preference, so that I can chat comfortably at night.
28. As a developer, I want the `web/` directory to be a self-contained Vite project that does not affect the Python backend's build, install, or runtime, so that the existing QQ and CLI entry points are untouched.
29. As a developer, I want `vite.config.ts` to proxy `/api` to the FastAPI backend during development, so that frontend development does not require CORS changes.
30. As a developer, I want the voice API routes added in a new router module (not edited into the existing `api.py`), so that the existing endpoint registration is untouched.

## Implementation Decisions

### Additive-only constraint

Every change is a new file or a new registration call. No existing Python module has its behavior changed. Specifically:
- `infra/http/api.py` is not edited — new routes go in a new `infra/http/voice_api.py` router, included via `app.include_router()` in the lifespan setup (the same pattern used by `knowledge_base_api.py`).
- `domain/message.py` — the `audio` segment type is a data convention (a `MessageSegment` with `type="audio"`), not a code change; `MessageSegment` is already generic over `type: str`.
- `ports/transport.py` is not edited.
- `config.py` — new voice-related settings fields are appended at the end of the `Settings` dataclass; existing fields and their defaults are untouched.

### Frontend: React + TypeScript + Vite + Tailwind

The frontend lives in `web/` at the repo root. It is a self-contained npm project with its own `package.json`, `tsconfig.json`, and `vite.config.ts`. It does not appear in `pyproject.toml` or the Python build.

Key libraries:
- **React 18** with TypeScript
- **Vite** for bundling and dev server
- **TailwindCSS v4** for utility-first styling with custom theme tokens matching the reference palette
- **Zustand** for lightweight state management (chat store, settings store)
- **react-markdown** + **remark-gfm** + **rehype-highlight** for Markdown rendering
- **pixi-live2d-display** (optional peer dependency) for Live2D rendering
- A Vite dev proxy at `/api` pointing to `http://127.0.0.1:8000` eliminates CORS during development

### Design system: LuoYing visual language

Tailwind custom theme tokens derived from the reference repo:

| Token | Value | Usage |
|---|---|---|
| `pink-accent` | `#ff91a4` | Primary accent, active states |
| `blue-bright` | `#4aa9ff` | Interactive borders, focus rings |
| `blue-deep` | `#2d5fa8` | Primary text |
| `blue-soft` | `#8ab6ff` | Secondary borders, hover |
| `bg-panel` | `rgba(255,255,255,0.92)` | Panel backgrounds |
| `bg-gradient-from` | `#ffeef7` | Radial background gradient start |
| `bg-gradient-to` | `#e7f2ff` | Radial background gradient end |

Shadows follow the reference convention: directional (upper-left light source), e.g. `-4px 4px 10px rgba(120,150,200,0.28)`. Hover transitions use `cubic-bezier(0.2, 0.8, 0.2, 1)` with 0.25s duration.

### Layout structure

```
+----------------------------------------------------------+
|  TopBar: logo, new-chat button, settings                 |
+------------+-----------------------------+---------------+
|  Sidebar   |  ChatPanel                  |  Live2DPanel  |
| (conv list)|  (resizable)               | (collapsible) |
|            |  MessageList (scrollable)   |               |
|            |  ChatInput + mic button     |               |
+------------+-----------------------------+---------------+
```

The Live2D panel is collapsible (folds to a thin strip with a toggle icon). When collapsed, the chat panel expands to fill the space.

### SSE streaming integration

The frontend consumes `POST /chat/stream` using the Fetch API with `response.body.getReader()`. Event types handled: `start`, `track`, `text_start`, `text_delta`, `text_end`, `file`, `script_result`, `final`, `error`, `done`. Unknown events are ignored per the API contract.

### Voice port abstraction (backend)

New file `ports/voice.py`:

```python
class VoicePort(ABC):
    @abstractmethod
    async def speech_to_text(self, audio: bytes, format: str) -> str: ...

    @abstractmethod
    async def text_to_speech(self, text: str, voice_id: str) -> AsyncIterator[bytes]: ...

    @abstractmethod
    def available(self) -> bool: ...
```

New file `infra/voice/stub.py` provides `StubVoiceAdapter` where `available()` returns `False` and both methods raise `NotImplementedError`.

New file `infra/http/voice_api.py` provides a FastAPI router with three endpoints:
- `GET /voice/config` returns `{"stt_enabled": bool, "tts_enabled": bool}`
- `POST /voice/stt` accepts multipart audio, returns `{"text": "..."}`
- `POST /voice/tts` accepts `{"text": str, "voice_id": str}`, returns audio stream

The router is included in `create_app()` the same way `knowledge_base_api` is included — by adding one `app.include_router()` call. This is the only edit to `api.py`: a single new line registering the router.

### Live2D interface contract

```typescript
interface Live2DController {
  loadModel(modelUrl: string): Promise<void>;
  setExpression(expression: string): void;
  startLipSync(audioBuffer: AudioBuffer): void;
  stopLipSync(): void;
  onTap(hitArea: string): void;
}
```

The `<Live2DPanel />` component accepts an optional `modelUrl` prop. When null, it renders a styled placeholder. A React context (`Live2DContext`) exposes the controller to sibling components (voice player, chat panel) so that TTS playback can trigger lip-sync without prop drilling.

### audio message segment

No code change to `MessageSegment` — it is already `type: str` with a `data: dict`. The convention for audio is:

```python
MessageSegment(type="audio", data={"file": "path/to/audio.wav", "duration": 3.5})
```

LLM text conversion (`_segment_to_llm_text`) already falls through to `[{seg.type}:{seg.data}]` for unknown types, so audio segments are naturally represented without code changes.

## Testing Decisions

### What makes a good test

Tests verify external behavior at module boundaries, not internal implementation details. A good test for this PRD asserts that an HTTP request returns the expected status and shape, that a React component renders the correct elements given props and mock API responses, or that a port abstraction's contract is satisfied by an adapter. Tests do not assert internal state transitions, CSS class names, or call counts on internal methods.

### Backend: API endpoint tests

New file `test/web/test_voice_api.py`. Tests use `httpx.AsyncClient` against the ASGI app (same pattern as the `test/kb/unit/` test structure of pytest-asyncio with injected fakes).

Test cases:
- `GET /voice/config` returns `{"stt_enabled": false, "tts_enabled": false}` when stub adapter is active.
- `POST /voice/stt` returns 503 when voice is unavailable.
- `POST /voice/tts` returns 503 when voice is unavailable.

### Backend: Voice port tests

New file `test/web/test_voice_port.py`. Verifies that `StubVoiceAdapter.available()` returns `False` and that its methods raise `NotImplementedError`.

### Frontend: Component tests

New files under `web/src/__tests__/`. Uses Vitest + React Testing Library. Prior art: none in this repo yet (first frontend tests), but follows standard React Testing Library conventions.

Test cases:
- `ChatInput` renders a text input and send button; submitting emits the expected callback.
- `MessageBubble` renders user messages and assistant messages with correct roles.
- `VoiceButton` is hidden when voice config reports unavailable.
- `Live2DPanel` renders placeholder when no model URL is provided.
- `useSSE` hook processes a mock event stream and produces the expected message sequence.

## Out of Scope

- **Real TTS/ASR integration**: This PRD delivers the port abstraction, stub, and API routes. Connecting to DashScope, OpenAI Whisper, or any real voice service is a follow-up.
- **User authentication**: The web frontend inherits the current anonymous `web-user` identity. Real login/registration is a separate effort.
- **Live2D model loading from production CDN**: The panel and interface are built; sourcing and hosting actual `.moc3` model files is separate.
- **Live2D lip-sync and expression triggering**: The interface is defined; wiring TTS audio output to `startLipSync()` and LLM emotion tags to `setExpression()` is a follow-up once both voice and Live2D model loading are functional.
- **Mobile-first responsive design**: The layout is responsive at desktop/tablet widths. A dedicated mobile layout (hamburger sidebar, bottom nav) is deferred.
- **QQ transport voice support**: Voice interaction is Web-only in this phase. QQ voice messages (silk/amr format) are not handled.
- **Production build serving from FastAPI**: During development, Vite dev server proxies to FastAPI. A production setup where FastAPI serves the built frontend assets (or a reverse proxy like Nginx) is not configured in this PRD.
- **User-to-user P2P audio/video calls (WebRTC)**: The architecture allows adding this later, but it is explicitly out of scope.

## Further Notes

- The only edit to an existing file is adding one `app.include_router(voice_router)` line in `api.py`. Every other change is a new file.
- The `web/` directory should be added to the project's `.gitignore` for `node_modules/` and `dist/`. The existing `.gitignore` only covers Python artifacts.
- The reference design repo (`LuoYing-Frontend`) is a static HTML/CSS/JS mockup with Arknights-inspired aesthetics. The chat frontend adapts its color palette and interaction patterns (directional shadows, cubic-bezier easing, hover lift effects) but does not replicate its game-specific layout or canvas particle effects.
- The `MessageSegment(type="audio")` convention does not require a migration. It works immediately because `MessageSegment.type` is an unconstrained string and `_segment_to_llm_text` has a catch-all branch for unknown types. This means existing QQ and CLI pipelines ignore audio segments gracefully.
