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
      className={`p-2 rounded-full transition-colors ${className} ${
        speaking
          ? 'bg-blue-100 hover:bg-blue-200 text-blue-500 animate-pulse'
          : 'bg-blue-50 hover:bg-blue-100 text-blue-400'
      }`}
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