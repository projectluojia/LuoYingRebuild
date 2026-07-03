import { motion } from 'framer-motion'
import { MessageSquarePlus, X } from 'lucide-react'
import type { ChatSession } from '../../types/chat'

interface ChatSidebarProps {
  sessions: ChatSession[]
  activeSessionId: string | null
  onNewChat: () => void
  onSwitchSession: (id: string) => void
  isMobile?: boolean
  onClose?: () => void
}

function formatDate(ts: number): string {
  const d = new Date(ts)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 86400000) return '今天'
  if (diff < 86400000 * 2) return '昨天'
  return `${d.getMonth() + 1}/${d.getDate()}`
}

const QUICK_SERVICES = [
  { label: '招生咨询', prompt: '我想了解人工智能学院的招生信息' },
  { label: '培养方案', prompt: '请介绍一下人工智能学院的培养方案' },
  { label: '科研方向', prompt: '人工智能学院有哪些科研方向？' },
  { label: '办事指南', prompt: '请问学院有哪些常用的办事指南？' },
]

export default function ChatSidebar({
  sessions,
  activeSessionId,
  onNewChat,
  onSwitchSession,
  isMobile,
  onClose,
}: ChatSidebarProps) {
  return (
    <div className="flex h-full flex-col overflow-hidden rounded-lg border border-[#dce3ec] bg-white shadow-sm">
      <div className="border-b border-[#e8ecf1] px-4 pb-3 pt-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-full bg-[#f0f7ff]">
              <img src="/images/sai-whu-emblem.png" alt="武汉大学人工智能学院" className="h-7 w-7 object-contain" />
            </div>
            <div>
              <h2 className="font-display text-base font-semibold text-[#1e293b]">珞樱</h2>
              <p className="text-[11px] text-[#94a3b8]">武汉大学人工智能学院</p>
            </div>
          </div>
          {isMobile && onClose && (
            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-[#94a3b8] transition-colors hover:bg-[#f1f5f9] hover:text-[#64748b]"
              aria-label="关闭侧边栏"
            >
              <X size={18} />
            </button>
          )}
        </div>
      </div>

      <div className="px-3 py-3">
        <button
          onClick={onNewChat}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#0067B1] px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#005a96]"
        >
          <MessageSquarePlus size={15} />
          新对话
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-1">
        <p className="px-2 py-1.5 text-[10px] font-medium uppercase tracking-wider text-[#94a3b8]">历史会话</p>
        <div className="flex flex-col gap-1">
          {sessions.map((session) => {
            const isActive = session.id === activeSessionId
            const lastMsg = session.messages[session.messages.length - 1]
            return (
              <motion.button
                key={session.id}
                onClick={() => onSwitchSession(session.id)}
                className={`w-full rounded-lg px-3 py-2 text-left transition-all duration-150 ${
                  isActive
                    ? 'bg-[#f0f7ff] ring-1 ring-[#0067B1]/20'
                    : 'hover:bg-[#f8fafc]'
                }`}
                whileTap={{ scale: 0.985 }}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-[#1e293b]">{session.title}</span>
                  <span className="shrink-0 text-[10px] text-[#94a3b8]">{formatDate(session.updatedAt)}</span>
                </div>
                {lastMsg && (
                  <p className="mt-0.5 truncate text-xs text-[#94a3b8]">
                    {lastMsg.role === 'user' ? '你：' : '珞樱：'}
                    {lastMsg.content.slice(0, 36)}
                  </p>
                )}
              </motion.button>
            )
          })}
          {sessions.length === 0 && (
            <div className="rounded-lg border border-dashed border-[#dce3ec] py-8 text-center text-xs text-[#94a3b8]">
              暂无历史会话
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-[#e8ecf1] px-3 py-3">
        <p className="mb-2 px-1 text-[10px] font-medium uppercase tracking-wider text-[#94a3b8]">常用服务</p>
        <div className="flex flex-col gap-1">
          {QUICK_SERVICES.map((item) => (
            <button
              key={item.label}
              onClick={() => {
                window.dispatchEvent(new CustomEvent('luoying-quick-action', { detail: item.prompt }))
              }}
              className="flex w-full items-center rounded-lg px-3 py-2 text-left text-xs text-[#475569] transition-colors hover:bg-[#f8fafc] hover:text-[#0067B1]"
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
