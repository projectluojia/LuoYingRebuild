import { Github, Mail, FileText } from 'lucide-react'

const HELP_URL = 'https://www.cnblogs.com/mornhus-xsylf-123/p/19731597'
const GITHUB_URL = 'https://github.com/mornhussakuyo-hub/Luoying-V1-Structure'

export default function Footer() {
  return (
    <footer className="border-t border-[#0067B1]/12 bg-white text-[#1d3552]">
      <div className="mx-auto max-w-7xl px-5 py-10 sm:px-8 lg:px-10">
        <div className="grid gap-8 md:grid-cols-[1fr_auto] md:items-end">
          <div className="flex items-center gap-4">
            <img src="/images/sai-whu-horizontal.png" alt="武汉大学人工智能学院" className="h-12 w-auto max-w-[260px] object-contain" />
            <div className="border-l border-[#0067B1]/16 pl-4">
              <p className="font-display text-2xl font-semibold">珞樱 Luo Ying</p>
              <p className="mt-2 text-sm text-[#49627d]">武汉大学人工智能学院校园智能体系统</p>
            </div>
          </div>

          <div className="flex flex-wrap gap-5 text-sm text-[#49627d]">
            <a href="#agent" className="transition hover:text-[#0067B1]">
              能力总览
            </a>
            <a href="#interaction" className="transition hover:text-[#0067B1]">
              交互链路
            </a>
            <a href="#team" className="transition hover:text-[#0067B1]">
              项目团队
            </a>
            <a href="/chat" className="transition hover:text-[#0067B1]">
              在线对话
            </a>
            <a href="https://sai.whu.edu.cn/" target="_blank" rel="noopener noreferrer" className="transition hover:text-[#0067B1]">
              学院官网
            </a>
            <a href={HELP_URL} target="_blank" rel="noopener noreferrer" className="transition hover:text-[#0067B1]">
              帮助文档
            </a>
          </div>
        </div>

        <div className="mt-10 flex flex-col gap-4 border-t border-[#0067B1]/12 pt-6 text-xs text-[#7190ad] sm:flex-row sm:items-center sm:justify-between">
          <p>© 2026 珞樱项目组 · <a href="https://sai.whu.edu.cn/" target="_blank" rel="noopener noreferrer" className="transition hover:text-[#0067B1]">武汉大学人工智能学院</a></p>
          <div className="flex items-center gap-4">
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" aria-label="GitHub" className="transition hover:text-[#0067B1]">
              <Github size={18} />
            </a>
            <a href={HELP_URL} target="_blank" rel="noopener noreferrer" aria-label="帮助文档" className="transition hover:text-[#0067B1]">
              <FileText size={18} />
            </a>
            <a href="mailto:2564664062@qq.com" aria-label="Email" className="transition hover:text-[#0067B1]">
              <Mail size={18} />
            </a>
          </div>
        </div>
      </div>
    </footer>
  )
}
