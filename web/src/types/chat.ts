// src/types/chat.ts - Chat-related TypeScript types

export interface FileAttachment {
  id: string
  name: string
  size: number
  type: string
  url?: string
  progress?: number
  status: 'selected' | 'uploading' | 'uploaded' | 'failed'
}

export type MessageRole = 'user' | 'assistant'
export type MessageStatus = 'sending' | 'sent' | 'error' | 'streaming'

export interface Message {
  id: string
  role: MessageRole
  content: string
  timestamp: number
  attachments?: FileAttachment[]
  status?: MessageStatus
}

export interface ChatSession {
  id: string
  title: string
  messages: Message[]
  createdAt: number
  updatedAt: number
}

export interface ChatState {
  sessions: ChatSession[]
  activeSessionId: string | null
  isGenerating: boolean
  currentAiText: string
}

export type Live2DMood = 'happy' | 'thinking' | 'neutral' | 'excited' | 'gentle' | 'sad' | 'angry'
export type Live2DViseme = 'a' | 'o' | 'e' | 'i' | 'u' | 'v'

export interface Live2DVisemeFrame {
  atMs: number
  viseme: Live2DViseme
}

export interface Live2DAudioEvent {
  id: string
  audioBase64: string
  volumes: number[]
  emotion: Live2DMood
  text: string
  chunkMs: number
  sampleRate: number
  durationMs?: number
  visemes?: Live2DVisemeFrame[]
}

export interface Live2DState {
  visible: boolean
  mood: Live2DMood
  isSpeaking: boolean
  speechText: string
  audioEvent?: Live2DAudioEvent
}
