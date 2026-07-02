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
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${
          isUser
            ? 'bg-blue-600 text-white rounded-br-md'
            : 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-bl-md'
        }`}
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
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeHighlight, rehypeRaw]}
            >
              {content}
            </ReactMarkdown>
            {isStreaming && (
              <span className="inline-block ml-1 animate-pulse">▌</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
