import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AudioPlayer } from '../components/AudioPlayer';
import * as useVoiceModule from '../hooks/useVoice';

vi.mock('../hooks/useVoice', () => ({
  useVoice: vi.fn(),
}));

const useVoice = useVoiceModule.useVoice as ReturnType<typeof vi.fn>;

describe('AudioPlayer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when TTS is disabled', () => {
    useVoice.mockReturnValue({
      ttsEnabled: false,
      speaking: false,
      speak: vi.fn(),
      stopSpeaking: vi.fn(),
    });

    const { container } = render(<AudioPlayer text="hello" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders a play button when TTS is enabled', () => {
    useVoice.mockReturnValue({
      ttsEnabled: true,
      speaking: false,
      speak: vi.fn(),
      stopSpeaking: vi.fn(),
    });

    render(<AudioPlayer text="hello" />);
    const btn = screen.getByRole('button');
    expect(btn).toBeInTheDocument();
    expect(btn).toHaveAttribute('aria-label', 'Play voice');
  });

  it('calls speak on click when not speaking', async () => {
    const speak = vi.fn().mockResolvedValue(undefined);
    useVoice.mockReturnValue({
      ttsEnabled: true,
      speaking: false,
      speak,
      stopSpeaking: vi.fn(),
    });

    render(<AudioPlayer text="hello world" voiceId="voice-1" />);
    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(speak).toHaveBeenCalledOnce();
    });
    expect(speak).toHaveBeenCalledWith('hello world', 'voice-1');
  });

  it('calls stopSpeaking on click when speaking', async () => {
    const stopSpeaking = vi.fn();
    useVoice.mockReturnValue({
      ttsEnabled: true,
      speaking: true,
      speak: vi.fn(),
      stopSpeaking,
    });

    render(<AudioPlayer text="hello" />);
    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(stopSpeaking).toHaveBeenCalledOnce();
    });
  });

  it('shows stop icon and pulse class when speaking', () => {
    useVoice.mockReturnValue({
      ttsEnabled: true,
      speaking: true,
      speak: vi.fn(),
      stopSpeaking: vi.fn(),
    });

    render(<AudioPlayer text="hello" />);
    const btn = screen.getByRole('button');
    expect(btn).toHaveAttribute('aria-label', 'Stop speaking');
    expect(btn.className).toMatch(/animate-pulse/);
  });
});
