import { useState, useEffect } from 'react';
import { api } from '../api/client';
import type { Conversation } from '../types';

interface ConversationListProps {
  activeId: string;
  onSelect: (id: string) => void;
}

export function ConversationList({ activeId, onSelect }: ConversationListProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listConversations(50, 0, false)
      .then((data) => {
        setConversations(data.conversations);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleNew = async () => {
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
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await api.deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.thread_id !== id));
      if (activeId === id) onSelect('web-session');
    } catch (err) {
      console.error('Failed to delete conversation:', err);
    }
  };

  return (
    <div className="space-y-1 p-2">
      <button
        onClick={handleNew}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-colors"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
        新对话
      </button>

      {loading && (
        <div className="px-3 py-2 text-xs text-gray-400">加载中...</div>
      )}

      {!loading && conversations.length === 0 && (
        <div className="px-3 py-2 text-xs text-gray-400">暂无对话</div>
      )}

      {conversations.map((conv) => (
        <div
          key={conv.thread_id}
          onClick={() => onSelect(conv.thread_id)}
          className={`group flex items-center gap-2 px-3 py-2 rounded-lg text-sm cursor-pointer transition-colors ${
            conv.thread_id === activeId
              ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
              : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
          }`}
        >
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          <span className="flex-1 truncate">{conv.title || '无标题对话'}</span>
          <button
            onClick={(e) => handleDelete(e, conv.thread_id)}
            className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-100 dark:hover:bg-red-900/30 transition-opacity"
            aria-label="Delete conversation"
          >
            <svg className="w-3.5 h-3.5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      ))}
    </div>
  );
}