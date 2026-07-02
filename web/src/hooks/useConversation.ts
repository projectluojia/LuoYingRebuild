import { useState, useCallback, useRef } from 'react';
import { api } from '../api/client';
import type { Message, Attachment } from '../types';

export interface UseConversationOptions {
  onTrack?: (text: string | null) => void;
}

export function useConversation(initialSessionId = 'web-session', options: UseConversationOptions = {}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId] = useState(initialSessionId);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (text: string, attachments?: Attachment[]) => {
      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
        timestamp: Date.now(),
        attachments,
      };
      setMessages((prev) => [...prev, userMsg]);

      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setError(null);
      setIsStreaming(true);
      options.onTrack?.(null);

      abortRef.current = new AbortController();

      const image_ids = attachments?.filter((a) => a.type === 'image').map((a) => a.id);
      const file_ids = attachments?.filter((a) => a.type === 'file').map((a) => a.id);

      await new Promise<void>((resolve) => {
        api.chatStream(
          { text, session_id: sessionId, image_ids, file_ids },
          (chunk) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsg.id
                  ? { ...m, content: m.content + chunk }
                  : m
              )
            );
          },
          () => {
            setIsStreaming(false);
            options.onTrack?.(null);
            resolve();
          },
          (err) => {
            setError(err.message);
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsg.id
                  ? { ...m, content: '[Error: ' + err.message + ']' }
                  : m
              )
            );
            setIsStreaming(false);
            options.onTrack?.(null);
            resolve();
          },
          (text) => {
            options.onTrack?.(text);
          }
        );
      });
    },
    [sessionId, options]
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return { messages, isStreaming, error, sendMessage, clearMessages };
}