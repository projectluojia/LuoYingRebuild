import { useCallback } from 'react';
import { useVoice } from '../hooks/useVoice';

interface VoiceButtonProps {
  onTranscript: (text: string) => void;
  className?: string;
}

export function VoiceButton({ onTranscript, className = '' }: VoiceButtonProps) {
  const { sttEnabled, recording, transcribing, startRecording, stopRecording } = useVoice();

  const handleClick = useCallback(async () => {
    if (recording) {
      try {
        const text = await stopRecording();
        if (text.trim()) {
          onTranscript(text);
        }
      } catch {
        // STT failed — silently ignore
      }
    } else {
      try {
        await startRecording();
      } catch {
        // Microphone access denied — silently ignore
      }
    }
  }, [recording, startRecording, stopRecording, onTranscript]);

  if (!sttEnabled) {
    return null;
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={transcribing}
      className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all hover-lift hover-scale ${className} ${
        recording ? 'animate-pulse' : ''
      }`}
      style={
        recording
          ? {
              background: 'linear-gradient(135deg, rgba(229, 62, 62, 0.9), rgba(245, 101, 101, 0.85))',
              color: 'white',
              boxShadow: 'var(--shadow-glow-pink)',
            }
          : {
              background: 'rgba(255, 145, 164, 0.15)',
              border: '1px solid rgba(255, 145, 164, 0.3)',
              color: 'var(--color-pink-primary)',
            }
      }
      aria-label={recording ? 'Stop recording' : 'Start voice input'}
    >
      {recording ? (
        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
          <rect x="5" y="5" width="10" height="10" rx="2" />
        </svg>
      ) : (
        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
          <path d="M10 2a1 1 0 011 1v5a3 3 0 01-3 3H7a3 3 0 01-3-3V3a1 1 0 011-1h3zm4 9a5 5 0 01-5 5H6a5 5 0 01-5-5h1a4 4 0 008 0h1a4 4 0 000-8z" />
        </svg>
      )}
    </button>
  );
}
