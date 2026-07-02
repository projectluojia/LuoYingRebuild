import type { ChatRequest, ChatResponse, ConversationListResponse, VoiceConfig } from '../types';

export const API_BASE = '/api';

export interface UploadImageResponse {
  image_id: string;
  file_name: string;
  content_type: string;
  size: number;
  url: string;
}

export interface UploadFileResponse {
  file_id: string;
  file_name: string;
  content_type: string;
  size: number;
  url: string;
}

export interface WorkspaceNode {
  name: string;
  path: string;
  type: 'directory' | 'file';
  children?: WorkspaceNode[];
  size?: number;
  modified_at?: number | null;
  url?: string;
}

export interface WorkspaceTreeResponse {
  user_id: string;
  root: WorkspaceNode;
}

export const api = {
  async health() {
    const res = await fetch(`${API_BASE}/health`);
    return res.json();
  },

  async chat(request: ChatRequest): Promise<ChatResponse> {
    const res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    if (!res.ok) throw new Error(`Chat failed: ${res.statusText}`);
    return res.json();
  },

  async chatStream(
    request: ChatRequest,
    onChunk: (text: string) => void,
    onDone: () => void,
    onError: (err: Error) => void,
    onTrack?: (text: string) => void
  ) {
    const res = await fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    if (!res.body) {
      onError(new Error('No response body'));
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Split into SSE event blocks (separated by blank lines)
        while (buffer.includes('\n\n')) {
          const blockEnd = buffer.indexOf('\n\n');
          const block = buffer.slice(0, blockEnd);
          buffer = buffer.slice(blockEnd + 2);

          let eventName = '';
          let eventData = '';

          for (const line of block.split('\n')) {
            if (line.startsWith('event: ')) {
              eventName = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
              eventData = line.slice(6).trim();
            }
          }

          if (eventData === '[DONE]') {
            onDone();
            return;
          }

          if (!eventData) continue;

          try {
            const data = JSON.parse(eventData);
            switch (eventName) {
              case 'text_delta':
                if (data.text) onChunk(data.text);
                break;
              case 'track':
                onTrack?.(data.text ?? null);
                break;
              case 'done':
                onDone();
                return;
              case 'error':
                onError(new Error(data.error ?? 'Stream error'));
                return;
              case 'final':
                // already handled via text_delta chunks
                break;
            }
          } catch {
            // skip malformed JSON
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  },

  async listConversations(
    limit = 50,
    offset = 0,
    includeArchived = false
  ): Promise<ConversationListResponse> {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
      include_archived: String(includeArchived),
    });
    const res = await fetch(`${API_BASE}/conversations?${params}`);
    if (!res.ok) throw new Error(`List conversations failed: ${res.statusText}`);
    return res.json();
  },

  async createConversation(title?: string): Promise<{ thread_id: string }> {
    const res = await fetch(`${API_BASE}/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    if (!res.ok) throw new Error(`Create conversation failed: ${res.statusText}`);
    return res.json();
  },

  async deleteConversation(threadId: string): Promise<void> {
    const res = await fetch(`${API_BASE}/conversations/${threadId}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(`Delete conversation failed: ${res.statusText}`);
  },

  async uploadImage(file: File): Promise<UploadImageResponse> {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/uploads/images`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error((body as { detail?: string }).detail ?? `Upload failed: ${res.statusText}`);
    }
    return res.json();
  },

  async uploadFile(file: File): Promise<UploadFileResponse> {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/uploads/files`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error((body as { detail?: string }).detail ?? `Upload failed: ${res.statusText}`);
    }
    return res.json();
  },

  async getWorkspaceTree(): Promise<WorkspaceTreeResponse> {
    const res = await fetch(`${API_BASE}/workspace/tree`);
    if (!res.ok) throw new Error(`Workspace tree failed: ${res.statusText}`);
    return res.json();
  },

  async getVoiceConfig(): Promise<VoiceConfig> {
    const res = await fetch(`${API_BASE}/voice/config`);
    if (!res.ok) throw new Error(`Voice config failed: ${res.statusText}`);
    return res.json();
  },

  async speechToText(audioBlob: Blob): Promise<string> {
    const res = await fetch(`${API_BASE}/voice/stt`, {
      method: 'POST',
      body: audioBlob,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error((body as { detail?: string }).detail ?? `STT failed: ${res.statusText}`);
    }
    const data = await res.json() as { text: string };
    return data.text;
  },

  async textToSpeech(text: string, voiceId?: string): Promise<Blob> {
    const res = await fetch(`${API_BASE}/voice/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice_id: voiceId }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error((body as { detail?: string }).detail ?? `TTS failed: ${res.statusText}`);
    }
    return res.blob();
  },
};