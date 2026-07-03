import { useCallback } from 'react';

interface StartMenuProps {
  onStartChat: () => void;
  onOpenHistory: () => void;
}

// 角色配置
const CHARACTER = {
  name: '珞樱',
  level: 106,
  id: '857594593',
  greeting: '贵安，博士。我是珞樱，今天有什么需要我协助的吗？',
};

export function StartMenu({ onStartChat, onOpenHistory }: StartMenuProps) {
  const handleStartChat = useCallback(() => {
    onStartChat();
  }, [onStartChat]);

  const handleOpenHistory = useCallback(() => {
    onOpenHistory();
  }, [onOpenHistory]);

  return (
    <div className="relative h-full w-full flex items-center justify-center overflow-hidden">
      {/* 背景 */}
      <div className="static-bg" />

      <div
        className="relative z-10 flex gap-8 px-8"
        style={{ perspective: '1200px' }}
      >
        {/* 左侧面板 - 玩家卡片 */}
        <aside
          className="w-72 shrink-0 animate-spring"
          style={{ transform: 'translateZ(30px) rotateY(8deg)', transformOrigin: 'right center' }}
        >
          <div
            className="panel rounded-xl p-6"
            style={{ transformStyle: 'preserve-3d' }}
          >
            {/* 等级和玩家信息 */}
            <div className="flex items-center gap-5 mb-6">
              {/* 等级圆形 */}
              <div
                className="w-20 h-20 rounded-full flex flex-col items-center justify-center shrink-0"
                style={{
                  background: 'linear-gradient(135deg, rgba(255, 145, 164, 0.3), rgba(74, 169, 255, 0.3))',
                  border: '3px solid var(--color-pink-primary)',
                  boxShadow: 'var(--shadow-glow-pink)',
                }}
              >
                <span
                  className="text-2xl font-bold leading-none"
                  style={{
                    fontFamily: 'var(--font-display)',
                    color: 'var(--color-pink-primary)',
                  }}
                >
                  {CHARACTER.level}
                </span>
                <span
                  className="text-xs tracking-wider mt-0.5"
                  style={{ color: 'var(--color-blue-deep)' }}
                >
                  LV
                </span>
              </div>

              {/* 玩家信息 */}
              <div>
                <div
                  className="text-xl font-bold mb-1"
                  style={{ color: 'var(--color-blue-deep)' }}
                >
                  {CHARACTER.name}
                </div>
                <div
                  className="text-xs opacity-60"
                  style={{ color: 'var(--color-blue-deep)' }}
                >
                  ID: {CHARACTER.id}
                </div>
              </div>
            </div>

            {/* 分隔线 */}
            <div
              className="h-px mb-5"
              style={{
                background: 'linear-gradient(90deg, transparent, var(--color-pink-primary), transparent)',
              }}
            />

            {/* 待机语音 */}
            <div
              className="text-sm leading-relaxed"
              style={{ color: 'var(--color-blue-deep)', opacity: 0.8 }}
            >
              <div
                className="text-xs mb-2 font-semibold tracking-wide"
                style={{ color: 'var(--color-pink-primary)' }}
              >
                待机语音
              </div>
              <p className="italic">{CHARACTER.greeting}</p>
            </div>
          </div>
        </aside>

        {/* 右侧面板 - 功能导航 */}
        <section
          className="flex flex-col gap-5 animate-spring stagger-2"
          style={{ transform: 'translateZ(30px) rotateY(-5deg)', transformOrigin: 'left center' }}
        >
          {/* 货币/状态区域 */}
          <div className="flex gap-4">
            <StatusBadge label="在线" value="✓" color="pink" />
            <StatusBadge label="会话" value="0" color="blue" />
          </div>

          {/* 主要导航按钮 */}
          <div className="flex flex-col gap-3">
            <NavButton
              en="Squads"
              zh="开始聊天"
              description="创建新对话"
              onClick={handleStartChat}
              primary
            />
            <NavButton
              en="Operator"
              zh="历史管理"
              description="管理对话与角色"
              onClick={handleOpenHistory}
            />
          </div>

          {/* 次要导航 */}
          <div className="flex gap-3 mt-2">
            <SmallNavButton label="设置" icon="⚙" onClick={() => {}} />
            <SmallNavButton label="关于" icon="ℹ" onClick={() => {}} />
          </div>
        </section>
      </div>
    </div>
  );
}

// 状态徽章组件
function StatusBadge({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: 'pink' | 'blue';
}) {
  const isPink = color === 'pink';
  return (
    <div
      className="flex items-center gap-2 px-4 py-2 rounded-lg transition-all hover-lift"
      style={{
        background: isPink
          ? 'rgba(255, 145, 164, 0.15)'
          : 'rgba(74, 169, 255, 0.15)',
        border: `1px solid ${
          isPink ? 'var(--color-border-pink)' : 'var(--color-border-blue)'
        }`,
      }}
    >
      <span
        className="text-xs font-semibold"
        style={{ color: 'var(--color-blue-deep)', opacity: 0.7 }}
      >
        {label}
      </span>
      <span
        className="text-sm font-bold"
        style={{ color: isPink ? 'var(--color-pink-primary)' : 'var(--color-blue-light)' }}
      >
        {value}
      </span>
    </div>
  );
}

// 导航按钮组件
function NavButton({
  en,
  zh,
  description,
  onClick,
  primary = false,
}: {
  en: string;
  zh: string;
  description: string;
  onClick: () => void;
  primary?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className="group w-64 h-20 flex flex-col items-start justify-center px-6 py-3 rounded-xl transition-all hover-lift"
      style={{
        background: primary
          ? 'linear-gradient(135deg, rgba(255, 145, 164, 0.25), rgba(74, 169, 255, 0.25))'
          : 'linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(232, 243, 255, 0.90))',
        border: `1px solid ${
          primary ? 'var(--color-border-pink)' : 'var(--color-border-blue)'
        }`,
        boxShadow: 'var(--shadow-panel-sm)',
        borderLeft: `4px solid ${primary ? 'var(--color-pink-primary)' : 'var(--color-blue-light)'}`,
      }}
    >
      <span
        className="text-xl font-bold tracking-wide transition-colors"
        style={{
          fontFamily: 'var(--font-display)',
          fontStyle: 'italic',
          color: primary ? 'var(--color-pink-primary)' : 'var(--color-blue-deep)',
        }}
      >
        {en}
      </span>
      <span
        className="text-sm font-semibold mt-0.5 transition-colors"
        style={{ color: 'var(--color-blue-deep)' }}
      >
        {zh}
      </span>
      <span
        className="text-xs mt-1 opacity-0 group-hover:opacity-60 transition-opacity"
        style={{ color: 'var(--color-blue-deep)' }}
      >
        {description}
      </span>
    </button>
  );
}

// 小型导航按钮
function SmallNavButton({
  label,
  icon,
  onClick,
}: {
  label: string;
  icon: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all hover-lift hover-scale"
      style={{
        background: 'rgba(255, 255, 255, 0.85)',
        border: '1px solid var(--color-border-blue)',
        color: 'var(--color-blue-deep)',
      }}
    >
      <span>{icon}</span>
      <span>{label}</span>
    </button>
  );
}
