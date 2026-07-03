import { Outlet } from 'react-router'
import Navbar from './Navbar'
import { Toaster } from './ui/sonner'
import { useReminderSSE } from '../hooks/useReminderSSE'

export default function Layout() {
  useReminderSSE()

  return (
    <div className="min-h-[100dvh] flex flex-col">
      <Navbar />
      <main className="flex-1">
        <Outlet />
      </main>
      <Toaster position="top-right" />
    </div>
  )
}
