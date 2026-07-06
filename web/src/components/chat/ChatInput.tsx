import { AnimatePresence, motion } from 'framer-motion'
import { FileText, Image, Paperclip, Send, X } from 'lucide-react'
import type { ChangeEvent, KeyboardEvent } from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { FileAttachment } from '../../types/chat'

interface ChatInputProps {
  onSend: (text: string, attachments: FileAttachment[]) => void
  isLoading: boolean
}

function generateId(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}

export default function ChatInput({ onSend, isLoading }: ChatInputProps) {
  const [text, setText] = useState('')
  const [attachments, setAttachments] = useState<FileAttachment[]>([])
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`
  }, [text])

  const handleSend = useCallback(() => {
    if ((!text.trim() && attachments.length === 0) || isLoading) return
    onSend(text.trim(), attachments)
    setText('')
    setAttachments([])
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }, [attachments, isLoading, onSend, text])

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSend()
    }
  }

  const handleFileSelect = (event: ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files
    if (!files) return
    Array.from(files).forEach((file) => {
      setAttachments((prev) => [
        ...prev,
        {
          id: generateId(),
          name: file.name,
          size: file.size,
          type: file.type || 'application/octet-stream',
          status: 'selected',
        },
      ])
    })
    event.target.value = ''
  }

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((attachment) => attachment.id !== id))
  }

  const canSend = text.trim().length > 0 || attachments.length > 0

  return (
    <div className="mx-auto w-full max-w-4xl">
      <AnimatePresence>
        {attachments.length > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mb-2 flex gap-2 overflow-x-auto pb-1"
          >
            {attachments.map((attachment) => (
              <motion.div
                key={attachment.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -10 }}
                className="flex shrink-0 items-center gap-2 rounded-lg border border-[#e2e8f0] bg-white px-3 py-1.5"
              >
                <FileText size={14} className="text-[#0067B1]" />
                <span className="max-w-[140px] truncate text-xs text-[#1e293b]">{attachment.name}</span>
                <button
                  onClick={() => removeAttachment(attachment.id)}
                  className="rounded p-0.5 text-[#94a3b8] transition-colors hover:bg-[#f1f5f9] hover:text-[#ef4444]"
                  aria-label="移除附件"
                >
                  <X size={12} />
                </button>
              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex items-end gap-2 rounded-lg border border-[#dce3ec] bg-white px-3 py-2.5 shadow-sm transition-all duration-200 focus-within:border-[#0067B1]/40 focus-within:shadow-md">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="向珞樱提问：招生、课程、科研、办事流程……"
          rows={1}
          className="max-h-[160px] flex-1 resize-none border-none bg-transparent py-1.5 text-[15px] leading-relaxed text-[#1e293b] outline-none placeholder:text-[#94a3b8]"
          disabled={isLoading}
        />

        <div className="flex shrink-0 items-center gap-1 pb-1">
          <button
            onClick={() => fileInputRef.current?.click()}
            className="rounded-lg p-2 text-[#94a3b8] opacity-70 transition-colors hover:bg-[#f1f5f9] hover:text-[#0067B1] hover:opacity-100"
            aria-label="上传文件"
            disabled={isLoading}
          >
            <Paperclip size={18} />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.doc,.docx,.txt,.md,.csv,.json,.py,.js,.html,.css"
            className="hidden"
            onChange={handleFileSelect}
          />

          <button
            onClick={() => imageInputRef.current?.click()}
            className="rounded-lg p-2 text-[#94a3b8] opacity-70 transition-colors hover:bg-[#f1f5f9] hover:text-[#0067B1] hover:opacity-100"
            aria-label="上传图片"
            disabled={isLoading}
          >
            <Image size={18} />
          </button>
          <input
            ref={imageInputRef}
            type="file"
            multiple
            accept=".jpg,.jpeg,.png,.gif,.webp"
            className="hidden"
            onChange={handleFileSelect}
          />

          <button
            onClick={handleSend}
            disabled={!canSend || isLoading}
            className={`ml-1 grid h-9 w-9 place-items-center rounded-lg transition-all duration-150 ${
              canSend && !isLoading
                ? 'bg-[#0067B1] text-white shadow-sm hover:bg-[#005a96] active:scale-95'
                : 'cursor-not-allowed bg-[#f1f5f9] text-[#b0bec5]'
            }`}
            aria-label="发送消息"
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}
