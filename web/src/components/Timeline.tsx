import { useState, useCallback, useMemo } from 'react';

export interface TimelineNode {
  messageId: string;
  role: 'user' | 'assistant';
  timestamp: number;
  prompt?: string;
  content: string;
}

interface TimelineProps {
  nodes: TimelineNode[];
  currentNodeId?: string | null;
  onNodeClick?: (node: TimelineNode) => void;
}

export function Timeline({ nodes, currentNodeId, onNodeClick }: TimelineProps) {
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  const hoveredNode = useMemo(
    () => nodes.find((n) => n.messageId === hoveredNodeId) ?? null,
    [nodes, hoveredNodeId]
  );

  const handleNodeClick = useCallback(
    (node: TimelineNode) => {
      onNodeClick?.(node);
    },
    [onNodeClick]
  );

  if (nodes.length === 0) {
    return null;
  }

  return (
    <div className="relative h-full w-12 shrink-0">
      {/* 时间轴线 */}
      <div
        className="absolute left-1/2 top-4 bottom-4 w-0.5 -translate-x-1/2"
        style={{
          background: 'linear-gradient(180deg, var(--color-pink-primary), var(--color-blue-light), var(--color-pink-primary))',
        }}
      />

      {/* 节点列表 */}
      <div className="relative flex flex-col items-center gap-4 py-4">
        {nodes.map((node, index) => {
          const isHovered = hoveredNodeId === node.messageId;
          const isCurrent = currentNodeId === node.messageId;
          const isUser = node.role === 'user';

          return (
            <div
              key={node.messageId}
              className="relative group"
              onMouseEnter={() => setHoveredNodeId(node.messageId)}
              onMouseLeave={() => setHoveredNodeId(null)}
              onClick={() => handleNodeClick(node)}
            >
              {/* 节点圆点 */}
              <div
                className={`w-3 h-3 rounded-full cursor-pointer transition-all ${
                  isCurrent ? 'animate-pulse' : ''
                } ${isHovered ? 'scale-150' : ''}`}
                style={{
                  background: isUser
                    ? 'var(--color-blue-light)'
                    : 'var(--color-pink-primary)',
                  boxShadow: isHovered
                    ? '0 0 12px rgba(255, 145, 164, 0.5)'
                    : isCurrent
                    ? '0 0 8px rgba(255, 145, 164, 0.3)'
                    : 'none',
                  border: `2px solid ${isHovered ? 'white' : 'transparent'}`,
                }}
              />

              {/* 悬停提示（GitLens 风格） */}
              {isHovered && hoveredNode && (
                <div
                  className="absolute left-full top-1/2 -translate-y-1/2 ml-3 w-64 p-3 rounded-xl shadow-lg z-50 animate-spring"
                  style={{
                    background: 'rgba(255, 255, 255, 0.98)',
                    border: '1px solid var(--color-border-blue)',
                    backdropFilter: 'blur(10px)',
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  {/* 角色标识 */}
                  <div className="flex items-center gap-2 mb-2">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{
                        background: isUser
                          ? 'var(--color-blue-light)'
                          : 'var(--color-pink-primary)',
                      }}
                    />
                    <span
                      className="text-xs font-semibold"
                      style={{ color: 'var(--color-blue-deep)' }}
                    >
                      {isUser ? '你' : '珞樱'}
                    </span>
                    <span
                      className="text-xs"
                      style={{ color: 'var(--color-blue-deep)', opacity: 0.5 }}
                    >
                      #{index + 1}
                    </span>
                  </div>

                  {/* 内容预览 */}
                  <div
                    className="text-xs mb-2 line-clamp-3"
                    style={{ color: 'var(--color-blue-deep)', opacity: 0.8 }}
                  >
                    {node.content.slice(0, 100)}
                    {node.content.length > 100 ? '...' : ''}
                  </div>

                  {/* Prompt（如果存在） */}
                  {node.prompt && (
                    <div
                      className="mt-2 p-2 rounded-lg text-xs"
                      style={{
                        background: 'rgba(74, 169, 255, 0.1)',
                        border: '1px solid var(--color-border-blue)',
                      }}
                    >
                      <div
                        className="text-xs font-semibold mb-1"
                        style={{ color: 'var(--color-pink-primary)' }}
                      >
                        Prompt
                      </div>
                      <div
                        className="text-xs line-clamp-2"
                        style={{ color: 'var(--color-blue-deep)', opacity: 0.7 }}
                      >
                        {node.prompt}
                      </div>
                    </div>
                  )}

                  {/* 时间戳 */}
                  <div
                    className="text-xs mt-2"
                    style={{ color: 'var(--color-blue-deep)', opacity: 0.4 }}
                  >
                    {new Date(node.timestamp).toLocaleTimeString('zh-CN', {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </div>

                  {/* 指向箭头 */}
                  <div
                    className="absolute left-0 top-1/2 -translate-x-full -translate-y-1/2 w-0 h-0"
                    style={{
                      borderTop: '6px solid transparent',
                      borderBottom: '6px solid transparent',
                      borderRight: '6px solid var(--color-border-blue)',
                    }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// 简化版时间轴（用于消息列表左侧）
export function MiniTimeline({ nodes }: { nodes: TimelineNode[] }) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  if (nodes.length === 0) {
    return null;
  }

  return (
    <div className="flex items-center gap-1">
      {nodes.map((node, index) => {
        const isHovered = hoveredIndex === index;
        const isUser = node.role === 'user';

        return (
          <div
            key={node.messageId}
            className="relative"
            onMouseEnter={() => setHoveredIndex(index)}
            onMouseLeave={() => setHoveredIndex(null)}
          >
            <div
              className={`w-2 h-2 rounded-full transition-all ${isHovered ? 'scale-125' : ''}`}
              style={{
                background: isUser
                  ? 'var(--color-blue-light)'
                  : 'var(--color-pink-primary)',
                opacity: isHovered ? 1 : 0.5,
              }}
            />

            {/* 悬停提示 */}
            {isHovered && (
              <div
                className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 rounded text-xs whitespace-nowrap shadow-lg z-50"
                style={{
                  background: 'rgba(255, 255, 255, 0.95)',
                  border: '1px solid var(--color-border-blue)',
                  color: 'var(--color-blue-deep)',
                }}
              >
                {isUser ? '你' : '珞樱'} · #{index + 1}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// 时间轴控制器（管理节点状态）
export function useTimelineController() {
  const [nodes, setNodes] = useState<TimelineNode[]>([]);
  const [currentIndex, setCurrentIndex] = useState<number | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  // 添加节点
  const addNode = useCallback(
    (node: Omit<TimelineNode, 'messageId'>) => {
      const messageId = `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      setNodes((prev) => [...prev, { ...node, messageId }]);
      setCurrentIndex(nodes.length); // 指向新添加的节点
    },
    [nodes.length]
  );

  // 从消息列表生成节点
  const syncFromMessages = useCallback(
    (messages: Array<{
      id: string;
      role: 'user' | 'assistant';
      content: string;
      timestamp: number;
      prompt?: string;
    }>) => {
      setNodes(
        messages.map((msg) => ({
          messageId: msg.id,
          role: msg.role,
          timestamp: msg.timestamp,
          content: msg.content,
          prompt: msg.prompt,
        }))
      );
    },
    []
  );

  // 清除所有节点
  const clear = useCallback(() => {
    setNodes([]);
    setCurrentIndex(null);
    setHoveredNodeId(null);
  }, []);

  // 获取当前节点
  const currentNode = currentIndex !== null ? nodes[currentIndex] ?? null : null;

  return {
    nodes,
    currentIndex,
    currentNode,
    hoveredNodeId,
    addNode,
    syncFromMessages,
    clear,
    setCurrentIndex,
    setHoveredNodeId,
  };
}
