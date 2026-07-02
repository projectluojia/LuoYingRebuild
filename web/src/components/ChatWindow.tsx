import { useState, useRef, useEffect } from 'react';
import { MessageBubble } from './MessageBubble';
import { VoiceButton } from './VoiceButton';
import { api } from '../api/client';
import type { Message, Attachment } from '../types';

interface ChatWindowProps {
  messages: Message[];
  isStreaming: boolean;
  onSend: (text: string, attachments?: Attachment[]) => void;
}

export function ChatWindow({ messages, isStreaming, onSend }: ChatWindowProps) {
  const [input, setInput] = useState('');
  const [pendingAttachments, setPendingAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<string>('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput('');
    const attachments = pendingAttachments.length > 0 ? [...pendingAttachments] : undefined;
    setPendingAttachments([]);
    onSend(text, attachments);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = 'auto';
      ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
    }
  };

  const handleFileUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    setUploadProgress('');

    const newAttachments: Attachment[] = [];

    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        setUploadProgress(`上传中 ${i + 1}/${files.length}: ${file.name}`);
        const isImage = file.type.startsWith('image/');
        const result = isImage
          ? await api.uploadImage(file)
          : await api.uploadFile(file);
        newAttachments.push({
          id: isImage ? (result as { image_id: string }).image_id : (result as { file_id: string }).file_id,
          name: result.file_name,
          type: isImage ? 'image' : 'file',
          url: result.url,
        });
      }
      setPendingAttachments((prev) => [...prev, ...newAttachments]);
    } catch (err) {
      console.error('Upload failed:', err);
      setUploadProgress(`上传失败: ${(err as Error).message}`);
      setTimeout(() => setUploadProgress(''), 3000);
    } finally {
      setUploading(false);
      setUploadProgress('');
    }
  };

  const removeAttachment = (id: string) => {
    setPendingAttachments((prev) => prev.filter((a) => a.id !== id));
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            开始聊天吧
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            role={msg.role}
            content={msg.content}
            attachments={msg.attachments}
            isStreaming={isStreaming && msg.id === messages[messages.length - 1].id && msg.role === 'assistant'}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <form onSubmit={handleSubmit} className="border-t border-gray-200 dark:border-gray-700 p-4 space-y-3">
        {/* Pending attachments preview */}
        {pendingAttachments.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {pendingAttachments.map((att) => (
              <div
                key={att.id}
                className="relative group flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs"
                style={{
                  background: 'rgba(74, 169, 255, 0.12)',
                  border: '1px solid rgba(74, 169, 255, 0.3)',
                }}
              >
                <span className="text-base">
                  {att.type === 'image' ? '🖼️' : '📎'}
                </span>
                <span className="max-w-[100px] truncate" style={{ color: 'var(--color-blue-deep)' }}>
                  {att.name}
                </span>
                <button
                  type="button"
                  onClick={() => removeAttachment(att.id)}
                  className="ml-1 w-4 h-4 rounded-full flex items-center justify-center opacity-50 hover:opacity-100 transition-opacity"
                  style={{ background: 'rgba(0,0,0,0.1)' }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Upload progress */}
        {uploadProgress && (
          <div className="text-xs animate-pulse" style={{ color: 'var(--color-blue-deep)', opacity: 0.7 }}>
            {uploadProgress}
          </div>
        )}

        {/* Text input row */}
        <div className="flex items-end gap-3">
          {/* Attach button */}
          <div className="shrink-0 flex items-end">
            <div className="relative">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isStreaming || uploading}
                className="w-10 h-10 rounded-xl flex items-center justify-center transition-all hover:scale-105 disabled:opacity-40"
                style={{
                  background: 'rgba(74, 169, 255, 0.12)',
                  border: '1px solid rgba(74, 169, 255, 0.3)',
                  color: 'var(--color-blue-deep)',
                }}
                title="添加文件"
              >
                📎
              </button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={(e) => handleFileUpload(e.target.files)}
                accept="image/*,.pdf,.doc,.docx,.txt,.md,.csv,.json,.yaml,.yml,.py,.ts,.tsx,.js,.jsx,.java,.zip,.tar,.gz"
              />
              {/* Image sub-button */}
              <button
                type="button"
                onClick={() => imageInputRef.current?.click()}
                disabled={isStreaming || uploading}
                className="absolute -bottom-1 -right-1 w-5 h-5 rounded-full flex items-center justify-center text-xs shadow-sm transition-all hover:scale-110 disabled:opacity-40"
                style={{
                  background: 'var(--color-pink-primary)',
                  color: 'white',
                }}
                title="添加图片"
              >
                +
              </button>
              <input
                ref={imageInputRef}
                type="file"
                multiple
                accept="image/*"
                className="hidden"
                onChange={(e) => handleFileUpload(e.target.files)}
              />
            </div>
          </div>

          {/* Voice button */}
          <VoiceButton
            className="shrink-0"
            onTranscript={(text) => {
              setInput(prev => prev ? `${prev} ${text}` : text);
              textareaRef.current?.focus();
            }}
          />

          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleTextareaChange}
            onKeyDown={handleKeyDown}
            placeholder="输入消息..."
            rows={1}
            className="flex-1 resize-none rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-4 py-2.5 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={isStreaming}
          />
          <button
            type="submit"
            disabled={(!input.trim() && pendingAttachments.length === 0) || isStreaming || uploading}
            className="shrink-0 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isStreaming ? '...' : '发送'}
          </button>
        </div>

        {/* Keyboard hint */}
        {pendingAttachments.length === 0 && !input && (
          <div className="flex items-center justify-between px-1">
            <span className="text-xs opacity-40" style={{ color: 'var(--color-blue-deep)' }}>
              Shift+Enter 换行 · Enter 发送
            </span>
            <span className="text-xs opacity-40" style={{ color: 'var(--color-blue-deep)' }}>
              📎 上传文件 · 🖼️ 上传图片
            </span>
          </div>
        )}
      </form>
    </div>
  );
}