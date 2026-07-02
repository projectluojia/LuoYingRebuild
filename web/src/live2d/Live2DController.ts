/**
 * Live2D Controller interface contract.
 * Defines the minimum surface area needed to drive a Live2D model.
 * The actual implementation can be pixi-live2d-display, native Cubism SDK, or any adapter.
 */
export interface Live2DController {
  /** Load a model from a URL (e.g. a .model3.json or .json manifest). */
  loadModel(modelUrl: string): Promise<void>;

  /** Apply an expression by name (e.g. "angry", "smile"). */
  setExpression(expression: string): void;

  /** Start lip-sync from an audio buffer (TTS output). */
  startLipSync(audioBuffer: AudioBuffer): void;

  /** Stop ongoing lip-sync animation. */
  stopLipSync(): void;

  /** Register a tap handler on a named hit area (e.g. "head", "body"). */
  onTap(hitArea: string, handler: () => void): void;

  /** Attach the controller to a canvas element before loading a model. */
  setCanvas(canvas: HTMLCanvasElement): void;

  /**
   * Mount the controller onto a canvas element.
   * Convenience method — may call setCanvas internally.
   * Call when the Live2D panel becomes visible.
   */
  mount(canvas: HTMLCanvasElement): Promise<void>;

  /** Whether a model has been successfully loaded and is on stage. */
  readonly isLoaded: boolean;

  /** Unload the current model and free resources. */
  destroy(): void;
}

export interface Live2DContextValue {
  /** The active controller instance (null when using NullController). */
  controller: Live2DController | null;

  /** Whether a model has been loaded and is on stage. */
  isLoaded: boolean;

  /** Load a model from a URL. */
  loadModel: (url: string) => Promise<void>;

  /** Apply an expression by name. */
  setExpression: (expression: string) => void;

  /** Start lip-sync from an audio buffer. */
  startLipSync: (audioBuffer: AudioBuffer) => void;

  /** Stop ongoing lip-sync animation. */
  stopLipSync: () => void;

  /** Set the canvas element the controller should render into. */
  setCanvas: (canvas: HTMLCanvasElement | null) => void;

  /**
   * Mount and initialise the controller on a canvas.
   * Triggers PIXI init + model load. Safe to call multiple times.
   */
  mount: (canvas: HTMLCanvasElement) => Promise<void>;
}
