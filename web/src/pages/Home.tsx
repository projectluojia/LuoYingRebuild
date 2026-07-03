import { useRef, type ReactNode } from 'react'
import { Link } from 'react-router'
import { motion, useInView, useScroll, useTransform } from 'framer-motion'
import {
  ArrowRight,
  AudioLines,
  Bell,
  BookOpen,
  Bot,
  Braces,
  ChevronDown,
  Code2,
  Image,
  MessageCircle,
  Mic2,
  Network,
  NotebookPen,
  Orbit,
  Search,
  Sparkles,
  Users,
  Waves,
} from 'lucide-react'
import Footer from '../components/Footer'

const HELP_URL = 'https://www.cnblogs.com/mornhus-xsylf-123/p/19731597'

const capabilities = [
  {
    id: '01',
    title: '智能对话',
    text: '珞樱能够理解自然语言，根据上下文进行多轮对话。她会记住你说过的话，结合语境给出准确、连贯的回答。',
    icon: MessageCircle,
  },
  {
    id: '02',
    title: '任务执行',
    text: '她不只是聊天——查天气、设提醒、搜论文、写代码，珞樱能理解你的意图并调用对应的能力模块来完成任务。',
    icon: AudioLines,
  },
  {
    id: '03',
    title: '多模态理解',
    text: '发送截图或照片，珞樱就能描述画面、识别文字、分析内容。支持多图对比和针对性提问。',
    icon: Mic2,
  },
  {
    id: '04',
    title: '校园服务',
    text: '每日天气早报、定时提醒、群信息查询、备忘录管理——珞樱是面向校园场景的智能助手。',
    icon: Sparkles,
  },
]

const pipeline = [
  ['Intent Parse', '自然语言意图识别'],
  ['Task Route', '能力模块调度分发'],
  ['Agent Execute', '子智能体协同执行'],
  ['Response Stream', '流式结果输出'],
]

const statusItems = [
  '武汉大学人工智能学院',
  'SCHOOL OF ARTIFICIAL INTELLIGENCE',
  'WUHAN UNIVERSITY',
  '珞樱校园智能助手',
  'sai.whu.edu.cn',
]

const agentCapabilities = [
  {
    icon: MessageCircle,
    title: '自然语言交互',
    text: '无需记忆命令格式，直接用日常语言即可。珞樱能理解上下文、区分对话意图，并在多轮交互中保持连贯。',
  },
  {
    icon: Image,
    title: '图像理解',
    text: '支持图像描述、文字识别、截图分析和多图对比。可直接发送图片或通过引用消息指定分析目标。',
  },
  {
    icon: Code2,
    title: '编程辅助',
    text: '内置编程工作区，支持 Python、C++、Java 等语言的代码编写，可直接执行 Python 脚本并返回结果。',
  },
  {
    icon: Bell,
    title: '定时提醒',
    text: '支持一次性提醒和每日循环提醒，数据持久化存储。提醒触发时会在原对话中通知用户。',
  },
  {
    icon: NotebookPen,
    title: '备忘录系统',
    text: '支持通过自然语言进行备忘录的创建、查看、修改、删除和搜索，数据跨会话持久保存。',
  },
  {
    icon: Search,
    title: '联网搜索',
    text: '对于超出本地知识范围的问题，珞樱会调用搜索引擎获取实时信息，适用于时效性查询和外部资料检索。',
  },
  {
    icon: BookOpen,
    title: '学术论文检索',
    text: '可按关键词检索 arXiv 上的最新论文，返回论文标题和摘要信息，便于快速了解前沿研究方向。',
  },
  {
    icon: Users,
    title: '群信息管理',
    text: '支持查询群基本信息、成员资料、角色权限等，可进行随机抽奖等群互动操作。',
  },
]

