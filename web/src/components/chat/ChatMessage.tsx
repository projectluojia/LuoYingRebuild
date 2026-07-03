import { motion } from 'framer-motion'
import { Check, Copy, Download, FileText, User } from 'lucide-react'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeHighlight from 'rehype-highlight'
import type { Message } from '../../types/chat'
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/github.min.css'

interface ChatMessageProps {
  message: Message
  isGenerating?: boolean
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function normalizeLatex(text: string): string {
  return text
    .replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$')
    .replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$')
    .replace(/\\bf\{/g, '\\mathbf{')
    .replace(/\\it\b/g, '\\textit')
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

export default function ChatMessage({ message, isGenerating = false }: ChatMessageProps) {
  const isUser = message.role === 'user'
  const [copied, setCopied] = useState(false)
  const isStreaming = message.status === 'streaming'

  const handleCopy = () => {
    void navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }

  return (
    <motion.div
      initial={isUser ? { opacity: 0, x: 12 } : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, x: 0, y: 0 }}
      transition={{ duration: isUser ? 0.2 : 0.28, ease: [0.16, 1, 0.3, 1] }}
      className={`group mb-4 flex items-start gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
    >
      {isUser ? (
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#0067B1] text-white">
          <User size={14} />
        </div>
      ) : (
        <div className="relative h-8 w-8 shrink-0 overflow-hidden rounded-full bg-white ring-1 ring-[#0067B1]/15">
          <img src="/images/sai-whu-emblem.png" alt="珞樱" className="h-full w-full object-contain p-0.5" />
          {isStreaming && isGenerating && (
            <span className="absolute inset-0 rounded-full ring-2 ring-[#0067B1]/30 animate-pulse" />
          )}
        </div>
      )}

      <div className={`flex max-w-[82%] flex-col sm:max-w-[75%] ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className={`relative px-4 py-3 ${
            isUser
              ? 'rounded-2xl rounded-br-md bg-[#0067B1] text-white'
              : 'rounded-2xl rounded-bl-md border border-[#e2e8f0] bg-white text-[#1e293b] shadow-sm'
          }`}
        >
          {message.attachments && message.attachments.length > 0 && (
            <div className="mb-2.5 flex flex-col gap-1.5">
              {message.attachments.map((attachment) => <FileChip key={attachment.id} attachment={attachment} />)}
            </div>
          )}

          {message.attachments?.some((attachment) => attachment.type.startsWith('image/')) && (
            <div className="mb-2.5">
              {message.attachments
                .filter((attachment) => attachment.type.startsWith('image/'))
                .map((image) => (
                  <img
                    key={image.id}
                    src={image.url ?? '/live2d-placeholder.jpg'}
                    alt={image.name}
                    className="max-h-[300px] max-w-full rounded border border-white/70 object-contain"
                  />
                ))}
            </div>
          )}

          {message.content && (
            <div className={`markdown-body ${isUser ? 'markdown-user' : 'markdown-assistant'}`}>
              {isUser ? (
                <p className="whitespace-pre-wrap">{message.content}</p>
              ) : isStreaming ? (
                <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
              ) : (
                <ReactMarkdown
                  remarkPlugins={[remarkMath]}
                  rehypePlugins={[rehypeKatex, rehypeHighlight]}
                  components={{
                    code({ className, children, ...props }) {
                      const match = /language-(\w+)/.exec(className || '')
                      const isInline = !match
                      return isInline ? (
                        <code className="inline-code" {...props}>
                          {children}
                        </code>
                      ) : (
                        <code className={className} {...props}>
                          {children}
                        </code>
                      )
                    },
                  }}
                >
                  {normalizeLatex(message.content)}
                </ReactMarkdown>
              )}
            </div>
          )}

          {!isUser && message.status === 'streaming' && (
            <span className="ml-1 inline-block h-3.5 w-0.5 translate-y-0.5 animate-caret-blink bg-[#0067B1]" />
          )}
        </div>

        {!isUser ? (
          <div className="mt-1 flex items-center gap-3 px-1 opacity-0 transition-opacity duration-200 group-hover:opacity-70">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 text-[10px] text-[#94a3b8] transition-colors hover:text-[#0067B1]"
              aria-label="复制内容"
            >
              {copied ? <Check size={11} /> : <Copy size={11} />}
              {copied ? '已复制' : '复制'}
            </button>
            <span className="text-[10px] text-[#94a3b8]">{formatTime(message.timestamp)}</span>
          </div>
        ) : (
          <span className="mt-1 px-1 text-[10px] text-[#94a3b8] opacity-0 transition-opacity duration-200 group-hover:opacity-70">
            {formatTime(message.timestamp)}
          </span>
        )}
      </div>
    </motion.div>
  )
}

function FileChip({ attachment }: { attachment: { id: string; name: string; size: number; type: string; status?: string } }) {
  return (
    <div className="group/file flex cursor-pointer items-center gap-2.5 rounded-lg border border-[#e2e8f0] bg-[#f8fafc] px-3 py-2 transition-colors hover:border-[#0067B1]/30">
      <FileText size={15} className="shrink-0 text-[#0067B1]" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-[#1e293b]">{attachment.name}</p>
        <p className="text-[10px] text-[#94a3b8]">{formatFileSize(attachment.size)}</p>
      </div>
      <button className="rounded bg-[#0067B1] p-1.5 text-white opacity-0 transition-opacity group-hover/file:opacity-100" aria-label="下载文件">
        <Download size={12} />
      </button>
    </div>
  )
}
