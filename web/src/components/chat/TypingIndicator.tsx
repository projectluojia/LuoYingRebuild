import { motion } from 'framer-motion'

export default function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] as [number, number, number, number] }}
      className="flex items-start gap-3 mb-4"
    >
      <div className="relative h-8 w-8 shrink-0 overflow-hidden rounded-full bg-white ring-1 ring-[#0067B1]/15">
        <img src="/images/sai-whu-emblem.png" alt="珞樱" className="h-full w-full object-contain p-0.5" />
      </div>

      <div className="rounded-2xl rounded-bl-md border border-[#e2e8f0] bg-white px-5 py-3.5 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1">
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                className="h-1.5 w-1.5 rounded-full bg-[#0067B1]"
                animate={{
                  y: [0, -5, 0],
                }}
                transition={{
                  duration: 0.6,
                  repeat: Infinity,
                  delay: i * 0.15,
                  ease: 'easeInOut',
                }}
              />
            ))}
          </div>
          <span className="text-xs text-[#94a3b8]">珞樱正在思考…</span>
        </div>
      </div>
    </motion.div>
  )
}
