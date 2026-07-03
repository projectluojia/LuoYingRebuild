import { AnimatePresence, motion } from 'framer-motion'
import { Bot, ChevronDown, Menu } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import ChatInput from '../components/chat/ChatInput'
import ChatMessage from '../components/chat/ChatMessage'
import ChatSidebar from '../components/chat/ChatSidebar'
import Live2DPanel from '../components/chat/Live2DPanel'
import TypingIndicator from '../components/chat/TypingIndicator'
import { useChat } from '../hooks/useChat'
import type { FileAttachment } from '../types/chat'

const QUICK_QUESTIONS = [
  '学院介绍',
  '招生咨询',
  '本科培养',
  '研究生培养',
  '科研方向',
  '实验室与导师',
  '办事指南',
  '学术资源',
  '校园服务',
]

export default function Chat() {
  const {
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
  } = useChat()

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const [showNewMsgIndicator, setShowNewMsgIndicator] = useState(false)
  const [userScrolledUp, setUserScrolledUp] = useState(false)
  const [isCompactLayout, setIsCompactLayout] = useState(false)

  useEffect(() => {
    const mediaQuery = window.matchMedia('(max-width: 1023px)')
    const updateLayout = () => setIsCompactLayout(mediaQuery.matches)
    updateLayout()
    mediaQuery.addEventListener('change', updateLayout)
    return () => mediaQuery.removeEventListener('change', updateLayout)
  }, [])

  // Listen for quick action events from Live2DPanel
  useEffect(() => {
    const handler = (e: Event) => {
      const prompt = (e as CustomEvent).detail as string
      if (prompt) handleSend(prompt, [])
    }
    window.addEventListener('luoying-quick-action', handler)
    return () => window.removeEventListener('luoying-quick-action', handler)
  })

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [])

  useEffect(() => {
    if (!userScrolledUp) {
      scrollToBottom()
    } else {
      setShowNewMsgIndicator(true)
    }
  }, [activeSession?.messages.length, currentAiText, isGenerating, scrollToBottom, userScrolledUp])

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 96
    setUserScrolledUp(!nearBottom)
    if (nearBottom) setShowNewMsgIndicator(false)
  }, [])

  const handleSend = (text: string, attachments: FileAttachment[]) => {
    void sendMessage(text, attachments)
    setUserScrolledUp(false)
    setShowNewMsgIndicator(false)
  }

  const totalMessages = activeSession?.messages.length ?? 0
  const showEmpty = totalMessages === 0 && !isGenerating

  return (
    <div className="relative min-h-[100dvh] overflow-hidden bg-[#f8fafc] pt-16 text-[#1e293b]">
      <img
        src="/images/luoying-campus-ai-bg.png"
        alt=""
        className="pointer-events-none fixed inset-0 h-full w-full object-cover opacity-[0.06]"
      />

      <AnimatePresence>
        {sidebarOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm lg:hidden"
              onClick={toggleSidebar}
            />
            <motion.div
              initial={{ x: -320 }}
              animate={{ x: 0 }}
              exit={{ x: -320 }}
              transition={{ duration: 0.28, ease: [0.4, 0, 0.2, 1] }}
              className="fixed bottom-0 left-0 top-0 z-50 w-[300px] p-3 shadow-2xl lg:hidden"
            >
              <ChatSidebar
                sessions={sessions}
                activeSessionId={activeSessionId}
                onNewChat={createNewSession}
                onSwitchSession={switchSession}
                isMobile
                onClose={toggleSidebar}
              />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {live2dVisible && isCompactLayout && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm lg:hidden"
              onClick={toggleLive2D}
            />
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ duration: 0.28, ease: [0.4, 0, 0.2, 1] }}
              className="fixed bottom-0 right-0 top-0 z-50 w-[340px] max-w-[90vw] p-3 shadow-2xl lg:hidden"
            >
              <Live2DPanel
                isSpeaking={isGenerating}
                speechText={currentAiText}
                mood={liveMood}
                audioEvent={liveAudioEvent}
                isOpen={live2dVisible}
                onToggle={toggleLive2D}
                isMobile
              />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <div className="relative mx-auto flex h-[calc(100dvh-4rem)] max-w-[1600px] gap-3 px-3 pb-3 pt-3">
        {/* Left Sidebar */}
        <aside className="hidden w-[260px] shrink-0 lg:block">
          <ChatSidebar
            sessions={sessions}
            activeSessionId={activeSessionId}
            onNewChat={createNewSession}
            onSwitchSession={switchSession}
          />
        </aside>

        {/* Main Chat Area */}
        <section className="relative flex min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-[#dce3ec] bg-white shadow-sm">
          {/* Header */}
          <div className="flex shrink-0 items-center justify-between border-b border-[#f1f5f9] bg-white px-4 py-3 lg:px-6">
            <button
              onClick={toggleSidebar}
              className="rounded-lg border border-[#e2e8f0] p-2 text-[#64748b] transition-colors hover:bg-[#f8fafc] hover:text-[#0067B1] lg:hidden"
              aria-label="打开会话列表"
            >
              <Menu size={18} />
            </button>

            <div className="min-w-0 flex-1 lg:pl-0 pl-3">
              <h1 className="truncate font-display text-lg font-semibold text-[#1e293b]">
                {activeSession?.title ?? '新的对话'}
              </h1>
              {isGenerating && (
                <p className="mt-0.5 text-xs text-[#0067B1]">珞樱正在回应…</p>
              )}
            </div>

            <button
              onClick={toggleLive2D}
              className="rounded-lg border border-[#e2e8f0] p-2 text-[#64748b] transition-colors hover:bg-[#f8fafc] hover:text-[#0067B1] lg:hidden"
              aria-label="打开助手面板"
            >
              <Bot size={18} />
            </button>
          </div>

          {/* Messages */}
          <div
            ref={scrollContainerRef}
            onScroll={handleScroll}
            className="relative flex-1 overflow-y-auto px-4 py-6 sm:px-6 xl:px-8"
          >
            {showEmpty && (
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center text-center"
              >
                <div className="mb-5 grid h-14 w-14 place-items-center rounded-full bg-[#f0f7ff] ring-1 ring-[#0067B1]/10">
                  <img src="/images/sai-whu-emblem.png" alt="武汉大学人工智能学院" className="h-10 w-10 object-contain" />
                </div>
                <h2 className="font-display text-2xl font-semibold text-[#1e293b]">
                  你好，我是珞樱
                </h2>
                <p className="mt-2.5 max-w-lg text-sm leading-7 text-[#64748b]">
                  武汉大学人工智能学院的校园智能助手。我可以帮助你了解学院介绍、招生培养、科研方向、导师团队、办事流程与校园服务。
                </p>
                <div className="mt-6 flex flex-wrap justify-center gap-2">
                  {QUICK_QUESTIONS.map((q) => (
                    <button
                      key={q}
                      onClick={() => handleSend(q === '学院介绍' ? '请介绍一下武汉大学人工智能学院' : `请介绍一下人工智能学院的${q}相关信息`, [])}
                      className="rounded-full border border-[#d0d8e4] bg-white px-3.5 py-1.5 text-xs text-[#475569] transition-all hover:border-[#0067B1]/40 hover:bg-[#f0f4fa] hover:text-[#0067B1]"
                    >
                      {q}
                    </button>
                  ))}
                </div>
                <p className="mt-5 text-[11px] leading-relaxed text-[#94a3b8]">
                  回答将优先参考学院公开信息与当前会话上下文。
                </p>
              </motion.div>
            )}

            <div className="mx-auto flex max-w-3xl flex-col gap-1">
              {activeSession?.messages.map((message) => <ChatMessage key={message.id} message={message} isGenerating={isGenerating} />)}

              {isGenerating ? (
                currentAiText ? (
                  <ChatMessage
                    message={{
                      id: 'streaming',
                      role: 'assistant',
                      content: currentAiText,
                      timestamp: Date.now(),
                      status: 'streaming',
                    }}
                    isGenerating={isGenerating}
                  />
                ) : (
                  <TypingIndicator />
                )
              ) : null}
            </div>
            <div ref={messagesEndRef} />
          </div>

          {/* New message indicator */}
          <AnimatePresence>
            {showNewMsgIndicator && (
              <motion.button
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                onClick={() => {
                  scrollToBottom()
                  setShowNewMsgIndicator(false)
                  setUserScrolledUp(false)
                }}
                className="absolute bottom-24 left-1/2 z-30 flex -translate-x-1/2 items-center gap-1 rounded-full bg-[#1e293b] px-4 py-2 text-xs text-white shadow-lg"
              >
                <ChevronDown size={14} />
                新消息
              </motion.button>
            )}
          </AnimatePresence>

          {/* Input */}
          <div className="shrink-0 border-t border-[#f1f5f9] bg-white px-4 py-4 sm:px-6 xl:px-8">
            <ChatInput onSend={handleSend} isLoading={isGenerating} />
          </div>
        </section>

        {/* Right Panel - Live2D / Assistant */}
        {live2dVisible && !isCompactLayout && (
          <aside className="hidden w-[320px] shrink-0 xl:w-[360px] lg:block">
            <Live2DPanel
              isSpeaking={isGenerating}
              speechText={currentAiText}
              mood={liveMood}
              audioEvent={liveAudioEvent}
              isOpen={live2dVisible}
              onToggle={toggleLive2D}
            />
          </aside>
        )}
      </div>
    </div>
  )
}
