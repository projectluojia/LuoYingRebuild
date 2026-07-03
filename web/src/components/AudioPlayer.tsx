import { useVoice } from '../hooks/useVoice';

interface AudioPlayerProps {
  text: string;
  voiceId?: string;
  className?: string;
}

export function AudioPlayer({ text, voiceId, className = '' }: AudioPlayerProps) {
  const { ttsEnabled, speaking, speak, stopSpeaking } = useVoice();

  if (!ttsEnabled) {
    return null;
  }

  return (
    <button
      type="button"
      onClick={speaking ? stopSpeaking : () => speak(text, voiceId)}
      className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all hover-lift hover-scale ${className} ${
        speaking ? 'animate-pulse' : ''
      }`}
      style={
        speaking
          ? {
              background: 'linear-gradient(135deg, rgba(255, 145, 164, 0.25), rgba(74, 169, 255, 0.25))',
              color: 'var(--color-pink-primary)',
              boxShadow: 'var(--shadow-glow-pink)',
            }
          : {
              background: 'rgba(74, 169, 255, 0.12)',
              border: '1px solid rgba(74, 169, 255, 0.25)',
              color: 'var(--color-blue-light)',
            }
      }
      aria-label={speaking ? 'Stop speaking' : 'Play voice'}
    >
      {speaking ? (
        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
          <path d="M5 4h3v12H5V4zm7 0h3v12h-3V4z" />
        </svg>
      ) : (
        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
          <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
        </svg>
      )}
    </button>
  );
}
