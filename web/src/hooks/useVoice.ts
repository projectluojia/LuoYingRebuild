import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../api/client';

interface VoiceState {
  available: boolean;
  sttEnabled: boolean;
  ttsEnabled: boolean;
  recording: boolean;
  transcribing: boolean;
  speaking: boolean;
}

export function useVoice() {
  const [state, setState] = useState<VoiceState>({
    available: false,
    sttEnabled: false,
    ttsEnabled: false,
    recording: false,
    transcribing: false,
    speaking: false,
  });

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    api.getVoiceConfig().then(config => {
      setState(s => ({
        ...s,
        available: config.stt_enabled || config.tts_enabled,
        sttEnabled: config.stt_enabled,
        ttsEnabled: config.tts_enabled,
      }));
    }).catch(() => {
      // Voice service unavailable — remain disabled
    });
  }, []);

  const startRecording = useCallback(async (): Promise<void> => {
    if (!state.sttEnabled) return;

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
    mediaRecorderRef.current = mediaRecorder;
    audioChunksRef.current = [];

    mediaRecorder.ondataavailable = e => {
      if (e.data.size > 0) {
        audioChunksRef.current.push(e.data);
      }
    };

    mediaRecorder.start(100);
    setState(s => ({ ...s, recording: true }));
  }, [state.sttEnabled]);

  const stopRecording = useCallback(async (): Promise<string> => {
    return new Promise((resolve, reject) => {
      const mediaRecorder = mediaRecorderRef.current;
      if (!mediaRecorder) {
        reject(new Error('No active recording'));
        return;
      }

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });

        // Stop all tracks to release microphone
        mediaRecorder.stream.getTracks().forEach(track => track.stop());
        mediaRecorderRef.current = null;

        setState(s => ({ ...s, recording: false, transcribing: true }));

        try {
          const text = await api.speechToText(audioBlob);
          setState(s => ({ ...s, transcribing: false }));
          resolve(text);
        } catch (err) {
          setState(s => ({ ...s, transcribing: false }));
          reject(err);
        }
      };

      mediaRecorder.stop();
    });
  }, []);

  const speak = useCallback(async (text: string, voiceId?: string): Promise<void> => {
    if (!state.ttsEnabled) return;

    setState(s => ({ ...s, speaking: true }));

    try {
      const blob = await api.textToSpeech(text, voiceId);
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;

      audio.onended = () => {
        URL.revokeObjectURL(url);
        setState(s => ({ ...s, speaking: false }));
      };

      audio.onerror = () => {
        URL.revokeObjectURL(url);
        setState(s => ({ ...s, speaking: false }));
      };

      await audio.play();
    } catch (err) {
      setState(s => ({ ...s, speaking: false }));
      throw err;
    }
  }, [state.ttsEnabled]);

  const stopSpeaking = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setState(s => ({ ...s, speaking: false }));
  }, []);

  return {
    ...state,
    startRecording,
    stopRecording,
    speak,
    stopSpeaking,
  };
}