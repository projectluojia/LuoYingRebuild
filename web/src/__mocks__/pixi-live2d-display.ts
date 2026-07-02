/**
 * Test mocks for pixi-live2d-display and pixi.js.
 * These stub out the heavy WebGL dependencies so tests run in jsdom.
 */
import { vi } from 'vitest';

// Stub window.Live2D so pixi-live2d-display doesn't throw on import
if (typeof window !== 'undefined') {
  (window as any).Live2D = {};
}

vi.mock('pixi-live2d-display', () => ({
  Live2DModel: {
    from: vi.fn().mockResolvedValue({
      on: vi.fn(),
      once: vi.fn(),
      expression: vi.fn().mockResolvedValue(undefined),
      destroy: vi.fn(),
    }),
  },
}));

vi.mock('pixi.js', () => ({
  Application: vi.fn().mockImplementation(() => ({
    init: vi.fn().mockResolvedValue(undefined),
    stage: { removeChildren: vi.fn(), addChild: vi.fn() },
    destroy: vi.fn(),
  })),
  Container: class MockContainer {},
}));

// Suppress PIXI console noise during tests
vi.mock('@pixi/react', () => ({}));

vi.mock('@pixi/react', () => ({
  Application: vi.fn(),
  extend: vi.fn(),
}));
