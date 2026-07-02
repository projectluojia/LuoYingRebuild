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

  /** Unload the current model and free resources. */
  destroy(): void;
}

export interface Live2DContextValue {
  controller: Live2DController | null;
  isLoaded: boolean;
  loadModel: (url: string) => Promise<void>;
  setExpression: (expression: string) => void;
  startLipSync: (audioBuffer: AudioBuffer) => void;
  stopLipSync: () => void;
}
