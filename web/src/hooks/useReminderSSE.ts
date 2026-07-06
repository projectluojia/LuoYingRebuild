import { useEffect } from 'react'
import { toast } from 'sonner'

const API_BASE = import.meta.env.DEV ? '/api' : ''
const RECONNECT_DELAY = 3000

export function useReminderSSE() {
  useEffect(() => {
    let es: EventSource | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let unmounted = false

    function connect() {
      if (unmounted) return

      es = new EventSource(`${API_BASE}/events`)

      es.addEventListener('reminder', (e) => {
        try {
          const data = JSON.parse(e.data)
          toast.info(data.text || '你有一条新提醒', {
            duration: 8000,
          })
        } catch {
          toast.info(e.data || '你有一条新提醒')
        }
      })

      es.onerror = () => {
        es?.close()
        es = null
        if (!unmounted) {
          reconnectTimer = setTimeout(connect, RECONNECT_DELAY)
        }
      }
    }

    connect()

    return () => {
      unmounted = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      es?.close()
    }
  }, [])
}
