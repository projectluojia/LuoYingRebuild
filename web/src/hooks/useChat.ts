import { useCallback, useMemo, useRef, useState } from 'react'
import { pinyin } from 'pinyin-pro'
import type { ChatSession, FileAttachment, Live2DAudioEvent, Live2DMood, Live2DViseme, Live2DVisemeFrame, Message } from '../types/chat'

const API_BASE = import.meta.env.DEV ? '/api' : ''
const TEXT_DRIP_INTERVAL = 46
const AUDIO_SAFETY_GAP = 80
const STREAM_IDLE_TIMEOUT = 90000

function generateId(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function formatTimeLabel(ts: number): string {
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

function normalizeMood(value: unknown): Live2DMood {
  const raw = String(value || 'neutral').toLowerCase()
  if (raw.includes('happy') || raw.includes('joy')) return 'happy'
  if (raw.includes('gentle') || raw.includes('warm') || raw.includes('soft')) return 'gentle'
  if (raw.includes('sad')) return 'sad'
  if (raw.includes('angry') || raw.includes('serious')) return 'angry'
  if (raw.includes('think') || raw.includes('focus')) return 'thinking'
  if (raw.includes('excited') || raw.includes('surprise')) return 'excited'
  return 'neutral'
}

function titleFromText(text: string): string {
  const clean = text.replace(/\s+/g, ' ').trim()
  return clean ? clean.slice(0, 18) : '新的对话'
}

function parseSseChunk(buffer: string): { events: Array<{ event: string; data: Record<string, unknown> }>; rest: string } {
  const normalized = buffer.replace(/\r\n/g, '\n')
  const parts = normalized.split('\n\n')
  const rest = parts.pop() ?? ''
  const events = parts
    .map((part) => {
      let event = 'message'
      const dataLines: string[] = []
      for (const line of part.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
      }
      if (dataLines.length === 0) return null
      try {
        return { event, data: JSON.parse(dataLines.join('\n')) as Record<string, unknown> }
      } catch {
        return { event, data: { text: dataLines.join('\n') } }
      }
    })
    .filter((event): event is { event: string; data: Record<string, unknown> } => Boolean(event))

  return { events, rest }
}

function estimateAudioDuration(event: Live2DAudioEvent): number {
  if (event.durationMs && Number.isFinite(event.durationMs)) return event.durationMs
  const fromVolumes = event.volumes.length * Math.max(event.chunkMs || 20, 12)
  const fromText = Math.max(event.text.length * 115, 650)
  return Math.max(fromVolumes || 0, fromText)
}

function textStepDelay(text: string, durationMs: number): number {
  const chars = Math.max(Array.from(text).length, 1)
  return Math.max(32, Math.min(150, durationMs / chars))
}

function splitRevealText(text: string): string[] {
  return Array.from(text)
}

function syllableToViseme(syllable: string): Live2DViseme | null {
  const clean = syllable.toLowerCase().replace(/[^a-züv]/g, '')
  if (!clean) return null
  if (clean.includes('ü') || clean.includes('v')) return 'v'
  const lastVowel = clean.match(/[aoeiu](?!.*[aoeiu])/)?.[0]
  return (lastVowel as Live2DViseme | undefined) ?? null
}

function buildVisemeTimeline(text: string, durationMs: number): Live2DVisemeFrame[] {
  const syllables = pinyin(text, { toneType: 'none', type: 'array', nonZh: 'consecutive' })
    .map((part) => syllableToViseme(String(part)))
    .filter((part): part is Live2DViseme => Boolean(part))
  if (syllables.length === 0) return []

  const usableDuration = Math.max(durationMs - 120, 240)
  const step = usableDuration / syllables.length
  return syllables.map((viseme, index) => ({
    atMs: Math.round(index * step),
    viseme,
  }))
}

async function readWithIdleTimeout(
  reader: ReadableStreamDefaultReader<Uint8Array>
): Promise<ReadableStreamReadResult<Uint8Array> | null> {
  let timer: ReturnType<typeof setTimeout> | undefined
  const timeout = new Promise<null>((resolve) => {
    timer = setTimeout(() => resolve(null), STREAM_IDLE_TIMEOUT)
  })
  const result = await Promise.race([reader.read(), timeout])
  if (timer) clearTimeout(timer)
  return result
}

const FALLBACK_REPLIES: Record<string, string> = {
  default:
    '你好，我是珞樱，武汉大学人工智能学院的校园智能助手。我可以帮助你了解学院介绍、招生培养、科研方向、导师团队、办事流程与校园服务。请问有什么可以帮你？',
  live2d:
    '右侧的助手面板展示了珞樱的形象与当前服务状态，支持语音交互功能。你可以通过语音或文字与珞樱进行对话。',
  campus:
    '珞樱可以帮你了解武汉大学人工智能学院的校园服务信息，包括办事指南、学术资源、校园生活等。请问你想了解哪方面？',
}

const INITIAL_SESSIONS: ChatSession[] = [
  {
    id: 'welcome',
    title: '珞樱智能助手',
    createdAt: Date.now(),
    updatedAt: Date.now(),
    messages: [
      {
        id: 'welcome-1',
        role: 'assistant',
        content:
          '你好，我是珞樱，武汉大学人工智能学院的校园智能助手。我可以帮助你了解学院介绍、招生培养、科研方向、导师团队、办事流程与校园服务。',
        timestamp: Date.now(),
        status: 'sent',
      },
    ],
  },
]

type SpeechQueueItem = {
  text: string
  audioEvent: Live2DAudioEvent
  durationMs: number
}

export function useChat() {
  const [sessions, setSessions] = useState<ChatSession[]>(INITIAL_SESSIONS)
  const [activeSessionId, setActiveSessionId] = useState<string | null>('welcome')
  const [isGenerating, setIsGenerating] = useState(false)
  const [currentAiText, setCurrentAiText] = useState('')
  const [live2dVisible, setLive2dVisible] = useState(true)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [liveMood, setLiveMood] = useState<Live2DMood>('gentle')
  const [liveAudioEvent, setLiveAudioEvent] = useState<Live2DAudioEvent | undefined>()
  const abortRef = useRef<AbortController | null>(null)
  const visibleTextRef = useRef('')
  const rawTextRef = useRef('')
  const unsyncedTextRef = useRef('')
  const speechQueueRef = useRef<SpeechQueueItem[]>([])
  const speechLoopRef = useRef<Promise<void> | null>(null)
  const fallbackTextLoopRef = useRef<Promise<void> | null>(null)
  const generationTokenRef = useRef(0)
  const gotAudioRef = useRef(false)

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) ?? null,
    [activeSessionId, sessions]
  )

  const resetTimeline = useCallback(() => {
    generationTokenRef.current += 1
    visibleTextRef.current = ''
    rawTextRef.current = ''
    unsyncedTextRef.current = ''
    speechQueueRef.current = []
    speechLoopRef.current = null
    fallbackTextLoopRef.current = null
    gotAudioRef.current = false
    setCurrentAiText('')
    setLiveAudioEvent(undefined)
  }, [])

  const revealText = useCallback(async (text: string, durationMs: number, token: number) => {
    const chars = splitRevealText(text)
    const delay = textStepDelay(text, durationMs)
    for (const char of chars) {
      if (generationTokenRef.current !== token || abortRef.current?.signal.aborted) return
      visibleTextRef.current += char
      setCurrentAiText(visibleTextRef.current)
      if (/[,，。.!！？?]$/.test(char)) {
        await sleep(Math.min(delay * 3, 280))
      } else {
        await sleep(delay)
      }
    }
  }, [])

  const runFallbackTextLoop = useCallback((token: number) => {
    if (fallbackTextLoopRef.current) return
    fallbackTextLoopRef.current = (async () => {
      await sleep(260)
      while (generationTokenRef.current === token && (unsyncedTextRef.current || isGenerating)) {
        if (!gotAudioRef.current && unsyncedTextRef.current) {
          const next = splitRevealText(unsyncedTextRef.current).shift() ?? ''
          unsyncedTextRef.current = unsyncedTextRef.current.slice(next.length)
          visibleTextRef.current += next
          setCurrentAiText(visibleTextRef.current)
        }
        await sleep(TEXT_DRIP_INTERVAL)
        if (!unsyncedTextRef.current && !gotAudioRef.current) await sleep(120)
      }
      fallbackTextLoopRef.current = null
    })()
  }, [isGenerating])

  const runSpeechQueue = useCallback((token: number) => {
    if (speechLoopRef.current) return speechLoopRef.current

    speechLoopRef.current = (async () => {
      while (generationTokenRef.current === token && speechQueueRef.current.length > 0) {
        const item = speechQueueRef.current.shift()
        if (!item) break
        setLiveMood(item.audioEvent.emotion)
        setLiveAudioEvent({ ...item.audioEvent, id: generateId() })
        await Promise.all([
          revealText(item.text, item.durationMs, token),
          sleep(item.durationMs + 120),
        ])
        await sleep(AUDIO_SAFETY_GAP)
      }
      speechLoopRef.current = null
    })()

    return speechLoopRef.current
  }, [revealText])

  const enqueueSpeech = useCallback((audioEvent: Live2DAudioEvent, explicitText: string, token: number) => {

    gotAudioRef.current = true
    const text = explicitText || unsyncedTextRef.current || audioEvent.text
    if (text && unsyncedTextRef.current.startsWith(text)) {
      unsyncedTextRef.current = unsyncedTextRef.current.slice(text.length)
    } else if (text && unsyncedTextRef.current) {
      unsyncedTextRef.current = ''
    }

    const durationMs = estimateAudioDuration({ ...audioEvent, text })
    speechQueueRef.current.push({
      text,
      audioEvent: {
        ...audioEvent,
        text,
        visemes: buildVisemeTimeline(text, durationMs),
      },
      durationMs,
    })
    void runSpeechQueue(token)
  }, [runSpeechQueue])

  const flushRemainingText = useCallback(async (token: number) => {
    while (speechLoopRef.current) await speechLoopRef.current
    const remaining = rawTextRef.current.slice(visibleTextRef.current.length)
    if (remaining) await revealText(remaining, Math.max(remaining.length * 70, 500), token)
  }, [revealText])

  const createNewSession = useCallback(() => {
    abortRef.current?.abort()
    resetTimeline()
    const newSession: ChatSession = {
      id: generateId(),
      title: '新的对话',
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    }
    setSessions((prev) => [newSession, ...prev])
    setActiveSessionId(newSession.id)
    setIsGenerating(false)
    setSidebarOpen(false)
    setLiveMood('gentle')
  }, [resetTimeline])

  const switchSession = useCallback((id: string) => {
    setActiveSessionId(id)
    setSidebarOpen(false)
  }, [])

  const toggleLive2D = useCallback(() => {
    setLive2dVisible((visible) => !visible)
  }, [])

  const toggleSidebar = useCallback(() => {
    setSidebarOpen((open) => !open)
  }, [])

  const appendMessage = useCallback((sessionId: string, message: Message) => {
    setSessions((prev) =>
      prev.map((session) =>
        session.id === sessionId
          ? {
              ...session,
              messages: [...session.messages, message],
              title: session.title === '新的对话' && message.role === 'user' ? titleFromText(message.content) : session.title,
              updatedAt: Date.now(),
            }
          : session
      )
    )
  }, [])

  const ensureSession = useCallback(
    (text: string) => {
      if (activeSessionId) return activeSessionId
      const sessionId = generateId()
      const session: ChatSession = {
        id: sessionId,
        title: titleFromText(text),
        messages: [],
        createdAt: Date.now(),
        updatedAt: Date.now(),
      }
      setSessions((prev) => [session, ...prev])
      setActiveSessionId(sessionId)
      return sessionId
    },
    [activeSessionId]
  )

  const runFallbackStream = useCallback(
    async (sessionId: string, userText: string, token: number) => {
      const lower = userText.toLowerCase()
      const reply = lower.includes('live2d') || userText.includes('皮套') || userText.includes('形象')
        ? FALLBACK_REPLIES.live2d
        : userText.includes('招生') || userText.includes('培养') || userText.includes('办事') || userText.includes('校园')
          ? FALLBACK_REPLIES.campus
          : FALLBACK_REPLIES.default

      setLiveMood('thinking')
      rawTextRef.current = reply
      unsyncedTextRef.current = reply
      await revealText(reply, Math.max(reply.length * 72, 1400), token)

      appendMessage(sessionId, {
        id: generateId(),
        role: 'assistant',
        content: reply,
        timestamp: Date.now(),
        status: 'sent',
      })
      setLiveMood('gentle')
    },
    [appendMessage, revealText]
  )

  const sendMessage = useCallback(
    async (text: string, attachments: FileAttachment[]) => {
      if ((!text.trim() && attachments.length === 0) || isGenerating) return

      abortRef.current?.abort()
      resetTimeline()
      const token = generationTokenRef.current
      const sessionId = ensureSession(text)
      const userMessage: Message = {
        id: generateId(),
        role: 'user',
        content: text,
        timestamp: Date.now(),
        attachments: attachments.length > 0 ? attachments : undefined,
        status: 'sent',
      }

      appendMessage(sessionId, userMessage)
      setIsGenerating(true)
      setLiveMood('thinking')

      const controller = new AbortController()
      abortRef.current = controller
      let gotBackendEvent = false

      try {
        const response = await fetch(`${API_BASE}/chat/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sessionId,
            user_id: 'web-user',
            user_name: '网页用户',
            text,
          }),
          signal: controller.signal,
        })

        if (!response.ok || !response.body) {
          throw new Error(`后端返回 ${response.status}`)
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder('utf-8')
        let buffer = ''

        while (true) {
          const result = await readWithIdleTimeout(reader)
          if (!result) {
            controller.abort()
            break
          }
          const { value, done } = result
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const parsed = parseSseChunk(buffer)
          buffer = parsed.rest

          for (const { event, data } of parsed.events) {
            gotBackendEvent = true
            if (event === 'text_delta') {
              const delta = String(data.text ?? '')
              rawTextRef.current += delta
              unsyncedTextRef.current += delta
              if (!gotAudioRef.current) runFallbackTextLoop(token)
              if (rawTextRef.current.length > 12) setLiveMood('gentle')
            } else if (event === 'expression') {
              setLiveMood(normalizeMood(data.emotion))
            } else if (event === 'track') {
              // LuoYingRebuild backend sends 'track' events for status updates.
              // Treat as expression change when mood info is present.
              if (data.emotion) setLiveMood(normalizeMood(data.emotion))
            } else if (event === 'audio') {
              const audioEvent: Live2DAudioEvent = {
                id: generateId(),
                audioBase64: String(data.audio ?? ''),
                volumes: Array.isArray(data.volumes) ? data.volumes.map(Number) : [],
                emotion: normalizeMood(data.emotion),
                text: String(data.text ?? ''),
                chunkMs: Number(data.chunk_ms ?? 20),
                sampleRate: Number(data.sample_rate ?? 24000),
                durationMs: Number(data.duration_ms || 0) || undefined,
              }
              enqueueSpeech(audioEvent, audioEvent.text, token)
            } else if (event === 'final') {
              const finalText = String(data.reply ?? rawTextRef.current)
              if (finalText && finalText.length >= rawTextRef.current.length) {
                rawTextRef.current = finalText
              }
            } else if (event === 'error') {
              throw new Error(String(data.error ?? '后端流式接口错误'))
            } else if (event === 'done') {
              // LuoYingRebuild backend sends 'done' to signal stream end.
              break
            }
          }
        }

        if (!gotBackendEvent) {
          throw new Error('后端没有推送事件')
        }

        await flushRemainingText(token)
        const finalContent = rawTextRef.current.trim() || '后端已完成处理，但没有返回文本内容。'
        appendMessage(sessionId, {
          id: generateId(),
          role: 'assistant',
          content: finalContent,
          timestamp: Date.now(),
          status: 'sent',
        })
        setLiveMood('gentle')
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          await runFallbackStream(sessionId, text, token)
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null
        setIsGenerating(false)
        await sleep(240)
        setCurrentAiText('')
      }
    },
    [appendMessage, enqueueSpeech, ensureSession, flushRemainingText, isGenerating, resetTimeline, runFallbackStream, runFallbackTextLoop]
  )

  return {
    sessions,
    activeSessionId,
    activeSession,
    createNewSession,
    switchSession,
    sendMessage,
    isGenerating,
    currentAiText,
    live2dVisible,
    liveMood,
    liveAudioEvent,
    toggleLive2D,
    sidebarOpen,
    toggleSidebar,
    formatTimeLabel,
  }
}
