import { useLive2D } from '../live2d/Live2DContext';

interface Live2DPanelProps {
  /** URL of a Live2D model manifest (e.g. .model3.json). */
  modelUrl?: string | null;
  /** Whether the panel is collapsed (thin strip). */
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

/** Live2D avatar panel. Renders a placeholder when no model is loaded. */
export function Live2DPanel({ collapsed = false, onToggleCollapse }: Live2DPanelProps) {
  const { isLoaded } = useLive2D();

  if (collapsed) {
    return (
      <div
        className="h-full flex flex-col items-center justify-center cursor-pointer transition-all"
        style={{ width: 40 }}
        onClick={onToggleCollapse}
        title="展开 Live2D 面板"
      >
        <div
          className="flex-1 w-full rounded-l-xl flex items-center justify-center"
          style={{
            background: 'linear-gradient(90deg, rgba(255, 255, 255, 0.88) 0%, rgba(232, 243, 255, 0.82) 100%)',
            borderRight: '1px solid rgba(255, 145, 164, 0.3)',
          }}
        >
          <span className="text-2xl" style={{ transform: 'rotate(-90deg)', whiteSpace: 'nowrap', color: 'var(--color-pink-primary)' }}>
            🎭
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      className="h-full flex flex-col rounded-l-xl overflow-hidden"
      style={{
        background: 'linear-gradient(90deg, rgba(255, 255, 255, 0.88) 0%, rgba(232, 243, 255, 0.82) 100%)',
        borderRight: '1px solid rgba(255, 145, 164, 0.3)',
        boxShadow: 'var(--shadow-panel)',
        width: 280,
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b"
        style={{ borderColor: 'rgba(74, 169, 255, 0.2)' }}
      >
        <span className="text-sm font-semibold" style={{ color: 'var(--color-blue-deep)' }}>
          🎭 Live2D
        </span>
        <button
          onClick={onToggleCollapse}
          className="w-6 h-6 rounded-full flex items-center justify-center text-xs opacity-60 hover:opacity-100 transition-opacity"
          style={{ background: 'rgba(74, 169, 255, 0.1)', color: 'var(--color-blue-deep)' }}
          title="收起"
        >
          ‹
        </button>
      </div>

      {/* Canvas / placeholder */}
      <div className="flex-1 flex items-center justify-center relative overflow-hidden">
        {isLoaded ? (
          <canvas id="live2d-canvas" className="w-full h-full" />
        ) : (
          <PlaceholderAvatar />
        )}
      </div>

      {/* Footer hint */}
      <div
        className="px-4 py-2 border-t text-xs text-center"
        style={{ borderColor: 'rgba(74, 169, 255, 0.2)', color: 'var(--color-blue-deep)', opacity: 0.5 }}
      >
        {isLoaded ? '点击角色互动' : '等待模型加载…'}
      </div>
    </div>
  );
}

function PlaceholderAvatar() {
  return (
    <div className="flex flex-col items-center gap-3 animate-spring">
      {/* Animated character silhouette */}
      <div
        className="w-36 h-36 rounded-full flex items-center justify-center relative"
        style={{
          background: 'linear-gradient(135deg, rgba(255, 145, 164, 0.15) 0%, rgba(74, 169, 255, 0.15) 100%)',
          border: '2px solid rgba(255, 145, 164, 0.3)',
        }}
      >
        {/* Glow ring */}
        <div
          className="absolute inset-0 rounded-full animate-pulse"
          style={{
            background: 'rgba(255, 145, 164, 0.08)',
            transform: 'scale(1.1)',
          }}
        />
        {/* Avatar face */}
        <div className="relative flex flex-col items-center">
          {/* Eyes */}
          <div className="flex gap-4 mb-3">
            <div
              className="w-5 h-5 rounded-full animate-bounce"
              style={{ background: 'var(--color-blue-deep)', animationDuration: '2s', animationDelay: '0s' }}
            />
            <div
              className="w-5 h-5 rounded-full animate-bounce"
              style={{ background: 'var(--color-blue-deep)', animationDuration: '2s', animationDelay: '0.3s' }}
            />
          </div>
          {/* Mouth */}
          <div
            className="w-8 h-3 rounded-full animate-pulse"
            style={{ background: 'var(--color-pink-primary)', opacity: 0.6 }}
          />
        </div>
      </div>

      {/* Name tag */}
      <div
        className="px-4 py-1.5 rounded-full text-xs font-medium"
        style={{
          background: 'rgba(255, 145, 164, 0.1)',
          border: '1px solid rgba(255, 145, 164, 0.3)',
          color: 'var(--color-blue-deep)',
        }}
      >
        珞樱 · 待机中
      </div>

      {/* Status dots */}
      <div className="flex gap-1.5">
        {['rgba(74, 169, 255, 0.4)', 'rgba(255, 145, 164, 0.4)', 'rgba(74, 169, 255, 0.2)'].map((color, i) => (
          <div
            key={i}
            className="w-1.5 h-1.5 rounded-full animate-ping"
            style={{ background: color, animationDuration: '1.5s', animationDelay: `${i * 0.5}s` }}
          />
        ))}
      </div>

      <p className="text-xs mt-2" style={{ color: 'var(--color-blue-deep)', opacity: 0.4 }}>
        未配置 Live2D 模型
      </p>
    </div>
  );
}
