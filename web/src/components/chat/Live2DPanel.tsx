import { AnimatePresence, motion } from 'framer-motion'
import { BookOpen, ChevronDown, GraduationCap, Mic, MicOff, Search, Settings2, Smile, Sparkles, Wand2, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Live2DAudioEvent, Live2DMood, Live2DViseme } from '../../types/chat'

interface Live2DPanelProps {
  isSpeaking: boolean
  speechText: string
  mood: Live2DMood
  audioEvent?: Live2DAudioEvent
  isOpen: boolean
  onToggle: () => void
  isMobile?: boolean
}

const MODEL_URL = '/live2d/models/mao_pro/mao_pro.model3.json'
type ViewMode = 'bust' | 'full'

const MOOD_LABELS: Record<Live2DMood, string> = {
  happy: '愉悦',
  thinking: '思考中',
  neutral: '在线',
  excited: '活跃',
  gentle: '温和',
  sad: '平静',
  angry: '专注',
}

const EXPRESSION_BY_MOOD: Partial<Record<Live2DMood, string>> = {
  happy: 'exp_01',
  gentle: 'exp_02',
  thinking: 'exp_03',
  excited: 'exp_05',
  sad: 'exp_07',
  angry: 'exp_08',
  neutral: 'exp_04',
}

const MOTION_BY_MOOD: Partial<Record<Live2DMood, { group: string; index?: number }>> = {
  happy: { group: '', index: 0 },
  gentle: { group: '', index: 1 },
  thinking: { group: '', index: 2 },
  excited: { group: '', index: 3 },
  sad: { group: '', index: 4 },
  angry: { group: '', index: 5 },
}

const VISEME_PARAM_IDS: Record<Live2DViseme, string[]> = {
  a: ['ParamA'],
  o: ['ParamO'],
  e: ['ParamE'],
  i: ['ParamI'],
  u: ['ParamU'],
  v: ['ParamU'],
}

const MOUTH_FORM_BY_VISEME: Record<Live2DViseme, number> = {
  a: 0,
  o: -0.55,
  e: 0.35,
  i: 0.7,
  u: -0.75,
  v: -0.9,
}

type PixiApp = {
  stage: { addChild: (child: unknown) => void; removeChildren?: () => void }
  view: HTMLCanvasElement
  renderer: { resize: (width: number, height: number) => void }
  ticker: { add: (fn: () => void) => void; remove: (fn: () => void) => void }
  destroy: (removeView?: boolean, options?: unknown) => void
}

type Live2DModelInstance = {
  anchor: { set: (x: number, y?: number) => void }
  scale: { set: (x: number, y?: number) => void }
  x: number
  y: number
  width: number
  height: number
  getBounds?: () => { x: number; y: number; width: number; height: number }
  interactive?: boolean
  on?: (event: string, handler: (...args: unknown[]) => void) => void
  focus?: (x: number, y: number, instant?: boolean) => void
  motion?: (group: string, index?: number, priority?: number) => Promise<boolean>
  expression?: (id?: string | number) => Promise<boolean>
  internalModel?: {
    coreModel?: {
      setParameterValueById?: (id: string, value: number, weight?: number) => void
      setParamFloat?: (id: string, value: number, weight?: number) => void
    }
  }
}

