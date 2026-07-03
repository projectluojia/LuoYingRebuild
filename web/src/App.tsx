import { useState, useCallback } from 'react';
import { ThemeToggle } from './components/ThemeToggle';
import { ChatWindow } from './components/ChatWindow';
import { WorkspaceTree } from './components/WorkspaceTree';
import { TrackBanner } from './components/TrackBanner';
import { Live2DPanel } from './components/Live2DPanel';
import { Live2DProvider } from './live2d/Live2DContext';
import { StartMenu } from './components/StartMenu';
import { HistoryManager } from './components/HistoryManager';
import { ChatSidebar } from './components/ChatSidebar';
import { Timeline, useTimelineController } from './components/Timeline';
import { useConversation } from './hooks/useConversation';
import { useNavigation } from './hooks/useNavigation';
import { useSparkEffect, useCursorEffect } from './effects';
import './index.css';

function App() {
  const { currentView, navigate, chatParams } = useNavigation();
  const [activeSession, setActiveSession] = useState('web-session');
  const [showWorkspace, setShowWorkspace] = useState(false);
  const [showLive2D, setShowLive2D] = useState(false);
  const [showVoice, setShowVoice] = useState(false);
  const [trackText, setTrackText] = useState<string | null>(null);
  const { messages, isStreaming, error, sendMessage, clearMessages } =
    useConversation(activeSession, { onTrack: setTrackText });

  // 时间轴控制器
  const timeline = useTimelineController();

  // 同步消息到时间轴
  const syncTimeline = useCallback(() => {
    timeline.syncFromMessages(
      messages.map((msg) => ({
        id: msg.id,
        role: msg.role,
        content: msg.content,
        timestamp: msg.timestamp,
        prompt: msg.prompt,
      }))
    );
  }, [messages, timeline]);

  // 启用机能风特效
  useSparkEffect({
    color: '255,145,164',
    scale: 1.5,
    opacity: 1.0,
    speed: 1.0,
    maxTrail: 16,
  });

  useCursorEffect();

  // 处理会话切换
  const handleSessionSelect = useCallback((id: string) => {
    setActiveSession(id);
    clearMessages();
  }, [clearMessages]);

  // 处理创建分支
  const handleCreateBranch = useCallback(() => {
    // TODO: 实现分支创建逻辑
    console.log('Create branch from current conversation');
  }, []);

  // 渲染起始菜单
  if (currentView === 'start') {
    return (
      <Live2DProvider>
        <div
          className="relative h-full w-full overflow-hidden"
          style={{ background: 'radial-gradient(circle at center, #ffeef7 0%, #e7f2ff 100%)' }}
        >
          <div className="static-bg" />
          <StartMenu
            onStartChat={() => navigate.toChat()}
            onOpenHistory={() => navigate.toHistory()}
          />
        </div>
      </Live2DProvider>
    );
  }

  // 渲染历史管理
  if (currentView === 'history') {
    return (
      <Live2DProvider>
        <div
          className="relative h-full w-full overflow-hidden"
          style={{ background: 'radial-gradient(circle at center, #ffeef7 0%, #e7f2ff 100%)' }}
        >
          <HistoryManager
            onBack={() => navigate.toStart()}
            onSelectConversation={(id) => {
              setActiveSession(id);
              clearMessages();
              navigate.toChat({ conversationId: id });
            }}
          />
        </div>
      </Live2DProvider>
    );
  }

  // 渲染聊天界面（默认）
  return (
    <Live2DProvider>
      <div
        className="relative h-full w-full overflow-hidden"
        style={{ background: 'radial-gradient(circle at center, #ffeef7 0%, #e7f2ff 100%)' }}
      >
        {/* 背景层 */}
        <div className="static-bg" />

        {/* 滚动字幕 */}
        <TrackBanner text={trackText} isStreaming={isStreaming} />

        <div className="relative z-10 flex h-full">
          {/* 左侧边栏 */}
          <ChatSidebar
            activeId={activeSession}
            onSelect={handleSessionSelect}
            showLive2D={showLive2D}
            onToggleLive2D={() => setShowLive2D((v) => !v)}
            showVoice={showVoice}
            onToggleVoice={() => setShowVoice((v) => !v)}
            onNewConversation={() => {
              setActiveSession('web-session');
              clearMessages();
            }}
            onCreateBranch={handleCreateBranch}
          />

          {/* 主聊天区域 */}
          <main className="flex-1 flex flex-col min-w-0 px-4 py-4">
            <div
              className="panel rounded-xl flex-1 flex flex-col min-h-0 overflow-hidden"
              style={{ borderLeft: '4px solid var(--color-pink-primary)' }}
            >
              {/* 顶部栏 */}
              <div
                className="flex items-center justify-between px-5 py-3"
                style={{ borderBottom: '1px solid rgba(74, 169, 255, 0.2)' }}
              >
                <div className="flex items-center gap-3">
                  <ThemeToggle />
                  <span
                    className="text-sm font-medium"
                    style={{ color: 'var(--color-blue-deep)' }}
                  >
                    {activeSession === 'web-session' ? '新对话' : '对话中'}
                  </span>
                </div>

                {/* 右侧功能按钮 */}
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowWorkspace((v) => !v)}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover-lift"
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
                    onClick={() => navigate.toHistory()}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover-lift"
                    style={{
                      background: 'rgba(255, 145, 164, 0.15)',
                      border: '1px solid var(--color-border-pink)',
                      color: 'var(--color-pink-primary)',
                    }}
                  >
                    历史管理
                  </button>
                </div>
              </div>

              {/* 聊天内容区（带时间轴） */}
              <div className="flex-1 flex min-h-0 overflow-hidden">
                {/* 时间轴 */}
                <Timeline
                  nodes={timeline.nodes}
                  currentNodeId={timeline.currentNode?.messageId}
                  onNodeClick={(node) => {
                    const index = timeline.nodes.findIndex(
                      (n) => n.messageId === node.messageId
                    );
                    if (index !== -1) {
                      timeline.setCurrentIndex(index);
                    }
                  }}
                />

                {/* 聊天窗口 */}
                <div className="flex-1 flex flex-col min-h-0">
                  <ChatWindow
                    messages={messages}
                    isStreaming={isStreaming}
                    onSend={sendMessage}
                  />
                </div>
              </div>

              {/* 错误信息 */}
              {error && (
                <div className="px-5 pb-3 text-xs" style={{ color: '#e53e3e' }}>
                  错误: {error}
                </div>
              )}
            </div>
          </main>

          {/* 右侧面板堆叠 */}
          {showWorkspace && (
            <aside
              className="w-80 shrink-0 px-2 py-4 animate-spring"
              style={{ transform: 'translateZ(20px) rotateY(-5deg)', transformOrigin: 'right center' }}
            >
              <div className="panel rounded-xl h-full overflow-hidden flex flex-col">
                <div
                  className="px-4 py-3 flex items-center justify-between"
                  style={{ borderBottom: '1px solid rgba(74, 169, 255, 0.2)' }}
                >
                  <h2 className="text-sm font-semibold" style={{ color: 'var(--color-blue-deep)' }}>
                    工作区
                  </h2>
                  <button
                    onClick={() => setShowWorkspace(false)}
                    className="w-6 h-6 rounded flex items-center justify-center text-xs transition-all hover-scale"
                    style={{ color: 'var(--color-blue-deep)', opacity: 0.6 }}
                  >
                    ✕
                  </button>
                </div>
                <div className="flex-1 overflow-y-auto p-3">
                  <WorkspaceTree />
                </div>
              </div>
            </aside>
          )}

          {/* Live2D 面板 */}
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
