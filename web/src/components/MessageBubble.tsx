import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import rehypeRaw from 'rehype-raw';
import type { Attachment } from '../types';

interface MessageBubbleProps {
  role: 'user' | 'assistant';
  content: string;
  attachments?: Attachment[];
  isStreaming?: boolean;
}

export function MessageBubble({ role, content, attachments, isStreaming }: MessageBubbleProps) {
  const isUser = role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} animate-spring`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 ${
          isUser
            ? 'rounded-br-md'
            : 'rounded-bl-md'
        }`}
        style={{
          background: isUser
            ? 'linear-gradient(135deg, var(--color-blue-light) 0%, #6bbfff 100%)'
            : 'linear-gradient(135deg, rgba(255, 255, 255, 0.95) 0%, rgba(232, 243, 255, 0.90) 100%)',
          color: isUser ? 'white' : 'var(--color-blue-deep)',
          boxShadow: isUser
            ? '-4px 4px 15px rgba(74, 169, 255, 0.35)'
            : 'var(--shadow-panel-sm)',
          border: isUser
            ? 'none'
            : '1px solid rgba(74, 169, 255, 0.15)',
          borderLeft: isUser ? 'none' : '3px solid var(--color-pink-primary)',
        }}
      >
        {/* Attachments for user messages */}
        {isUser && attachments && attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {attachments.map((att) => (
              <div
                key={att.id}
                className="relative rounded-lg overflow-hidden"
                style={{ maxWidth: 120, maxHeight: 120 }}
              >
                {att.type === 'image' && att.url ? (
                  <img
                    src={att.url}
                    alt={att.name}
                    className="w-full h-full object-cover"
                    style={{ maxWidth: 120, maxHeight: 120 }}
                  />
                ) : (
                  <div
                    className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs"
                    style={{
                      background: 'rgba(255,255,255,0.2)',
                      color: 'white',
                    }}
                  >
                    <span>📎</span>
                    <span className="truncate max-w-[80px]">{att.name}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Message content */}
        {isUser ? (
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{content}</p>
        ) : (
          <div className="prose prose-sm max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeHighlight, rehypeRaw]}
            >
              {content}
            </ReactMarkdown>
            {isStreaming && (
              <span className="inline-block ml-1 animate-pulse" style={{ color: 'var(--color-pink-primary)' }}>▌</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
