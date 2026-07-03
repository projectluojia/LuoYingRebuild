import { useState, useCallback, useMemo } from 'react';

export interface TimelineNode {
  messageId: string;
  role: 'user' | 'assistant';
  timestamp: number;
  prompt?: string; // 用于追溯的提示词
  content: string;
}

export interface ConversationFolder {
  id: string;
  name: string;
  conversations: Conversation[];
  expanded?: boolean;
  createdAt: string;
}

export interface Branch {
  id: string;
  parentId: string;
  conversationId: string;
  title: string;
  createdAt: string;
}

export interface Conversation {
  thread_id: string;
  title: string;
  summary: string;
  summarized_message_count: number;
  archived: boolean;
  created_at: string | null;
  updated_at: string | null;
  user_id?: string;
  user_name?: string;
  platform?: string;
  channel_type?: string;
  conversation_id?: string;
  folderId?: string; // 所属文件夹
  branchId?: string; // 分支ID
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  attachments?: Attachment[];
  prompt?: string; // 时间轴追溯用
}

export interface Attachment {
  id: string;
  name: string;
  type: 'image' | 'file';
  url?: string;
}

export interface ChatRequest {
  text: string;
  session_id?: string;
  image_ids?: string[];
  file_ids?: string[];
}

export interface ChatResponse {
  reply: string;
}

export interface ConversationListResponse {
  conversations: Conversation[];
}

export interface VoiceConfig {
  stt_enabled: boolean;
  tts_enabled: boolean;
}

/**
 * 时间轴数据 Hook
 * 管理消息列表并生成时间轴节点
 */
export function useTimeline() {
  const [nodes, setNodes] = useState<TimelineNode[]>([]);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  // 添加节点
  const addNode = useCallback((node: Omit<TimelineNode, 'messageId'>) => {
    const messageId = `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    setNodes((prev) => [...prev, { ...node, messageId }]);
  }, []);

  // 批量添加节点（用于加载历史消息）
  const setNodesFromMessages = useCallback((messages: Message[]) => {
    setNodes(
      messages.map((msg) => ({
        messageId: msg.id,
        role: msg.role,
        timestamp: msg.timestamp,
        content: msg.content,
        prompt: msg.prompt,
      }))
    );
  }, []);

  // 清除节点
  const clearNodes = useCallback(() => {
    setNodes([]);
    setHoveredNodeId(null);
  }, []);

  // 获取悬停节点
  const hoveredNode = useMemo(
    () => nodes.find((n) => n.messageId === hoveredNodeId) ?? null,
    [nodes, hoveredNodeId]
  );

  return {
    nodes,
    hoveredNodeId,
    hoveredNode,
    addNode,
    setNodesFromMessages,
    clearNodes,
    setHoveredNodeId,
  };
}

/**
 * 对话文件夹管理 Hook
 */
export function useConversationFolders() {
  const [folders, setFolders] = useState<ConversationFolder[]>([]);
  const [unfoldered, setUnfoldered] = useState<Conversation[]>([]);

  // 创建文件夹
  const createFolder = useCallback((name: string) => {
    const folder: ConversationFolder = {
      id: `folder-${Date.now()}`,
      name,
      conversations: [],
      expanded: true,
      createdAt: new Date().toISOString(),
    };
    setFolders((prev) => [...prev, folder]);
    return folder;
  }, []);

  // 删除文件夹
  const deleteFolder = useCallback((folderId: string) => {
    setFolders((prev) => {
      const folder = prev.find((f) => f.id === folderId);
      if (folder) {
        // 将文件夹中的对话移回未分类
        setUnfoldered((u) => [...u, ...folder.conversations]);
      }
      return prev.filter((f) => f.id !== folderId);
    });
  }, []);

  // 重命名文件夹
  const renameFolder = useCallback((folderId: string, newName: string) => {
    setFolders((prev) =>
      prev.map((f) => (f.id === folderId ? { ...f, name: newName } : f))
    );
  }, []);

  // 切换文件夹展开状态
  const toggleFolder = useCallback((folderId: string) => {
    setFolders((prev) =>
      prev.map((f) =>
        f.id === folderId ? { ...f, expanded: !f.expanded } : f
      )
    );
  }, []);

  // 将对话移入文件夹
  const moveToFolder = useCallback((conversationId: string, folderId: string | null) => {
    setFolders((prev) => {
      // 从所有文件夹中移除
      const cleaned = prev.map((f) => ({
        ...f,
        conversations: f.conversations.filter((c) => c.thread_id !== conversationId),
      }));

      if (folderId) {
        // 添加到目标文件夹
        const folder = cleaned.find((f) => f.id === folderId);
        const conversation = unfoldered.find((c) => c.thread_id === conversationId)
          ?? cleaned.flatMap((f) => f.conversations).find((c) => c.thread_id === conversationId);
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
      // 移出文件夹到未分类
      setUnfoldered((prev) => {
        const conversation = folders
          .flatMap((f) => f.conversations)
          .find((c) => c.thread_id === conversationId);
        if (conversation) {
          return [...prev, { ...conversation, folderId: undefined }];
        }
        return prev;
      });
    }
  }, [folders, unfoldered]);

  // 设置未分类对话
  const setUnfolderedConversations = useCallback((convs: Conversation[]) => {
    setUnfoldered(convs);
  }, []);

  // 设置文件夹
  const setFolderedConversations = useCallback((newFolders: ConversationFolder[]) => {
    setFolders(newFolders);
  }, []);

  return {
    folders,
    unfoldered,
    createFolder,
    deleteFolder,
    renameFolder,
    toggleFolder,
    moveToFolder,
    setUnfolderedConversations,
    setFolderedConversations,
  };
}
