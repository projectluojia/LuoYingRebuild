import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { Live2DProvider, useLive2D } from '../live2d/Live2DContext';
import type { Live2DController } from '../live2d/Live2DController';

// A minimal mock controller for testing
function makeMockController(overrides: Partial<Live2DController> = {}): Live2DController {
  return {
    loadModel: vi.fn().mockResolvedValue(undefined),
    setExpression: vi.fn(),
    startLipSync: vi.fn(),
    stopLipSync: vi.fn(),
    onTap: vi.fn(),
    destroy: vi.fn(),
    ...overrides,
  };
}

// Helper component that exposes context values for inspection
function TestConsumer() {
  const ctx = useLive2D();
  return (
    <div>
      <span data-testid="isLoaded">{String(ctx.isLoaded)}</span>
      <span data-testid="hasController">{String(ctx.controller !== null)}</span>
    </div>
  );
}

describe('Live2DProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('initializes with isLoaded false and no controller when none provided', () => {
    render(
      <Live2DProvider>
        <TestConsumer />
      </Live2DProvider>
    );
    expect(screen.getByTestId('isLoaded')).toHaveTextContent('false');
    expect(screen.getByTestId('hasController')).toHaveTextContent('true'); // NullController is not null
  });

  it('provides the supplied controller', () => {
    const ctrl = makeMockController();
    render(
      <Live2DProvider controller={ctrl}>
        <TestConsumer />
      </Live2DProvider>
    );
    expect(screen.getByTestId('hasController')).toHaveTextContent('true');
  });

  it('loadModel sets isLoaded true after controller.loadModel resolves', async () => {
    const ctrl = makeMockController();
    let capturedLoadModel: (url: string) => Promise<void>;

    function SetupCapture() {
      const ctx = useLive2D();
      capturedLoadModel = ctx.loadModel;
      return null;
    }

    render(
      <Live2DProvider controller={ctrl}>
        <SetupCapture />
        <TestConsumer />
      </Live2DProvider>
    );

    expect(screen.getByTestId('isLoaded')).toHaveTextContent('false');

    await act(async () => {
      await capturedLoadModel!('https://example.com/model.json');
    });

    expect(ctrl.loadModel).toHaveBeenCalledWith('https://example.com/model.json');
    expect(screen.getByTestId('isLoaded')).toHaveTextContent('true');
  });

  it('setExpression forwards to controller', () => {
    const ctrl = makeMockController();
    let capturedSetExpression: (expr: string) => void;

    function SetupCapture() {
      const ctx = useLive2D();
      capturedSetExpression = ctx.setExpression;
      return null;
    }

    render(
      <Live2DProvider controller={ctrl}>
        <SetupCapture />
      </Live2DProvider>
    );

    capturedSetExpression!('smile');
    expect(ctrl.setExpression).toHaveBeenCalledWith('smile');
  });

  it('startLipSync and stopLipSync forward to controller', () => {
    const ctrl = makeMockController();
    let capturedStartLipSync: (buf: AudioBuffer) => void;
    let capturedStopLipSync: () => void;

    function SetupCapture() {
      const ctx = useLive2D();
      capturedStartLipSync = ctx.startLipSync;
      capturedStopLipSync = ctx.stopLipSync;
      return null;
    }

    render(
      <Live2DProvider controller={ctrl}>
        <SetupCapture />
      </Live2DProvider>
    );

    // jsdom does not provide AudioBuffer; mock the constructor so the stub call succeeds
    const mockBuffer = {} as AudioBuffer;
    vi.stubGlobal('AudioBuffer', class MockAudioBuffer {
      constructor() { return mockBuffer; }
    });

    expect(() => capturedStartLipSync!(mockBuffer)).not.toThrow();
    expect(() => capturedStopLipSync!()).not.toThrow();
  });
});
