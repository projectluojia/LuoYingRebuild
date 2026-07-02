import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { api } from '../api/client';

// We'll use a spy on globalThis.fetch to test the api client.
// In jsdom, globalThis.fetch is available.
describe('api client', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  // --- getVoiceConfig ---

  it('getVoiceConfig returns VoiceConfig on 200', async () => {
    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify({ stt_enabled: true, tts_enabled: false }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const config = await api.getVoiceConfig();
    expect(config).toEqual({ stt_enabled: true, tts_enabled: false });
    expect(fetchSpy).toHaveBeenCalledWith('/api/voice/config');
  });

  it('getVoiceConfig throws on non-ok response', async () => {
    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Service unavailable' }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    await expect(api.getVoiceConfig()).rejects.toThrow('Voice config failed');
  });

  // --- speechToText ---

  it('speechToText POSTs audio blob and returns text', async () => {
    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify({ text: 'hello world' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const blob = new Blob(['fake audio'], { type: 'audio/webm' });
    const text = await api.speechToText(blob);

    expect(text).toBe('hello world');
    const calledWith = fetchSpy.mock.calls[0] as [RequestInfo, RequestInit?];
    expect(calledWith[0]).toContain('/api/voice/stt');
    expect(calledWith[1]?.method).toBe('POST');
    expect((calledWith[1]?.body as Blob).type).toBe('audio/webm');
  });

  it('speechToText throws with detail on non-ok response', async () => {
    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'STT not configured' }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    await expect(api.speechToText(new Blob())).rejects.toThrow('STT not configured');
  });

  // --- textToSpeech ---

  it('textToSpeech POSTs JSON and returns blob on 200', async () => {
    const fakeAudio = new Uint8Array([0x52, 0x49, 0x46, 0x46]); // "RIFF" — fake WAV header
    fetchSpy.mockResolvedValue(
      new Response(fakeAudio, {
        status: 200,
        headers: { 'Content-Type': 'audio/wav' },
      })
    );

    const blob = await api.textToSpeech('hello', 'voice-1');
    expect(blob).toBeInstanceOf(Blob);

    const calledWith = fetchSpy.mock.calls[0] as [RequestInfo, RequestInit?];
    expect(calledWith[0]).toContain('/api/voice/tts');
    expect(calledWith[1]?.method).toBe('POST');
    const body = JSON.parse((calledWith[1]?.body as string) ?? '{}');
    expect(body).toEqual({ text: 'hello', voice_id: 'voice-1' });
  });

  it('textToSpeech throws with detail on non-ok response', async () => {
    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'TTS not configured' }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    await expect(api.textToSpeech('hello')).rejects.toThrow('TTS not configured');
  });

  // --- health ---

  it('health returns parsed JSON', async () => {
    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const result = await api.health();
    expect(result).toEqual({ status: 'ok' });
    expect(fetchSpy).toHaveBeenCalledWith('/api/health');
  });
});
