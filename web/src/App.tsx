import { useState } from 'react';
import { ThemeToggle } from './components/ThemeToggle';
import { ChatWindow } from './components/ChatWindow';
import { ConversationList } from './components/ConversationList';
import { WorkspaceTree } from './components/WorkspaceTree';
import { TrackBanner } from './components/TrackBanner';
import { Live2DPanel } from './components/Live2DPanel';
import { Live2DProvider } from './live2d/Live2DContext';
import { useConversation } from './hooks/useConversation';
import './index.css';

function App() {
  const [activeSession, setActiveSession] = useState('web-session');
  const [showWorkspace, setShowWorkspace] = useState(false);
  const [showLive2D, setShowLive2D] = useState(false);
  const [trackText, setTrackText] = useState<string | null>(null);
  const { messages, isStreaming, error, sendMessage, clearMessages } =
    useConversation(activeSession, { onTrack: setTrackText });

  const handleSessionSelect = (id: string) => {
    setActiveSession(id);
    clearMessages();
  };

  return (
    <Live2DProvider>
      <div
        className="relative h-full w-full overflow-hidden"
        style={{ background: 'radial-gradient(circle at center, #ffeef7 0%, #e7f2ff 100%)' }}
      >
        {/* Background layer */}
        <div className="static-bg" />

        {/* Track Banner */}
        <TrackBanner text={trackText} isStreaming={isStreaming} />

        <div className="relative z-10 flex h-full">
          {/* Left sidebar */}
          <aside
            className="w-72 shrink-0 flex flex-col px-4 py-4"
            style={{ transform: 'translateZ(20px) rotateY(5deg)', transformOrigin: 'left center' }}
          >
            <div className="panel rounded-xl p-4 mb-4 flex items-center justify-between">
              <h1 className="text-xl font-bold" style={{ color: 'var(--color-blue-deep)' }}>
                珞樱
              </h1>
              <ThemeToggle />
            </div>
            <div className="panel rounded-xl flex-1 overflow-hidden flex flex-col min-h-0">
              <ConversationList activeId={activeSession} onSelect={handleSessionSelect} />
            </div>
          </aside>

          {/* Main chat area */}
          <main className="flex-1 flex flex-col min-w-0 px-4 py-4">
            <div className="panel rounded-xl flex-1 flex flex-col min-h-0 overflow-hidden">
              {/* Top bar */}
              <div
                className="flex items-center justify-between px-5 py-3 border-b"
                style={{ borderColor: 'rgba(74, 169, 255, 0.2)' }}
              >
                <div className="flex items-center gap-3">
                  <span
                    className="text-sm font-medium"
                    style={{ color: 'var(--color-blue-deep)' }}
                  >
                    {activeSession === 'web-session' ? '新对话' : '对话中'}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowWorkspace((v) => !v)}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover:scale-105"
                    style={{
                      background: showWorkspace
                        ? 'var(--color-pink-primary)'
                        : 'rgba(74, 169, 255, 0.15)',
                      color: showWorkspace ? 'white' : 'var(--color-blue-deep)',
                      border: '1px solid rgba(74, 169, 255, 0.3)',
                    }}
                  >
                    {showWorkspace ? '隐藏文件' : '工作区'}
                  </button>
                  <button
                    onClick={() => setShowLive2D((v) => !v)}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover:scale-105"
                    style={{
                      background: showLive2D
                        ? 'var(--color-pink-primary)'
                        : 'rgba(74, 169, 255, 0.15)',
                      color: showLive2D ? 'white' : 'var(--color-blue-deep)',
                      border: '1px solid rgba(74, 169, 255, 0.3)',
                    }}
                  >
                    {showLive2D ? '隐藏角色' : 'Live2D'}
                  </button>
                </div>
              </div>

              {/* Chat window */}
              <ChatWindow
                messages={messages}
                isStreaming={isStreaming}
                onSend={sendMessage}
              />
              {error && (
                <div className="px-5 pb-3 text-xs" style={{ color: '#e53e3e' }}>
                  错误: {error}
                </div>
              )}
            </div>
          </main>

          {/* Right panels stack */}
          {showWorkspace && (
            <aside
              className="w-80 shrink-0 px-2 py-4 animate-spring"
              style={{ transform: 'translateZ(20px) rotateY(-5deg)', transformOrigin: 'right center' }}
            >
              <div className="panel rounded-xl h-full overflow-hidden flex flex-col">
                <div
                  className="px-4 py-3 border-b"
                  style={{ borderColor: 'rgba(74, 169, 255, 0.2)' }}
                >
                  <h2 className="text-sm font-semibold" style={{ color: 'var(--color-blue-deep)' }}>
                    工作区
                  </h2>
                </div>
                <div className="flex-1 overflow-y-auto p-3">
                  <WorkspaceTree />
                </div>
              </div>
            </aside>
          )}

          {/* Live2D panel */}
          {showLive2D && (
            <aside className="shrink-0 px-2 py-4 animate-spring">
              <Live2DPanel
                collapsed={false}
                onToggleCollapse={() => setShowLive2D(false)}
              />
            </aside>
          )}
        </div>
      </div>
    </Live2DProvider>
  );
}

export default App;
