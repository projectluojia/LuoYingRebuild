import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import type { Conversation, ConversationFolder } from '../types';

interface HistoryManagerProps {
  onBack: () => void;
  onSelectConversation: (conversationId: string) => void;
}

export function HistoryManager({ onBack, onSelectConversation }: HistoryManagerProps) {
  const [folders, setFolders] = useState<ConversationFolder[]>([]);
  const [unfoldered, setUnfoldered] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newFolderName, setNewFolderName] = useState('');
  const [showNewFolderInput, setShowNewFolderInput] = useState(false);
  const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null);
  const [editingFolderId, setEditingFolderId] = useState<string | null>(null);
  const [editingFolderName, setEditingFolderName] = useState('');

  // 加载对话列表
  useEffect(() => {
    loadConversations();
  }, []);

  const loadConversations = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getConversations();
      setUnfoldered(data.conversations || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  // 创建文件夹
  const handleCreateFolder = useCallback(() => {
    if (!newFolderName.trim()) return;
    const folder: ConversationFolder = {
      id: `folder-${Date.now()}`,
      name: newFolderName.trim(),
      conversations: [],
      expanded: true,
      createdAt: new Date().toISOString(),
    };
    setFolders((prev) => [...prev, folder]);
    setNewFolderName('');
    setShowNewFolderInput(false);
  }, [newFolderName]);

  // 删除文件夹
  const handleDeleteFolder = useCallback((folderId: string) => {
    setFolders((prev) => {
      const folder = prev.find((f) => f.id === folderId);
      if (folder) {
        setUnfoldered((u) => [...u, ...folder.conversations]);
      }
      return prev.filter((f) => f.id !== folderId);
    });
  }, []);

  // 开始编辑文件夹名
  const startEditFolder = useCallback((folder: ConversationFolder) => {
    setEditingFolderId(folder.id);
    setEditingFolderName(folder.name);
  }, []);

  // 保存文件夹名编辑
  const saveEditFolder = useCallback(() => {
    if (!editingFolderId || !editingFolderName.trim()) return;
    setFolders((prev) =>
      prev.map((f) =>
        f.id === editingFolderId ? { ...f, name: editingFolderName.trim() } : f
      )
    );
    setEditingFolderId(null);
    setEditingFolderName('');
  }, [editingFolderId, editingFolderName]);

  // 切换文件夹展开状态
  const toggleFolder = useCallback((folderId: string) => {
    setFolders((prev) =>
      prev.map((f) =>
        f.id === folderId ? { ...f, expanded: !f.expanded } : f
      )
    );
  }, []);

  // 将对话移入/移出文件夹
  const moveConversation = useCallback((conversationId: string, folderId: string | null) => {
    setFolders((prev) => {
      // 从所有文件夹中移除
      const cleaned = prev.map((f) => ({
        ...f,
        conversations: f.conversations.filter((c) => c.thread_id !== conversationId),
      }));

      if (folderId) {
        const folder = cleaned.find((f) => f.id === folderId);
        const conversation =
          unfoldered.find((c) => c.thread_id === conversationId) ||
          cleaned.flatMap((f) => f.conversations).find((c) => c.thread_id === conversationId);
        if (folder && conversation) {
          return cleaned.map((f) =>
            f.id === folderId
              ? { ...f, conversations: [...f.conversations, { ...conversation, folderId }] }
              : f
          );
        }
      }
      return cleaned;
    });

    if (!folderId) {
      const conversation = folders
        .flatMap((f) => f.conversations)
        .find((c) => c.thread_id === conversationId);
      if (conversation) {
        setUnfoldered((prev) => [...prev, { ...conversation, folderId: undefined }]);
      }
    }
  }, [folders, unfoldered]);

  // 选择对话
  const handleSelectConversation = useCallback((conv: Conversation) => {
    setSelectedConversation(conv);
  }, []);

  // 开始对话
  const handleStartConversation = useCallback((conv: Conversation) => {
    onSelectConversation(conv.thread_id);
  }, [onSelectConversation]);

  return (
    <div className="relative h-full w-full flex flex-col overflow-hidden">
      {/* 背景 */}
      <div className="static-bg" />

      {/* 顶部栏 */}
      <header
        className="relative z-10 flex items-center justify-between px-6 py-4"
        style={{ borderBottom: '1px solid rgba(74, 169, 255, 0.2)' }}
      >
        <div className="flex items-center gap-4">
          <button
            onClick={onBack}
            className="w-9 h-9 rounded-xl flex items-center justify-center transition-all hover-lift hover-scale"
            style={{
              background: 'rgba(255, 145, 164, 0.15)',
              border: '1px solid var(--color-border-pink)',
              color: 'var(--color-pink-primary)',
            }}
          >
            ←
          </button>
          <h1
            className="text-xl font-bold"
            style={{ color: 'var(--color-blue-deep)' }}
          >
            历史管理
          </h1>
        </div>

        {/* 新建文件夹按钮 */}
        {!showNewFolderInput ? (
          <button
            onClick={() => setShowNewFolderInput(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all hover-lift"
            style={{
              background: 'rgba(74, 169, 255, 0.15)',
              border: '1px solid var(--color-border-blue)',
              color: 'var(--color-blue-deep)',
            }}
          >
            <span>+</span>
            <span>新建文件夹</span>
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreateFolder()}
              placeholder="文件夹名称"
              className="input w-40"
              autoFocus
            />
            <button
              onClick={handleCreateFolder}
              className="px-3 py-2 rounded-lg text-sm font-medium transition-all hover-lift"
              style={{
                background: 'var(--color-pink-primary)',
                color: 'white',
              }}
            >
              创建
            </button>
            <button
              onClick={() => {
                setShowNewFolderInput(false);
                setNewFolderName('');
              }}
              className="px-3 py-2 rounded-lg text-sm font-medium transition-all hover-lift"
              style={{
                background: 'rgba(74, 169, 255, 0.15)',
                color: 'var(--color-blue-deep)',
              }}
            >
              取消
            </button>
          </div>
        )}
      </header>

      {/* 主内容区 */}
      <div className="relative z-10 flex-1 flex overflow-hidden">
        {/* 左侧对话列表 */}
        <div className="w-80 shrink-0 border-r overflow-y-auto p-4" style={{ borderColor: 'rgba(74, 169, 255, 0.2)' }}>
          {loading ? (
            <LoadingState />
          ) : error ? (
            <ErrorState error={error} onRetry={loadConversations} />
          ) : (
            <div className="space-y-4">
              {/* 文件夹列表 */}
              {folders.map((folder) => (
                <FolderItem
                  key={folder.id}
                  folder={folder}
                  onToggle={() => toggleFolder(folder.id)}
                  onDelete={() => handleDeleteFolder(folder.id)}
                  onEdit={() => startEditFolder(folder)}
                  editingFolderId={editingFolderId}
                  editingFolderName={editingFolderName}
                  onEditingNameChange={setEditingFolderName}
                  onSaveEdit={saveEditFolder}
                  onCancelEdit={() => setEditingFolderId(null)}
                  onMoveConversation={moveConversation}
                  onSelectConversation={handleSelectConversation}
                  onStartConversation={handleStartConversation}
                  unfoldered={unfoldered}
                />
              ))}

              {/* 未分类对话 */}
              {unfoldered.length > 0 && (
                <div>
                  <div
                    className="text-xs font-semibold uppercase tracking-wider mb-2 px-2"
                    style={{ color: 'var(--color-blue-deep)', opacity: 0.6 }}
                  >
                    未分类 ({unfoldered.length})
                  </div>
                  {unfoldered.map((conv) => (
                    <ConversationItem
                      key={conv.thread_id}
                      conversation={conv}
                      onSelect={() => handleSelectConversation(conv)}
                      onStart={() => handleStartConversation(conv)}
                      folders={folders}
                      onMoveToFolder={(folderId) => moveConversation(conv.thread_id, folderId)}
                      selected={selectedConversation?.thread_id === conv.thread_id}
                    />
                  ))}
                </div>
              )}

              {/* 空状态 */}
              {folders.length === 0 && unfoldered.length === 0 && (
                <EmptyState />
              )}
            </div>
          )}
        </div>

        {/* 右侧详情/长期记忆编辑区 */}
        <div className="flex-1 overflow-y-auto p-6">
          {selectedConversation ? (
            <MemoryEditor conversation={selectedConversation} />
          ) : (
            <div
              className="h-full flex flex-col items-center justify-center"
              style={{ color: 'var(--color-blue-deep)', opacity: 0.5 }}
            >
              <div className="text-4xl mb-4">📋</div>
              <div className="text-sm">选择一个对话查看详情</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// 文件夹项组件
function FolderItem({
  folder,
  onToggle,
  onDelete,
  onEdit,
  editingFolderId,
  editingFolderName,
  onEditingNameChange,
  onSaveEdit,
  onCancelEdit,
  onMoveConversation,
  onSelectConversation,
  onStartConversation,
  unfoldered,
}: {
  folder: ConversationFolder;
  onToggle: () => void;
  onDelete: () => void;
  onEdit: () => void;
  editingFolderId: string | null;
  editingFolderName: string;
  onEditingNameChange: (name: string) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onMoveConversation: (conversationId: string, folderId: string | null) => void;
  onSelectConversation: (conv: Conversation) => void;
  onStartConversation: (conv: Conversation) => void;
  unfoldered: Conversation[];
}) {
  const isEditing = editingFolderId === folder.id;

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{
        background: 'rgba(255, 255, 255, 0.7)',
        border: '1px solid var(--color-border-blue)',
      }}
    >
      {/* 文件夹标题栏 */}
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer"
        onClick={onToggle}
        style={{ background: 'rgba(74, 169, 255, 0.1)' }}
      >
        <span
          className="text-xs transition-transform"
          style={{ transform: folder.expanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
        >
          ▶
        </span>

        {isEditing ? (
          <input
            type="text"
            value={editingFolderName}
            onChange={(e) => onEditingNameChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onSaveEdit();
              if (e.key === 'Escape') onCancelEdit();
            }}
            onBlur={onSaveEdit}
            className="input flex-1 h-7 text-sm"
            autoFocus
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <>
            <span className="text-sm font-semibold flex-1" style={{ color: 'var(--color-blue-deep)' }}>
              📁 {folder.name}
            </span>
            <span className="text-xs px-2 py-0.5 rounded" style={{ background: 'rgba(74, 169, 255, 0.2)', color: 'var(--color-blue-deep)' }}>
              {folder.conversations.length}
            </span>
          </>
        )}

        {!isEditing && (
          <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={onEdit}
              className="w-6 h-6 rounded flex items-center justify-center text-xs transition-all hover-scale"
              style={{ color: 'var(--color-blue-deep)', opacity: 0.6 }}
            >
              ✏
            </button>
            <button
              onClick={onDelete}
              className="w-6 h-6 rounded flex items-center justify-center text-xs transition-all hover-scale"
              style={{ color: '#e53e3e', opacity: 0.6 }}
            >
              ✕
            </button>
          </div>
        )}
      </div>

      {/* 文件夹内对话 */}
      {folder.expanded && folder.conversations.length > 0 && (
        <div className="p-2 space-y-1">
          {folder.conversations.map((conv) => (
            <ConversationItem
              key={conv.thread_id}
              conversation={conv}
              onSelect={() => onSelectConversation(conv)}
              onStart={() => onStartConversation(conv)}
              folders={[]}
              onMoveToFolder={() => onMoveConversation(conv.thread_id, null)}
              selected={false}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// 对话项组件
function ConversationItem({
  conversation,
  onSelect,
  onStart,
  folders,
  onMoveToFolder,
  selected,
}: {
  conversation: Conversation;
  onSelect: () => void;
  onStart: () => void;
  folders: ConversationFolder[];
  onMoveToFolder: (folderId: string | null) => void;
  selected: boolean;
}) {
  const [showMenu, setShowMenu] = useState(false);

  return (
    <div
      className={`rounded-lg p-3 cursor-pointer transition-all hover-lift ${selected ? 'ring-2' : ''}`}
      style={{
        background: selected ? 'rgba(255, 145, 164, 0.15)' : 'rgba(255, 255, 255, 0.6)',
        border: `1px solid ${selected ? 'var(--color-pink-primary)' : 'transparent'}`,
      }}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div
            className="text-sm font-medium truncate"
            style={{ color: 'var(--color-blue-deep)' }}
          >
            {conversation.title || '未命名对话'}
          </div>
          <div
            className="text-xs mt-1 truncate opacity-60"
            style={{ color: 'var(--color-blue-deep)' }}
          >
            {conversation.summary || '暂无摘要'}
          </div>
          <div
            className="text-xs mt-1"
            style={{ color: 'var(--color-blue-deep)', opacity: 0.4 }}
          >
            {conversation.updated_at
              ? new Date(conversation.updated_at).toLocaleDateString('zh-CN')
              : '无更新'}
          </div>
        </div>

        {/* 操作菜单 */}
        <div className="relative">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setShowMenu((v) => !v);
            }}
            className="w-6 h-6 rounded flex items-center justify-center text-xs transition-all hover-scale"
            style={{ color: 'var(--color-blue-deep)', opacity: 0.6 }}
          >
            ⋮
          </button>

          {showMenu && (
            <div
              className="absolute right-0 top-full mt-1 py-1 rounded-lg shadow-lg z-20 min-w-32"
              style={{
                background: 'rgba(255, 255, 255, 0.98)',
                border: '1px solid var(--color-border-blue)',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={() => {
                  onStart();
                  setShowMenu(false);
                }}
                className="w-full px-3 py-2 text-left text-sm hover-lift transition-all"
                style={{ color: 'var(--color-blue-deep)' }}
              >
                继续对话
              </button>
              {folders.length > 0 && (
                <div className="relative group">
                  <button
                    className="w-full px-3 py-2 text-left text-sm hover-lift transition-all flex items-center justify-between"
                    style={{ color: 'var(--color-blue-deep)' }}
                  >
                    移入文件夹 ▸
                  </button>
                  <div
                    className="hidden group-hover:block absolute left-full top-0 ml-1 py-1 rounded-lg shadow-lg min-w-32"
                    style={{
                      background: 'rgba(255, 255, 255, 0.98)',
                      border: '1px solid var(--color-border-blue)',
                    }}
                  >
                    {folders.map((folder) => (
                      <button
                        key={folder.id}
                        onClick={() => {
                          onMoveToFolder(folder.id);
                          setShowMenu(false);
                        }}
                        className="w-full px-3 py-2 text-left text-sm hover-lift transition-all"
                        style={{ color: 'var(--color-blue-deep)' }}
                      >
                        📁 {folder.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <button
                onClick={() => {
                  onMoveToFolder(null);
                  setShowMenu(false);
                }}
                className="w-full px-3 py-2 text-left text-sm hover-lift transition-all"
                style={{ color: 'var(--color-blue-deep)' }}
              >
                移出文件夹
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// 长期记忆编辑面板
function MemoryEditor({ conversation }: { conversation: Conversation }) {
  const [memory, setMemory] = useState(conversation.summary || '');
  const [saving, setSaving] = useState(false);

  const handleSave = useCallback(async () => {
    setSaving(true);
    // TODO: 调用 API 保存长期记忆
    await new Promise((r) => setTimeout(r, 500));
    setSaving(false);
  }, [memory]);

  return (
    <div className="max-w-2xl">
      <h2
        className="text-lg font-bold mb-4"
        style={{ color: 'var(--color-blue-deep)' }}
      >
        干员档案
      </h2>

      <div
        className="rounded-xl p-6 mb-4"
        style={{
          background: 'rgba(255, 255, 255, 0.85)',
          border: '1px solid var(--color-border-blue)',
          borderLeft: '4px solid var(--color-pink-primary)',
        }}
      >
        <div className="mb-4">
          <label
            className="text-xs font-semibold uppercase tracking-wider mb-2 block"
            style={{ color: 'var(--color-pink-primary)' }}
          >
            对话标题
          </label>
          <div
            className="text-lg font-bold"
            style={{ color: 'var(--color-blue-deep)' }}
          >
            {conversation.title || '未命名对话'}
          </div>
        </div>

        <div className="mb-4">
          <label
            className="text-xs font-semibold uppercase tracking-wider mb-2 block"
            style={{ color: 'var(--color-pink-primary)' }}
          >
            创建时间
          </label>
          <div style={{ color: 'var(--color-blue-deep)', opacity: 0.7 }}>
            {conversation.created_at
              ? new Date(conversation.created_at).toLocaleString('zh-CN')
              : '未知'}
          </div>
        </div>

        <div className="mb-4">
          <label
            className="text-xs font-semibold uppercase tracking-wider mb-2 block"
            style={{ color: 'var(--color-pink-primary)' }}
          >
            最后更新
          </label>
          <div style={{ color: 'var(--color-blue-deep)', opacity: 0.7 }}>
            {conversation.updated_at
              ? new Date(conversation.updated_at).toLocaleString('zh-CN')
              : '未知'}
          </div>
        </div>
      </div>

      <div
        className="rounded-xl p-6"
        style={{
          background: 'rgba(255, 255, 255, 0.85)',
          border: '1px solid var(--color-border-blue)',
        }}
      >
        <label
          className="text-xs font-semibold uppercase tracking-wider mb-2 block"
          style={{ color: 'var(--color-pink-primary)' }}
        >
          长期记忆
        </label>
        <p
          className="text-xs mb-3"
          style={{ color: 'var(--color-blue-deep)', opacity: 0.6 }}
        >
          编辑这段对话的核心记忆，用于在后续对话中保持上下文连贯性
        </p>
        <textarea
          value={memory}
          onChange={(e) => setMemory(e.target.value)}
          placeholder="输入长期记忆内容..."
          className="input textarea w-full h-40"
        />
        <div className="flex justify-end mt-3">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 rounded-lg text-sm font-medium transition-all hover-lift disabled:opacity-50"
            style={{
              background: 'var(--color-pink-primary)',
              color: 'white',
            }}
          >
            {saving ? '保存中...' : '保存记忆'}
          </button>
        </div>
      </div>
    </div>
  );
}

// 加载状态
function LoadingState() {
  return (
    <div className="flex items-center justify-center py-12">
      <div
        className="w-8 h-8 border-2 rounded-full animate-spin"
        style={{ borderColor: 'var(--color-pink-primary)', borderTopColor: 'transparent' }}
      />
    </div>
  );
}

// 错误状态
function ErrorState({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div className="text-center py-8">
      <div className="text-3xl mb-3">⚠️</div>
      <div className="text-sm mb-3" style={{ color: '#e53e3e' }}>
        {error}
      </div>
      <button
        onClick={onRetry}
        className="px-4 py-2 rounded-lg text-sm font-medium transition-all hover-lift"
        style={{
          background: 'rgba(74, 169, 255, 0.15)',
          color: 'var(--color-blue-deep)',
        }}
      >
        重试
      </button>
    </div>
  );
}

// 空状态
function EmptyState() {
  return (
    <div
      className="text-center py-12"
      style={{ color: 'var(--color-blue-deep)', opacity: 0.5 }}
    >
      <div className="text-4xl mb-4">📭</div>
      <div className="text-sm">暂无对话记录</div>
      <div className="text-xs mt-2">开始聊天以创建新对话</div>
    </div>
  );
}
