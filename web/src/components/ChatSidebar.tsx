import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import type { Conversation } from '../types';

interface ChatSidebarProps {
  activeId: string;
  onSelect: (id: string) => void;
  showLive2D: boolean;
  onToggleLive2D: () => void;
  showVoice: boolean;
  onToggleVoice: () => void;
  onNewConversation: () => void;
  onCreateBranch: () => void;
}

export function ChatSidebar({
  activeId,
  onSelect,
  showLive2D,
  onToggleLive2D,
  showVoice,
  onToggleVoice,
  onNewConversation,
  onCreateBranch,
}: ChatSidebarProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState(false);

  // 加载对话列表
  useEffect(() => {
    loadConversations();
  }, []);

  const loadConversations = async () => {
    try {
      const data = await api.getConversations();
      setConversations(data.conversations || []);
    } catch (err) {
      console.error('Failed to load conversations:', err);
    } finally {
      setLoading(false);
    }
  };

  // 创建新对话
  const handleNew = useCallback(async () => {
    try {
      const { thread_id } = await api.createConversation();
      const newConv: Conversation = {
        thread_id,
        title: '新对话',
        summary: '',
        summarized_message_count: 0,
        archived: false,
        created_at: null,
        updated_at: null,
      };
      setConversations((prev) => [newConv, ...prev]);
      onSelect(thread_id);
    } catch (err) {
      console.error('Failed to create conversation:', err);
    }
  }, [onSelect]);

  // 删除对话
  const handleDelete = useCallback(async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await api.deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.thread_id !== id));
      if (activeId === id) {
        onNewConversation();
      }
    } catch (err) {
      console.error('Failed to delete conversation:', err);
    }
  }, [activeId, onNewConversation]);

  if (collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        className="w-10 h-10 rounded-xl flex items-center justify-center transition-all hover-lift"
        style={{
          background: 'rgba(255, 145, 164, 0.15)',
          border: '1px solid var(--color-border-pink)',
          color: 'var(--color-pink-primary)',
        }}
        title="展开侧边栏"
      >
        ☰
      </button>
    );
  }

  return (
    <aside
      className="w-72 shrink-0 flex flex-col overflow-hidden"
      style={{
        transform: 'translateZ(20px) rotateY(5deg)',
        transformOrigin: 'left center',
      }}
    >
      {/* 头部 */}
      <div className="panel rounded-xl p-4 mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setCollapsed(true)}
            className="w-7 h-7 rounded flex items-center justify-center text-xs transition-all hover-scale"
            style={{ color: 'var(--color-blue-deep)', opacity: 0.6 }}
            title="收起侧边栏"
          >
            ☰
          </button>
          <h2 className="text-lg font-bold" style={{ color: 'var(--color-blue-deep)' }}>
            珞樱
          </h2>
        </div>

        {/* 快捷开关 */}
        <div className="flex items-center gap-2">
          <ToggleButton
            active={showVoice}
            onClick={onToggleVoice}
            title="语音通话"
            icon={
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            }
          />
          <ToggleButton
            active={showLive2D}
            onClick={onToggleLive2D}
            title="Live2D"
            icon={
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            }
          />
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="flex gap-2 mb-4">
        <button
          onClick={() => {
            handleNew();
            onNewConversation();
          }}
          className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all hover-lift"
          style={{
            background: 'var(--color-pink-primary)',
            color: 'white',
          }}
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          新对话
        </button>
        <button
          onClick={onCreateBranch}
          className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all hover-lift"
          style={{
            background: 'rgba(74, 169, 255, 0.15)',
            border: '1px solid var(--color-border-blue)',
            color: 'var(--color-blue-deep)',
          }}
          title="从当前消息创建分支"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
          </svg>
          创建分支
        </button>
      </div>

      {/* 对话列表 */}
      <div className="panel rounded-xl flex-1 overflow-hidden flex flex-col min-h-0">
        <div
          className="px-4 py-3 flex items-center justify-between"
          style={{ borderBottom: '1px solid rgba(74, 169, 255, 0.2)' }}
        >
          <span
            className="text-xs font-semibold uppercase tracking-wider"
            style={{ color: 'var(--color-blue-deep)', opacity: 0.7 }}
          >
            对话列表
          </span>
          <span
            className="text-xs px-2 py-0.5 rounded"
            style={{
              background: 'rgba(74, 169, 255, 0.15)',
              color: 'var(--color-blue-deep)',
            }}
          >
            {conversations.length}
          </span>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {loading && (
            <div className="px-3 py-2 text-xs animate-pulse" style={{ color: 'var(--color-blue-deep)', opacity: 0.5 }}>
              加载中...
            </div>
          )}

          {!loading && conversations.length === 0 && (
            <div className="px-3 py-6 text-center" style={{ color: 'var(--color-blue-deep)', opacity: 0.5 }}>
              <div className="text-2xl mb-2">💬</div>
              <div className="text-xs">暂无对话记录</div>
            </div>
          )}

          {conversations.map((conv) => (
            <div
              key={conv.thread_id}
              onClick={() => onSelect(conv.thread_id)}
              className={`group flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm cursor-pointer transition-all hover-lift ${
                conv.thread_id === activeId ? 'animate-spring' : ''
              }`}
              style={
                conv.thread_id === activeId
                  ? {
                      background: 'rgba(255, 145, 164, 0.15)',
                      borderLeft: '3px solid var(--color-pink-primary)',
                      color: 'var(--color-blue-deep)',
                      fontWeight: 500,
                    }
                  : {
                      background: 'rgba(255, 255, 255, 0.5)',
                      color: 'var(--color-blue-deep)',
                      opacity: 0.75,
                    }
              }
            >
              <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              <span className="flex-1 truncate">{conv.title || '无标题对话'}</span>
              <button
                onClick={(e) => handleDelete(e, conv.thread_id)}
                className="opacity-0 group-hover:opacity-100 p-1 rounded transition-all hover-scale"
                style={{
                  background: 'rgba(229, 62, 62, 0.1)',
                  color: '#e53e3e',
                }}
                aria-label="删除对话"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* 底部功能 */}
      <div className="mt-4 flex gap-2">
        <button
          onClick={() => {
            // TODO: 打开历史管理
          }}
          className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-all hover-lift"
          style={{
            background: 'rgba(255, 255, 255, 0.85)',
            border: '1px solid var(--color-border-blue)',
            color: 'var(--color-blue-deep)',
          }}
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          历史管理
        </button>
      </div>
    </aside>
  );
}

// 开关按钮组件
function ToggleButton({
  active,
  onClick,
  title,
  icon,
}: {
  active: boolean;
  onClick: () => void;
  title: string;
  icon: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-8 h-8 rounded-lg flex items-center justify-center transition-all hover-lift hover-scale ${
        active ? 'animate-pulse' : ''
      }`}
      style={
        active
          ? {
              background: 'linear-gradient(135deg, rgba(255, 145, 164, 0.25), rgba(74, 169, 255, 0.25))',
              color: 'var(--color-pink-primary)',
              boxShadow: 'var(--shadow-glow-pink)',
            }
          : {
              background: 'rgba(255, 255, 255, 0.85)',
              border: '1px solid var(--color-border-blue)',
              color: 'var(--color-blue-deep)',
              opacity: 0.7,
            }
      }
      title={title}
    >
      {icon}
    </button>
  );
}