function Reveal({
  children,
  delay = 0,
  className = '',
}: {
  children: ReactNode
  delay?: number
  className?: string
}) {
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '-12% 0px' })

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 28 }}
      animate={inView ? { opacity: 1, y: 0 } : undefined}
      transition={{ duration: 0.7, delay, ease: [0.16, 1, 0.3, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

function ScanLines() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <motion.div
        className="absolute left-0 top-[18%] h-px w-full bg-white/45"
        animate={{ x: ['-100%', '100%'] }}
        transition={{ duration: 7.5, repeat: Infinity, ease: 'linear' }}
      />
      <motion.div
        className="absolute right-0 top-[46%] h-px w-2/3 bg-[#f7b7c9]/50"
        animate={{ x: ['100%', '-130%'] }}
        transition={{ duration: 10, repeat: Infinity, ease: 'linear', delay: 1.2 }}
      />
      <motion.div
        className="absolute bottom-[20%] left-0 h-px w-1/2 bg-[#9ed8ff]/45"
        animate={{ x: ['-120%', '210%'] }}
        transition={{ duration: 12, repeat: Infinity, ease: 'linear', delay: 0.6 }}
      />
      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.05)_1px,transparent_1px)] bg-[size:72px_72px]" />
    </div>
  )
}

function StatusTape() {
  return (
    <div className="overflow-hidden border-y border-white/24 bg-[#0067B1]/18 py-3 text-[11px] uppercase tracking-[0.28em] text-white/76 backdrop-blur-sm">
      <motion.div
        className="flex min-w-max gap-8"
        animate={{ x: ['0%', '-50%'] }}
        transition={{ duration: 24, repeat: Infinity, ease: 'linear' }}
      >
        {[...statusItems, ...statusItems].map((item, index) => (
          <span key={`${item}-${index}`} className="flex items-center gap-8">
            {item}
            <span className="h-1 w-1 bg-white/60" />
          </span>
        ))}
      </motion.div>
    </div>
  )
}

