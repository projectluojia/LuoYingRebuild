import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { AnimatePresence, motion } from 'framer-motion'
import { ArrowRight, Menu, X } from 'lucide-react'

const navLinks = [
  { label: '首页', path: '/' },
  { label: '对话', path: '/chat' },
  { label: '能力', path: '/#agent' },
  { label: '学院官网', path: 'https://sai.whu.edu.cn/', external: true },
]

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 36)
    handleScroll()
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  const handleNavClick = (path: string) => {
    setMobileOpen(false)

    if (path.startsWith('/#')) {
      const id = path.slice(2)
      if (location.pathname !== '/') {
        navigate('/')
        window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' }), 240)
        return
      }
      document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
      return
    }

    navigate(path)
  }

  const isDarkBar = scrolled || location.pathname !== '/'

  return (
    <nav
      className={`fixed left-0 right-0 top-0 z-50 border-b transition duration-300 ${
        isDarkBar
          ? 'border-[#e2e8f0] bg-white/95 shadow-sm backdrop-blur-sm'
          : 'border-white/0 bg-transparent'
      }`}
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8 lg:px-10">
        <Link to="/" className="group flex items-center gap-3" onClick={() => setMobileOpen(false)}>
          <img src="/images/sai-whu-emblem.png" alt="武汉大学人工智能学院院徽" className="h-10 w-10 object-contain" />
          <span className="leading-none">
            <span className={`block font-display text-lg font-semibold ${isDarkBar ? 'text-[#0067B1]' : 'text-white'}`}>珞樱</span>
            <span className={`block pt-1 text-[10px] uppercase tracking-[0.26em] ${isDarkBar ? 'text-[#0067B1]/62' : 'text-white/62'}`}>Luo Ying</span>
          </span>
        </Link>

        <div className="hidden items-center gap-9 md:flex">
          {navLinks.map((link) => {
            if ('external' in link && link.external) {
              return (
                <a
                  key={link.label}
                  href={link.path}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`group relative text-sm transition ${
                    isDarkBar ? 'text-[#1d3552]/68 hover:text-[#0067B1]' : 'text-white/66 hover:text-white'
                  }`}
                >
                  {link.label}
                </a>
              )
            }
            const active = location.pathname === link.path
            return (
              <button
                key={link.label}
                onClick={() => handleNavClick(link.path)}
                className={`group relative text-sm transition ${
                  active
                    ? isDarkBar ? 'text-[#0067B1]' : 'text-white'
                    : isDarkBar ? 'text-[#1d3552]/68 hover:text-[#0067B1]' : 'text-white/66 hover:text-white'
                }`}
              >
                {link.label}
                <span
                  className={`absolute -bottom-2 left-0 h-px transition-all ${isDarkBar ? 'bg-[#E9A6BC]' : 'bg-white'} ${
                    active ? 'w-full' : 'w-0 group-hover:w-full'
                  }`}
                />
              </button>
            )
          })}
        </div>

        <button
          onClick={() => navigate('/chat')}
          className={`hidden items-center gap-2 border px-4 py-2 text-sm transition md:inline-flex ${
            isDarkBar
              ? 'border-[#0067B1]/24 text-[#0067B1] hover:border-[#0067B1] hover:bg-[#0067B1] hover:text-white'
              : 'border-white/32 text-white hover:border-white hover:bg-white hover:text-[#0067B1]'
          }`}
        >
          开始对话
          <ArrowRight size={16} />
        </button>

        <button
          className={`grid h-10 w-10 place-items-center border md:hidden ${
            isDarkBar ? 'border-[#0067B1]/24 text-[#0067B1]' : 'border-white/24 text-white'
          }`}
          onClick={() => setMobileOpen((value) => !value)}
          aria-label={mobileOpen ? '关闭菜单' : '打开菜单'}
        >
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.22 }}
            className="overflow-hidden border-t border-[#0067B1]/12 bg-white/96 backdrop-blur-xl md:hidden"
          >
            <div className="grid gap-1 px-5 py-5">
              {navLinks.map((link) => {
                if ('external' in link && link.external) {
                  return (
                    <a
                      key={link.label}
                      href={link.path}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="border-b border-[#0067B1]/10 py-4 text-left text-base text-[#1d3552]/76"
                    >
                      {link.label}
                    </a>
                  )
                }
                return (
                  <button
                    key={link.label}
                    onClick={() => handleNavClick(link.path)}
                    className="border-b border-[#0067B1]/10 py-4 text-left text-base text-[#1d3552]/76"
                  >
                    {link.label}
                  </button>
                )
              })}
              <button
                onClick={() => handleNavClick('/chat')}
                className="mt-4 inline-flex items-center justify-center gap-2 bg-[#0067B1] px-5 py-3 text-sm font-semibold text-white"
              >
                开始对话
                <ArrowRight size={16} />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  )
}
