import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { VoiceButton } from '../components/VoiceButton';
import * as useVoiceModule from '../hooks/useVoice';

// Spy on the useVoice hook
vi.mock('../hooks/useVoice', () => ({
  useVoice: vi.fn(),
}));

const useVoice = useVoiceModule.useVoice as ReturnType<typeof vi.fn>;

describe('VoiceButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when STT is disabled', () => {
    useVoice.mockReturnValue({
      sttEnabled: false,
      recording: false,
      transcribing: false,
      startRecording: vi.fn(),
      stopRecording: vi.fn(),
    });

    const { container } = render(<VoiceButton onTranscript={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders a microphone button when STT is enabled', () => {
    useVoice.mockReturnValue({
      sttEnabled: true,
      recording: false,
      transcribing: false,
      startRecording: vi.fn(),
      stopRecording: vi.fn(),
    });

    render(<VoiceButton onTranscript={vi.fn()} />);
    expect(screen.getByRole('button')).toBeInTheDocument();
    expect(screen.getByRole('button')).toHaveAttribute('aria-label', 'Start voice input');
  });

  it('shows stop icon when recording', () => {
    useVoice.mockReturnValue({
      sttEnabled: true,
      recording: true,
      transcribing: false,
      startRecording: vi.fn(),
      stopRecording: vi.fn(),
    });

    render(<VoiceButton onTranscript={vi.fn()} />);
    expect(screen.getByRole('button')).toHaveAttribute('aria-label', 'Stop recording');
  });

  it('disables button while transcribing', () => {
    useVoice.mockReturnValue({
      sttEnabled: true,
      recording: false,
      transcribing: true,
      startRecording: vi.fn(),
      stopRecording: vi.fn(),
    });

    render(<VoiceButton onTranscript={vi.fn()} />);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('calls startRecording on click when not recording', async () => {
    const startRecording = vi.fn();
    useVoice.mockReturnValue({
      sttEnabled: true,
      recording: false,
      transcribing: false,
      startRecording,
      stopRecording: vi.fn(),
    });

    render(<VoiceButton onTranscript={vi.fn()} />);
    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(startRecording).toHaveBeenCalledOnce();
    });
  });

  it('calls stopRecording and onTranscript on click when recording', async () => {
    const stopRecording = vi.fn().mockResolvedValue('hello world');
    const onTranscript = vi.fn();
    useVoice.mockReturnValue({
      sttEnabled: true,
      recording: true,
      transcribing: false,
      startRecording: vi.fn(),
      stopRecording,
    });

    render(<VoiceButton onTranscript={onTranscript} />);
    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(stopRecording).toHaveBeenCalledOnce();
    });
    await waitFor(() => {
      expect(onTranscript).toHaveBeenCalledWith('hello world');
    });
  });

  it('ignores microphone errors silently', async () => {
    const startRecording = vi.fn().mockRejectedValue(new Error('mic denied'));
    useVoice.mockReturnValue({
      sttEnabled: true,
      recording: false,
      transcribing: false,
      startRecording,
      stopRecording: vi.fn(),
    });

    render(<VoiceButton onTranscript={vi.fn()} />);
    // Should not throw
    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(startRecording).toHaveBeenCalled();
    });
    // No error surface — just silently handled
  });

  it('does not call onTranscript for empty transcription', async () => {
    const stopRecording = vi.fn().mockResolvedValue('   ');
    const onTranscript = vi.fn();
    useVoice.mockReturnValue({
      sttEnabled: true,
      recording: true,
      transcribing: false,
      startRecording: vi.fn(),
      stopRecording,
    });

    render(<VoiceButton onTranscript={onTranscript} />);
    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(stopRecording).toHaveBeenCalledOnce();
    });
    // onTranscript should NOT be called for whitespace-only result
    await waitFor(() => {
      expect(onTranscript).not.toHaveBeenCalled();
    });
  });
});
