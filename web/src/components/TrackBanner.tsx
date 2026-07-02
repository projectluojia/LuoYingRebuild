interface TrackBannerProps {
  text: string | null;
  isStreaming: boolean;
}

export function TrackBanner({ text, isStreaming }: TrackBannerProps) {
  if (!isStreaming && !text) return null;

  return (
    <div
      className="absolute top-4 left-1/2 -translate-x-1/2 z-50 px-5 py-2 rounded-full text-sm font-medium animate-spring"
      style={{
        background: 'rgba(255, 255, 255, 0.9)',
        border: '1px solid rgba(255, 145, 164, 0.4)',
        boxShadow: 'var(--shadow-sm)',
        color: text ? 'var(--color-blue-deep)' : 'transparent',
        minWidth: 200,
        textAlign: 'center',
      }}
    >
      {text ? (
        <span className="flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full animate-pulse" style={{ background: 'var(--color-pink-primary)' }} />
          {text}
        </span>
      ) : (
        <span className="flex items-center justify-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full animate-pulse" style={{ background: 'var(--color-blue-light)' }} />
          <span style={{ color: 'var(--color-blue-deep)' }}>正在思考...</span>
        </span>
      )}
    </div>
  );
}