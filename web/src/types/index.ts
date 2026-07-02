export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  attachments?: Attachment[];
}

export interface Attachment {
  id: string;
  name: string;
  type: 'image' | 'file';
  url?: string;
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