export default function Live2DPanel({
  isSpeaking,
  speechText,
  mood,
  audioEvent,
  isMobile,
  onToggle,
}: Live2DPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const appRef = useRef<PixiApp | null>(null)
  const modelRef = useRef<Live2DModelInstance | null>(null)
  const mouthValueRef = useRef(0)
  const speakingRef = useRef(false)
  const fallbackSpeechRef = useRef('')
  const backendAudioSeenRef = useRef(false)
  const speechFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const objectUrlRef = useRef<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const pendingAudioRef = useRef<HTMLAudioElement | null>(null)
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [showSpeech, setShowSpeech] = useState(false)
  const [displaySpeech, setDisplaySpeech] = useState('')
  const [voiceEnabled, setVoiceEnabled] = useState(true)
  const [viewMode] = useState<ViewMode>('bust')
  const [controlsExpanded, setControlsExpanded] = useState(false)

  const moodLabel = MOOD_LABELS[mood]
  const hasBackendAudio = Boolean(audioEvent?.audioBase64)
  const audioUnlockedRef = useRef(false)

  const tryPlayAudio = useCallback((audio: HTMLAudioElement, onStarted?: () => void) => {
    if (!voiceEnabled) {
      pendingAudioRef.current = audio
      return
    }

    audio.play()
      .then(() => {
        if (pendingAudioRef.current === audio) pendingAudioRef.current = null
        onStarted?.()
      })
      .catch((error: unknown) => {
        pendingAudioRef.current = audio
        console.warn('Luoying audio playback was blocked; waiting for user interaction.', error)
      })
  }, [voiceEnabled])

  // Unlock audio playback on first user interaction
  useEffect(() => {
    const unlock = () => {
      audioUnlockedRef.current = true
      const AudioContextCtor = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (AudioContextCtor) {
        const ctx = new AudioContextCtor()
        const buffer = ctx.createBuffer(1, 1, 22050)
        const source = ctx.createBufferSource()
        source.buffer = buffer
        source.connect(ctx.destination)
        source.start(0)
        void ctx.close()
      }
      const pending = pendingAudioRef.current
      if (pending && !pending.ended) tryPlayAudio(pending)
    }
    document.addEventListener('click', unlock)
    document.addEventListener('touchstart', unlock)
    return () => {
      document.removeEventListener('click', unlock)
      document.removeEventListener('touchstart', unlock)
    }
  }, [tryPlayAudio])

  useEffect(() => {
    if (!voiceEnabled) {
      audioRef.current?.pause()
      return
    }
    const pending = pendingAudioRef.current
    if (pending && !pending.ended) tryPlayAudio(pending)
  }, [tryPlayAudio, voiceEnabled])

  const setMouth = useCallback((value: number) => {
    const clamped = Math.max(0, Math.min(1, value))
    mouthValueRef.current = clamped
    const core = modelRef.current?.internalModel?.coreModel
    const setParam = core?.setParameterValueById ?? core?.setParamFloat
    setParam?.call(core, 'ParamMouthOpenY', clamped, 1)
    setParam?.call(core, 'ParamMouthForm', clamped * 0.35, 0.35)
    setParam?.call(core, 'ParamA', clamped, 1)
    ;(['ParamI', 'ParamU', 'ParamE', 'ParamO'] as const).forEach((id) => setParam?.call(core, id, 0, 1))
  }, [])

  const setMouthViseme = useCallback((viseme: Live2DViseme | undefined, value: number) => {
    if (!viseme) {
      setMouth(value)
      return
    }

    const clamped = Math.max(0, Math.min(1, value))
    mouthValueRef.current = clamped
    const core = modelRef.current?.internalModel?.coreModel
    const setParam = core?.setParameterValueById ?? core?.setParamFloat
    ;(['ParamA', 'ParamI', 'ParamU', 'ParamE', 'ParamO'] as const).forEach((id) => {
      setParam?.call(core, id, 0, 1)
    })
    VISEME_PARAM_IDS[viseme].forEach((id) => setParam?.call(core, id, clamped, 1))
    setParam?.call(core, 'ParamMouthOpenY', clamped, 1)
    setParam?.call(core, 'ParamMouthForm', MOUTH_FORM_BY_VISEME[viseme] * clamped, 1)
    if (viseme !== 'a') setParam?.call(core, 'ParamA', clamped * 0.72, 0.72)
  }, [setMouth])

  const fitModel = useCallback(() => {
    const container = containerRef.current
    const app = appRef.current
    const model = modelRef.current
    if (!container || !app || !model) return

    const width = Math.max(container.clientWidth, 280)
    const height = Math.max(container.clientHeight, 360)
    app.renderer.resize(width, height)

    model.anchor.set(0, 0)
    model.scale.set(1)
    model.x = 0
    model.y = 0
    const naturalBounds = model.getBounds?.() ?? { x: 0, y: 0, width: model.width, height: model.height }
    const baseWidth = Math.max(naturalBounds.width, 1)
    const baseHeight = Math.max(naturalBounds.height, 1)
    const fullScale = Math.min(width / baseWidth, height / baseHeight) * 0.9
    const scale = viewMode === 'bust'
      ? Math.min(fullScale * 1.55, width / baseWidth * 1.42)
      : fullScale
    model.scale.set(scale)
    model.x = 0
    model.y = 0
    const bounds = model.getBounds?.() ?? { x: 0, y: 0, width: model.width, height: model.height }
    const targetCenterX = width * 0.5
    const targetCenterY = viewMode === 'bust' ? height * 0.82 : height * 0.5
    model.x += targetCenterX - (bounds.x + bounds.width / 2)
    model.y += targetCenterY - (bounds.y + bounds.height / 2)
  }, [viewMode])

  useEffect(() => {
    speakingRef.current = isSpeaking
  }, [isSpeaking])

  useEffect(() => {
    let disposed = false
    let resizeObserver: ResizeObserver | null = null
    let idleTimer: ReturnType<typeof setInterval> | null = null

    async function boot() {
      const container = containerRef.current
      if (!container) return

      try {
        setLoadState('loading')
        const PIXI = await import('pixi.js')
        ;(window as unknown as { PIXI?: unknown }).PIXI = PIXI
        const live2d = await import('pixi-live2d-display/cubism4')
        const app = new PIXI.Application({
          width: container.clientWidth,
          height: container.clientHeight,
          transparent: true,
          antialias: true,
          autoDensity: true,
          resolution: window.devicePixelRatio || 1,
        }) as unknown as PixiApp

        if (disposed) {
          app.destroy(true)
          return
        }

        container.innerHTML = ''
        container.appendChild(app.view)
        app.view.style.width = '100%'
        app.view.style.height = '100%'
        app.view.style.display = 'block'
        app.view.style.position = 'absolute'
        app.view.style.inset = '0'
        app.view.style.zIndex = '1'
        appRef.current = app

        const model = (await live2d.Live2DModel.from(MODEL_URL, {
          autoInteract: true,
        })) as unknown as Live2DModelInstance

        if (disposed) return

        model.interactive = true
        model.on?.('hit', () => {
          void model.motion?.('', 0, live2d.MotionPriority.FORCE)
          void model.expression?.('exp_01')
        })
        app.stage.addChild(model)
        modelRef.current = model
        fitModel()
        requestAnimationFrame(fitModel)
        setTimeout(fitModel, 250)
        resizeObserver = new ResizeObserver(fitModel)
        resizeObserver.observe(container)

        const tick = () => {
          if (audioRef.current && !audioRef.current.paused && !audioRef.current.ended) return
          const next = mouthValueRef.current * 0.78
          if (next < 0.01) {
            setMouth(0)
          } else {
            setMouth(next)
          }
        }
        app.ticker.add(tick)

        idleTimer = setInterval(() => {
          if (!speakingRef.current) void model.motion?.('Idle', 0, live2d.MotionPriority.IDLE)
        }, 9000)

        setLoadState('ready')
      } catch (error) {
        console.error(error)
        setLoadState('error')
      }
    }

    void boot()

    return () => {
      disposed = true
      resizeObserver?.disconnect()
      if (idleTimer) clearInterval(idleTimer)
      appRef.current?.destroy(true, { children: true, texture: true, baseTexture: true })
      appRef.current = null
      modelRef.current = null
    }
  }, [fitModel, setMouth])

  useEffect(() => {
    fitModel()
  }, [fitModel])

  useEffect(() => {
    const expression = EXPRESSION_BY_MOOD[mood]
    const motion = MOTION_BY_MOOD[mood]
    if (expression) void modelRef.current?.expression?.(expression)
    if (motion && isSpeaking) void modelRef.current?.motion?.(motion.group, motion.index, 3)
  }, [isSpeaking, mood])

  useEffect(() => {
    if (!speechText) {
      const timer = setTimeout(() => {
        setShowSpeech(false)
        setDisplaySpeech('')
      }, 1800)
      return () => clearTimeout(timer)
    }

    setShowSpeech(true)
    setDisplaySpeech(speechText.slice(-86))
  }, [speechText])

  useEffect(() => {
    if (!audioEvent?.audioBase64) return

    let stopped = false
    backendAudioSeenRef.current = true
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current)
      objectUrlRef.current = null
    }
    const binary = atob(audioEvent.audioBase64)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
    const objectUrl = URL.createObjectURL(new Blob([bytes], { type: 'audio/wav' }))
    objectUrlRef.current = objectUrl
    audioRef.current?.pause()
    audioRef.current = null
    const audio = new Audio(objectUrl)
    audioRef.current = audio
    audio.preload = 'auto'
    audio.autoplay = true
    let startedAt = performance.now()
    const chunkMs = audioEvent.chunkMs || 20
    let mouthLoopStarted = false

    setShowSpeech(true)
    setDisplaySpeech(audioEvent.text)
    const frame = () => {
      if (stopped) return
      const elapsed = performance.now() - startedAt
      const index = Math.floor(elapsed / chunkMs)
      const value = audioEvent.volumes[index] ?? 0
      const viseme = audioEvent.visemes?.reduce<Live2DViseme | undefined>(
        (current, frame) => (frame.atMs <= elapsed ? frame.viseme : current),
        undefined
      )
      setMouthViseme(viseme, value)
      if (!audio.paused && !audio.ended) requestAnimationFrame(frame)
    }
    const startMouthLoop = () => {
      if (mouthLoopStarted) return
      mouthLoopStarted = true
      startedAt = performance.now()
      requestAnimationFrame(frame)
    }
    const playAudio = () => tryPlayAudio(audio, startMouthLoop)

    if (audio.readyState >= 2) {
      playAudio()
    } else {
      audio.addEventListener('canplay', playAudio, { once: true })
    }

    audio.addEventListener('ended', () => setMouth(0))
    return () => {
      stopped = true
      audio.removeEventListener('canplay', playAudio)
      audio.pause()
      if (pendingAudioRef.current === audio) pendingAudioRef.current = null
      if (audioRef.current === audio) audioRef.current = null
      if (objectUrlRef.current === objectUrl) {
        URL.revokeObjectURL(objectUrl)
        objectUrlRef.current = null
      }
      setMouth(0)
    }
  }, [audioEvent, setMouth, setMouthViseme, tryPlayAudio])

  useEffect(() => {
    if (!voiceEnabled || hasBackendAudio || backendAudioSeenRef.current || !('speechSynthesis' in window)) return

    if (speechFlushTimerRef.current) clearTimeout(speechFlushTimerRef.current)
    const newText = speechText.slice(fallbackSpeechRef.current.length)
    if (!newText) return

    const shouldSpeak = /[。！？!?]\s*$/.test(newText) || newText.length > 28 || !isSpeaking
    if (!shouldSpeak) {
      speechFlushTimerRef.current = setTimeout(() => {
        fallbackSpeechRef.current = speechText
      }, 1200)
      return
    }

    fallbackSpeechRef.current = speechText
    const utterance = new SpeechSynthesisUtterance(newText)
    utterance.lang = 'zh-CN'
    utterance.rate = mood === 'excited' ? 1.14 : mood === 'thinking' ? 0.92 : 1.02
    utterance.pitch = mood === 'happy' || mood === 'excited' ? 1.18 : 1.04
    utterance.onboundary = () => setMouth(0.72)
    utterance.onstart = () => setMouth(0.55)
    utterance.onend = () => setMouth(0)
    window.speechSynthesis.speak(utterance)
  }, [hasBackendAudio, isSpeaking, mood, setMouth, speechText, voiceEnabled])

  useEffect(() => {
    if (isSpeaking) return
    fallbackSpeechRef.current = ''
    backendAudioSeenRef.current = false
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    setMouth(0)
  }, [isSpeaking, setMouth])

  const statusLabel = useMemo(() => {
    if (loadState === 'loading') return '加载中'
    if (loadState === 'error') return '加载失败'
    if (isSpeaking) return '回应中'
    return '在线'
  }, [isSpeaking, loadState])

  const playInteraction = useCallback((index: number, expression?: string) => {
    if (expression) void modelRef.current?.expression?.(expression)
    void modelRef.current?.motion?.('', index, 3)
  }, [])

  const handleQuickAction = useCallback((prompt: string) => {
    window.dispatchEvent(new CustomEvent('luoying-quick-action', { detail: prompt }))
  }, [])

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-[#e2e8f0] bg-white shadow-sm">
      {isMobile && (
        <div className="flex items-center justify-between border-b border-[#e8ecf1] px-4 py-3">
          <span className="font-display text-base font-semibold text-[#1e293b]">珞樱助手</span>
          <button
            onClick={onToggle}
            className="rounded-lg p-1.5 text-[#94a3b8] transition-colors hover:bg-[#f1f5f9] hover:text-[#64748b]"
            aria-label="关闭面板"
          >
            <X size={18} />
          </button>
        </div>
      )}

      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Character Display Area */}
        <div className="relative min-h-[320px] flex-1 bg-gradient-to-b from-[#f8fbff] to-[#f0f7ff]">
          <div ref={containerRef} className="absolute inset-0 z-[1]" />

          {loadState !== 'ready' && (
            <div className="absolute inset-0 grid place-items-center bg-white/80 text-center">
              <div>
                <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-[#0067B1] border-t-transparent" />
                <p className="text-sm text-[#64748b]">
                  {loadState === 'loading' ? '正在加载珞樱形象…' : '形象加载失败，请稍后重试'}
                </p>
              </div>
            </div>
          )}

          <AnimatePresence>
            {showSpeech && displaySpeech && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 6 }}
                className="absolute bottom-3 left-3 right-3 z-20 rounded-lg border border-[#e2e8f0] bg-white/95 px-3 py-2.5 text-[#1e293b] shadow-lg backdrop-blur-sm"
              >
                <p className="line-clamp-2 text-xs leading-5">{displaySpeech}</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Status Bar */}
        <div className="flex items-center justify-between border-t border-[#e8ecf1] px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className={`inline-block h-2 w-2 rounded-full ${loadState === 'ready' ? 'bg-emerald-400' : loadState === 'loading' ? 'bg-amber-400 animate-pulse' : 'bg-red-400'}`} />
            <span className="text-xs font-medium text-[#64748b]">{statusLabel}</span>
            {isSpeaking && (
              <span className="text-xs text-[#94a3b8]">· {moodLabel}</span>
            )}
          </div>
          <button
            onClick={() => setVoiceEnabled((enabled) => !enabled)}
            className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
              voiceEnabled
                ? 'bg-[#f0f7ff] text-[#0067B1]'
                : 'bg-[#f8fafc] text-[#94a3b8]'
            }`}
          >
            {voiceEnabled ? <Mic size={13} /> : <MicOff size={13} />}
            {voiceEnabled ? '语音' : '静音'}
          </button>
        </div>

        {/* Service Mode */}
        <div className="border-t border-[#e8ecf1] px-4 py-2.5">
          <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-[#94a3b8]">当前服务</p>
          <div className="flex flex-wrap gap-1.5">
            <span className="rounded-md bg-[#f0f4fa] px-2.5 py-1 text-[11px] font-medium text-[#0067B1]">学院问答</span>
            <span className="rounded-md bg-[#f8fafc] px-2.5 py-1 text-[11px] text-[#64748b]">实时检索</span>
            <span className="rounded-md bg-[#f8fafc] px-2.5 py-1 text-[11px] text-[#64748b]">语音回复</span>
          </div>
        </div>

        {/* Scrollable Controls Area */}
        <div className="overflow-y-auto border-t border-[#e8ecf1]">
          {/* Collapsible Interaction Controls */}
          <button
            onClick={() => setControlsExpanded((v) => !v)}
            className="flex w-full items-center justify-between px-4 py-2.5 text-left transition-colors hover:bg-[#f8fafc]"
          >
            <span className="text-[10px] font-medium uppercase tracking-wider text-[#94a3b8]">更多互动</span>
            <ChevronDown
              size={14}
              className={`text-[#94a3b8] transition-transform duration-200 ${controlsExpanded ? 'rotate-180' : ''}`}
            />
          </button>

          <AnimatePresence initial={false}>
            {controlsExpanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
                className="overflow-hidden"
              >
                <div className="px-4 pb-3">
                  <p className="mb-1.5 text-[10px] text-[#94a3b8]">表情</p>
                  <div className="grid grid-cols-4 gap-1.5">
                    <ActionButton icon={<Smile size={13} />} label="微笑" onClick={() => playInteraction(0, 'exp_01')} />
                    <ActionButton icon={<Smile size={13} />} label="温柔" onClick={() => playInteraction(1, 'exp_02')} />
                    <ActionButton icon={<Sparkles size={13} />} label="思考" onClick={() => playInteraction(2, 'exp_03')} />
                    <ActionButton icon={<Smile size={13} />} label="平静" onClick={() => playInteraction(0, 'exp_04')} />
                    <ActionButton icon={<Wand2 size={13} />} label="开心" onClick={() => playInteraction(3, 'exp_05')} />
                    <ActionButton icon={<Smile size={13} />} label="活泼" onClick={() => playInteraction(0, 'exp_06')} />
                    <ActionButton icon={<Smile size={13} />} label="难过" onClick={() => playInteraction(4, 'exp_07')} />
                    <ActionButton icon={<Smile size={13} />} label="生气" onClick={() => playInteraction(5, 'exp_08')} />
                  </div>

                  <p className="mb-1.5 mt-3 text-[10px] text-[#94a3b8]">动作</p>
                  <div className="grid grid-cols-3 gap-1.5">
                    <ActionButton icon={<Wand2 size={13} />} label="动作1" onClick={() => playInteraction(0)} />
                    <ActionButton icon={<Wand2 size={13} />} label="动作2" onClick={() => playInteraction(1)} />
                    <ActionButton icon={<Wand2 size={13} />} label="动作3" onClick={() => playInteraction(2)} />
                    <ActionButton icon={<Sparkles size={13} />} label="特殊1" onClick={() => playInteraction(3)} />
                    <ActionButton icon={<Sparkles size={13} />} label="特殊2" onClick={() => playInteraction(4)} />
                    <ActionButton icon={<Sparkles size={13} />} label="特殊3" onClick={() => playInteraction(5)} />
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Quick Service Links */}
          <div className="border-t border-[#e8ecf1] px-4 py-3">
            <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-[#94a3b8]">快捷服务</p>
            <div className="grid grid-cols-2 gap-1.5">
              <QuickServiceButton
                icon={<GraduationCap size={14} />}
                label="学院介绍"
                onClick={() => handleQuickAction('请介绍一下武汉大学人工智能学院')}
              />
              <QuickServiceButton
                icon={<BookOpen size={14} />}
                label="招生咨询"
                onClick={() => handleQuickAction('我想了解人工智能学院的招生信息')}
              />
              <QuickServiceButton
                icon={<Search size={14} />}
                label="科研方向"
                onClick={() => handleQuickAction('人工智能学院有哪些科研方向？')}
              />
              <QuickServiceButton
                icon={<Settings2 size={14} />}
                label="办事指南"
                onClick={() => handleQuickAction('请问学院有哪些常用的办事指南？')}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function QuickServiceButton({ icon, label, onClick }: { icon: ReactNode; label: string; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 rounded-lg border border-[#dce3ec] bg-[#f8fafc] px-3 py-2 text-xs text-[#475569] transition-colors hover:border-[#0067B1]/30 hover:bg-[#f0f7ff] hover:text-[#0067B1]"
    >
      {icon}
      {label}
    </button>
  )
}

function ActionButton({ icon, label, onClick }: { icon: ReactNode; label: string; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center justify-center gap-1.5 rounded-lg border border-[#dce3ec] bg-[#f8fafc] px-2 py-1.5 text-[11px] text-[#475569] transition-colors hover:border-[#0067B1]/30 hover:bg-[#f0f7ff] hover:text-[#0067B1]"
    >
      {icon}
      {label}
    </button>
  )
}