export default function Home() {
  const heroRef = useRef<HTMLElement | null>(null)
  const { scrollYProgress } = useScroll({ target: heroRef, offset: ['start start', 'end start'] })
  const heroImageY = useTransform(scrollYProgress, [0, 1], ['0%', '14%'])
  const heroTextY = useTransform(scrollYProgress, [0, 1], ['0%', '34%'])
  const heroOpacity = useTransform(scrollYProgress, [0, 0.78], [1, 0])

  return (
    <div className="min-h-screen bg-[#f7fbff] text-[#1d3552]">
      <section ref={heroRef} className="relative min-h-[100svh] overflow-hidden">
        <motion.div
          className="absolute inset-0 scale-105 bg-cover bg-center"
          style={{
            y: heroImageY,
            backgroundImage: 'url(/images/luoying-campus-ai-bg.png)',
          }}
        />
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(0,43,85,0.78)_0%,rgba(0,103,177,0.34)_48%,rgba(255,255,255,0.05)_100%)]" />
        <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(0,103,177,0.02)_0%,rgba(0,103,177,0.10)_58%,#f7fbff_100%)]" />
        <ScanLines />

        <motion.div
          style={{ y: heroTextY, opacity: heroOpacity }}
          className="relative z-10 mx-auto flex min-h-[100svh] max-w-7xl flex-col justify-end px-5 pb-24 pt-28 sm:px-8 lg:px-10"
        >
          <div className="max-w-4xl">
            <motion.p
              initial={{ opacity: 0, y: 22 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
              className="mb-5 flex items-center gap-3 text-xs uppercase tracking-[0.34em] text-white/70"
            >
              <img src="/images/sai-whu-emblem.png" alt="武汉大学人工智能学院院徽" className="h-9 w-9 object-contain" />
              <a href="https://sai.whu.edu.cn/" target="_blank" rel="noopener noreferrer" className="transition hover:text-white">武汉大学人工智能学院</a>
            </motion.p>

            <motion.h1
              initial={{ opacity: 0, y: 34 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.9, delay: 0.08, ease: [0.16, 1, 0.3, 1] }}
              className="font-display text-[clamp(5.4rem,18vw,15rem)] font-semibold leading-[0.82] tracking-normal text-white"
            >
              珞樱
            </motion.h1>

            <motion.div
              initial={{ opacity: 0, y: 28 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.25, ease: [0.16, 1, 0.3, 1] }}
              className="mt-8 grid max-w-3xl gap-6 border-l border-[#E9A6BC]/70 pl-5 md:grid-cols-[1.1fr_0.9fr]"
            >
              <p className="text-base leading-8 text-white/82 md:text-lg">
                珞樱是武汉大学人工智能学院研发的校园智能体系统。她能够理解自然语言、执行多步骤任务，集成天气查询、定时提醒、论文检索、代码运行、图像理解等多种能力模块，面向校园场景提供智能服务。
              </p>
              <div className="grid content-start gap-3 text-sm text-white/66">
                <div className="flex items-center justify-between border-b border-white/15 pb-2">
                  <span>Frontend</span>
                  <span>Live2D / Voice / Chat</span>
                </div>
                <div className="flex items-center justify-between border-b border-white/15 pb-2">
                  <span>Voice</span>
                  <span>GPT-SoVITS local</span>
                </div>
                <div className="flex items-center justify-between border-b border-white/15 pb-2">
                  <span>Agent</span>
                  <span>V2 多模态 / 编程 / 提醒</span>
                </div>
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.42, ease: [0.16, 1, 0.3, 1] }}
              className="mt-10 flex flex-wrap items-center gap-4"
            >
              <Link
                to="/chat"
                className="group inline-flex items-center gap-3 border border-white bg-white px-6 py-3 text-sm font-semibold text-[#0067B1] transition hover:border-[#E9A6BC] hover:bg-[#E9A6BC] hover:text-white"
              >
                进入对话
                <ArrowRight size={17} className="transition group-hover:translate-x-1" />
              </Link>
              <a
                href="#agent"
                className="inline-flex items-center gap-3 border border-white/35 px-6 py-3 text-sm text-white/88 transition hover:border-white hover:bg-white/10 hover:text-white"
              >
                了解珞樱的能力
              </a>
            </motion.div>
          </div>

          <div className="absolute bottom-0 left-0 right-0">
            <StatusTape />
          </div>
        </motion.div>

        <a
          href="#capabilities"
          aria-label="向下滚动"
          className="absolute bottom-16 right-8 z-20 hidden text-white/75 md:block"
        >
          <ChevronDown className="animate-bounce" size={28} />
        </a>
      </section>

      <section id="capabilities" className="relative border-y border-[#0067B1]/12 bg-[#f7fbff] text-[#1d3552]">
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(0,103,177,.045)_1px,transparent_1px),linear-gradient(90deg,rgba(0,103,177,.04)_1px,transparent_1px)] bg-[size:72px_72px]" />
        <div className="mx-auto grid max-w-7xl gap-10 px-5 py-20 sm:px-8 lg:grid-cols-[0.78fr_1.22fr] lg:px-10 lg:py-28">
          <Reveal>
            <div className="sticky top-28">
              <p className="mb-4 text-xs uppercase tracking-[0.32em] text-[#0067B1]">Agent System</p>
              <h2 className="font-display text-4xl font-semibold leading-tight text-[#1d3552] md:text-6xl">
                面向校园场景的智能体系统。
              </h2>
              <p className="mt-7 max-w-md text-base leading-8 text-[#49627d]">
                珞樱基于大语言模型构建，具备意图识别、任务分发和多智能体协同能力。她能够理解用户需求，自动选择合适的工具模块，在校园群聊场景中提供高效、准确的智能服务。
              </p>
            </div>
          </Reveal>

          <div className="divide-y divide-[#0067B1]/14 border-y border-[#0067B1]/14 bg-white/58 backdrop-blur-sm">
            {capabilities.map((item, index) => {
              const Icon = item.icon
              return (
                <Reveal key={item.id} delay={index * 0.08}>
                  <div className="group grid gap-5 py-8 md:grid-cols-[72px_1fr_52px] md:items-center">
                    <div className="flex items-center gap-4">
                      <span className="font-mono text-xs text-[#7190ad]">{item.id}</span>
                      <Icon size={24} className="text-[#0067B1]/70 transition group-hover:text-[#E36A95]" />
                    </div>
                    <div>
                      <h3 className="text-2xl font-semibold text-[#1d3552]">{item.title}</h3>
                      <p className="mt-3 max-w-2xl text-sm leading-7 text-[#49627d]">{item.text}</p>
                    </div>
                    <ArrowRight className="hidden text-[#7190ad] transition group-hover:translate-x-2 group-hover:text-[#E36A95] md:block" />
                  </div>
                </Reveal>
              )
            })}
          </div>
        </div>
      </section>

      <section id="agent" className="relative overflow-hidden bg-[#fff7fb] text-[#1d3552]">
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(227,106,149,.04)_1px,transparent_1px),linear-gradient(90deg,rgba(227,106,149,.03)_1px,transparent_1px)] bg-[size:72px_72px]" />
        <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:px-10 lg:py-28">
          <Reveal className="max-w-3xl">
            <p className="mb-4 text-xs uppercase tracking-[0.32em] text-[#E36A95]">Agent Capabilities</p>
            <h2 className="font-display text-4xl font-semibold leading-tight md:text-6xl">
              集成多种能力，覆盖校园服务场景。
            </h2>
            <p className="mt-7 text-base leading-8 text-[#49627d]">
              珞樱采用多智能体架构，将对话理解、任务规划和工具调用整合为统一流程。用户只需用自然语言表达需求，系统会自动路由到对应的能力模块执行。
            </p>
          </Reveal>

          <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {agentCapabilities.map((item, index) => {
              const Icon = item.icon
              return (
                <Reveal key={item.title} delay={index * 0.06}>
                  <div className="group relative flex h-full flex-col border border-[#0067B1]/12 bg-white/62 p-6 backdrop-blur-sm transition-all hover:-translate-y-1 hover:border-[#E36A95]/40 hover:shadow-[0_20px_50px_rgba(227,106,149,.12)]">
                    <Icon size={28} className="mb-5 text-[#0067B1]/70 transition group-hover:text-[#E36A95]" />
                    <h3 className="text-lg font-semibold text-[#1d3552]">{item.title}</h3>
                    <p className="mt-3 flex-1 text-sm leading-7 text-[#49627d]">{item.text}</p>
                    <motion.div
                      className="mt-5 h-0.5 w-8 bg-[#E36A95]/40"
                      whileHover={{ width: '100%' }}
                      transition={{ duration: 0.4 }}
                    />
                  </div>
                </Reveal>
              )
            })}
          </div>

          <Reveal delay={0.5}>
            <div className="mt-14 border border-[#0067B1]/12 bg-white/42 p-8 backdrop-blur-sm">
              <div className="grid gap-8 md:grid-cols-[1fr_auto] md:items-center">
                <div>
                  <h3 className="text-xl font-semibold text-[#1d3552]">持续演进的校园智能体</h3>
                  <p className="mt-3 text-sm leading-7 text-[#49627d]">
                    珞樱仍在持续迭代中。后续将增强多模态理解能力、提升工具调用稳定性、扩展更多校园服务场景，逐步成长为更完善的校园智能助手。
                  </p>
                </div>
                <Link
                  to="/chat"
                  className="inline-flex shrink-0 items-center gap-3 bg-[#E36A95] px-6 py-3 text-sm font-semibold text-white transition hover:bg-[#0067B1]"
                >
                  去试试看
                  <ArrowRight size={17} />
                </Link>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      <section id="interaction" className="relative overflow-hidden bg-[#eef7ff] text-[#1d3552]">
        <div className="absolute left-0 top-0 h-full w-px bg-[#0067B1]/18 md:left-[8%]" />
        <div className="absolute right-[14%] top-0 hidden h-full w-px bg-[#0067B1]/12 md:block" />
        <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:px-10 lg:py-28">
          <Reveal className="max-w-3xl">
            <p className="mb-4 text-xs uppercase tracking-[0.32em] text-[#0067B1]">Interaction Pipeline</p>
            <h2 className="font-display text-4xl font-semibold leading-tight md:text-6xl">
              从一句话到一次服务，每一步都经过设计。
            </h2>
          </Reveal>

          <div className="mt-16 grid gap-0 border-y border-[#0067B1]/20 bg-white/42 lg:grid-cols-4">
            {pipeline.map(([title, desc], index) => (
              <Reveal key={title} delay={index * 0.08}>
                <div className="relative min-h-[260px] border-[#0067B1]/18 px-6 py-8 lg:border-r">
                  <span className="font-mono text-xs text-[#7190ad]">0{index + 1}</span>
                  <h3 className="mt-16 text-2xl font-semibold">{title}</h3>
                  <p className="mt-3 text-sm leading-7 text-[#49627d]">{desc}</p>
                  <motion.div
                    className="absolute bottom-8 left-6 h-1 w-16 bg-[#E36A95]"
                    animate={{ scaleX: [0.2, 1, 0.2] }}
                    transition={{ duration: 2.4, repeat: Infinity, delay: index * 0.25 }}
                    style={{ transformOrigin: 'left' }}
                  />
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-[#fff7fb] text-[#1d3552]">
        <div className="mx-auto grid max-w-7xl gap-12 px-5 py-20 sm:px-8 lg:grid-cols-[0.9fr_1.1fr] lg:px-10 lg:py-28">
          <Reveal>
            <div className="relative overflow-hidden border border-[#0067B1]/14 bg-white/56">
              <img
                src="/images/luoying-campus-ai-bg.png"
                alt="珞樱视觉设定"
                className="aspect-[4/5] w-full object-cover object-center opacity-90"
              />
              <div className="absolute inset-x-0 bottom-0 border-t border-white/30 bg-[#0067B1]/56 px-5 py-4 text-xs uppercase tracking-[0.24em] text-white/86 backdrop-blur-sm">
                武汉大学人工智能学院 · 珞樱校园智能助手
              </div>
            </div>
          </Reveal>

          <Reveal delay={0.1} className="self-center">
            <p className="mb-4 text-xs uppercase tracking-[0.32em] text-[#E36A95]">Visual Direction</p>
            <h2 className="font-display text-4xl font-semibold leading-tight md:text-6xl">
              融合校园美学与技术表达。
            </h2>
            <p className="mt-7 text-base leading-8 text-[#49627d]">
              设计灵感源自武汉大学的樱花景观和校园建筑，结合人工智能的科技感。界面采用学院品牌色彩体系，兼顾学术严谨性与交互友好性。
            </p>
            <div className="mt-10 grid gap-4 sm:grid-cols-3">
              {[
                [Bot, '智能体架构'],
                [Waves, '流式对话引擎'],
                [Network, '前后端分离'],
                [Braces, '多模块协同'],
                [Orbit, '校园场景适配'],
                [Sparkles, '学院品牌'],
              ].map(([Icon, label]) => {
                const Glyph = Icon as typeof Bot
                return (
                  <div key={label as string} className="border border-[#0067B1]/12 bg-white/62 px-4 py-4">
                    <Glyph size={20} className="mb-5 text-[#0067B1]" />
                    <span className="text-sm text-[#49627d]">{label as string}</span>
                  </div>
                )
              })}
            </div>
            <Link
              to="/chat"
              className="mt-10 inline-flex items-center gap-3 border border-[#0067B1]/24 px-6 py-3 text-sm text-[#0067B1] transition hover:border-[#0067B1] hover:bg-[#0067B1] hover:text-white"
            >
              进入珞樱界面
              <ArrowRight size={17} />
            </Link>
          </Reveal>
        </div>
      </section>

      <section id="team" className="border-y border-[#0067B1]/12 bg-[#f7fbff] text-[#1d3552]">
        <div className="mx-auto grid max-w-7xl gap-8 px-5 py-16 sm:px-8 md:grid-cols-[1fr_auto] md:items-end lg:px-10">
          <Reveal>
            <p className="mb-4 text-xs uppercase tracking-[0.32em] text-[#0067B1]">Project Team</p>
            <h2 className="font-display text-4xl font-semibold md:text-5xl">武汉大学人工智能学院</h2>
            <p className="mt-5 max-w-2xl text-sm leading-7 text-[#49627d]">
              珞樱由武汉大学人工智能学院团队研发，涵盖前端交互、后端服务、语音合成、视觉呈现等多个技术方向。项目持续迭代，致力于打造面向校园场景的智能体系统。
            </p>
          </Reveal>
          <Reveal delay={0.12}>
            <Link
              to="/chat"
              className="inline-flex items-center gap-3 bg-[#0067B1] px-6 py-3 text-sm font-semibold text-white transition hover:bg-[#E36A95]"
            >
              开始对话
              <ArrowRight size={17} />
            </Link>
          </Reveal>
        </div>
      </section>

      <section id="docs" className="bg-[#fff7fb] text-[#1d3552]">
        <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:px-10 lg:py-28">
          <Reveal className="max-w-3xl">
            <p className="mb-4 text-xs uppercase tracking-[0.32em] text-[#E36A95]">Documentation</p>
            <h2 className="font-display text-4xl font-semibold leading-tight md:text-5xl">
              使用帮助与开发文档。
            </h2>
            <p className="mt-7 text-base leading-8 text-[#49627d]">
              了解珞樱的完整功能列表、命令系统、配置方式和开发指南。文档涵盖所有已支持的 Agent 能力、斜杠命令说明以及常见问题解答。
            </p>
          </Reveal>

          <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Reveal>
              <a
                href={HELP_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex h-full flex-col border border-[#0067B1]/12 bg-white/62 p-6 backdrop-blur-sm transition-all hover:-translate-y-1 hover:border-[#E36A95]/40 hover:shadow-[0_20px_50px_rgba(227,106,149,.12)]"
              >
                <BookOpen size={28} className="mb-5 text-[#0067B1]/70 transition group-hover:text-[#E36A95]" />
                <h3 className="text-lg font-semibold text-[#1d3552]">帮助文档</h3>
                <p className="mt-3 flex-1 text-sm leading-7 text-[#49627d]">
                  珞樱的完整使用指南，包括功能介绍、命令列表、配置说明和常见问题。
                </p>
                <div className="mt-5 flex items-center gap-2 text-sm text-[#0067B1] transition group-hover:text-[#E36A95]">
                  <span>查看文档</span>
                  <ArrowRight size={14} className="transition group-hover:translate-x-1" />
                </div>
              </a>
            </Reveal>

            <Reveal delay={0.08}>
              <Link
                to="/chat"
                className="group flex h-full flex-col border border-[#0067B1]/12 bg-white/62 p-6 backdrop-blur-sm transition-all hover:-translate-y-1 hover:border-[#E36A95]/40 hover:shadow-[0_20px_50px_rgba(227,106,149,.12)]"
              >
                <MessageCircle size={28} className="mb-5 text-[#0067B1]/70 transition group-hover:text-[#E36A95]" />
                <h3 className="text-lg font-semibold text-[#1d3552]">在线体验</h3>
                <p className="mt-3 flex-1 text-sm leading-7 text-[#49627d]">
                  直接与珞樱对话，体验智能体的各项能力。支持自然语言交互和实时流式响应。
                </p>
                <div className="mt-5 flex items-center gap-2 text-sm text-[#0067B1] transition group-hover:text-[#E36A95]">
                  <span>开始对话</span>
                  <ArrowRight size={14} className="transition group-hover:translate-x-1" />
                </div>
              </Link>
            </Reveal>

            <Reveal delay={0.16}>
              <a
                href="https://github.com/mornhussakuyo-hub/Luoying-V1-Structure"
                target="_blank"
                rel="noopener noreferrer"
                className="group flex h-full flex-col border border-[#0067B1]/12 bg-white/62 p-6 backdrop-blur-sm transition-all hover:-translate-y-1 hover:border-[#E36A95]/40 hover:shadow-[0_20px_50px_rgba(227,106,149,.12)]"
              >
                <Code2 size={28} className="mb-5 text-[#0067B1]/70 transition group-hover:text-[#E36A95]" />
                <h3 className="text-lg font-semibold text-[#1d3552]">开源仓库</h3>
                <p className="mt-3 flex-1 text-sm leading-7 text-[#49627d]">
                  V1 版本的架构代码已开源，包含基础的 Agent 框架和能力实现。
                </p>
                <div className="mt-5 flex items-center gap-2 text-sm text-[#0067B1] transition group-hover:text-[#E36A95]">
                  <span>查看代码</span>
                  <ArrowRight size={14} className="transition group-hover:translate-x-1" />
                </div>
              </a>
            </Reveal>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  )
}
