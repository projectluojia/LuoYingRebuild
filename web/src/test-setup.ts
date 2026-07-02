/// <reference types="vitest/globals" />
import '@testing-library/jest-dom';

/**
 * Set up DOM globals needed by pixi-live2d-display before any module loads.
 * The factory function runs synchronously before module resolution.
 */
if (typeof window !== 'undefined') {
  // pixi-live2d-display checks window.Live2D in a top-level factory — set it before import
  (window as unknown as Record<string, unknown>).Live2D = {};
}
