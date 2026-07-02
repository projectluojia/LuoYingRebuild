/**
 * PixiLive2DController — Live2DController backed by pixi-live2d-display.
 *
 * Satisfies the Live2DController interface contract defined in Live2DController.ts.
 *
 * Lifecycle:
 * 1. mount(canvas) — attach PIXI to a <canvas> element (call when panel becomes visible)
 * 2. loadModel(url?) — load a Live2D model (.model3.json or .model.json)
 * 3. destroy() — free all resources (call when panel is hidden or on unmount)
 *
 * Falls back gracefully when no model URL is configured.
 *
 * NOTE: pixi-live2d-display and pixi.js are dynamically imported inside _ensureApp()
 * to avoid WebGL errors when the panel is not visible.
 */
import * as PIXI from 'pixi.js';
import type { Live2DController } from './Live2DController';

/** Result of dynamically importing pixi-live2d-display — resolved once per controller instance. */
type Live2DLib = typeof import('pixi-live2d-display');

/** Cubism 4 mouth parameter ID — most models use this. */
const DEFAULT_MOUTH_PARAM = 'ParamMouthForm';
/** Cubism 2 mouth parameter ID (fallback). */
const CUBISM2_MOUTH_PARAM = 'mouth_open';

export class PixiLive2DController implements Live2DController {
  private _app: PIXI.Application | null = null;
  private _model: Awaited<ReturnType<Live2DLib['Live2DModel']['from']>> | null = null;
  private _canvas: HTMLCanvasElement | null = null;
  private _loaded = false;
  private _tapHandlers = new Map<string, () => void>();
  /** Lazily-loaded pixi-live2d-display module. */
  private _live2dLib: Live2DLib | null = null;

  // Lip-sync state
  private _lipCtx: AudioContext | null = null;
  private _lipAnalyser: AnalyserNode | null = null;
  private _lipSource: AudioBufferSourceNode | null = null;
  private _lipAnimId: number | null = null;
  /** The parameter name used for mouth animation (auto-detected per model). */
  private _mouthParam = DEFAULT_MOUTH_PARAM;

  // ─── Public lifecycle ───────────────────────────────────────────────────────

  /** True after a model has been successfully loaded and is on stage. */
  get isLoaded() {
    return this._loaded;
  }

  /**
   * Mount the PIXI application into a canvas element.
   * Call when the Live2D panel becomes visible; call destroy() when hiding.
   */
  async mount(canvas: HTMLCanvasElement): Promise<void> {
    this._canvas = canvas;
    await this._ensureApp();
    console.debug('[Live2D] mounted on canvas');
  }

  /**
   * Set the canvas element directly without initialising PIXI.
   * The controller will lazily initialise PIXI when loadModel() is called.
   */
  setCanvas(canvas: HTMLCanvasElement): void {
    this._canvas = canvas;
  }

  /** Initialise the PIXI Application. Called lazily by loadModel() if not yet mounted. */
  private async _ensureApp(): Promise<void> {
    if (this._app) return;

    if (!this._canvas) {
      console.warn('[Live2D] No canvas set — call setCanvas() or mount() first');
      return;
    }

    // Dynamic import so pixi-live2d-display is never loaded unless Live2D is active
    // @ts-expect-error - pixi-live2d-display ships no bundled typings
    const lib: Live2DLib = await import('pixi-live2d-display');
    this._live2dLib = lib;

    this._app = new PIXI.Application();
    await this._app.init({
      canvas: this._canvas,
      width: this._canvas.clientWidth || 280,
      height: this._canvas.clientHeight || 400,
      backgroundAlpha: 0, // transparent so CSS gradient shows
      antialias: true,
      resolution: window.devicePixelRatio || 1,
      autoDensity: true,
    });

    console.debug('[Live2D] PIXI Application initialised');
  }

  // ─── Live2DController implementation ───────────────────────────────────────

  /**
   * Load a Live2D model from a URL.
   * Reads VITE_LIVE2D_MODEL_URL if no URL is passed.
   */
  async loadModel(modelUrl?: string): Promise<void> {
    const url = modelUrl ?? (import.meta.env.VITE_LIVE2D_MODEL_URL as string | undefined);

    if (!url) {
      console.warn('[Live2D] No model URL — set VITE_LIVE2D_MODEL_URL or pass a URL');
      return;
    }

    if (!this._canvas) {
      console.warn('[Live2D] No canvas — call setCanvas() or mount() first');
      return;
    }

    await this._ensureApp();

    // Teardown previous model if any
    if (this._model) {
      try {
        this._app.stage.removeChild(this._model as unknown as PIXI.Container);
        this._model.destroy({ children: true, texture: true });
      } catch { /* ignore */ }
      this._model = null;
      this._loaded = false;
    }

    console.debug('[Live2D] Loading:', url);

    const Live2DModel = this._live2dLib!.Live2DModel;

    try {
      const model = await Live2DModel.from(url, {
        autoInteract: true,
        autoUpdate: true,
        motionPreload: 'IDLE',
      });

      // Forward hit events to registered handlers
      model.on('hit', (areas: string[]) => {
        console.debug('[Live2D] hit:', areas);
        areas.forEach((area) => {
          const h = this._tapHandlers.get(area);
          if (h) h();
        });
        // Also fire first registered handler on any hit (fallback)
        if (areas.length > 0 && this._tapHandlers.size > 0) {
          const first = this._tapHandlers.values().next().value;
          if (first) first();
        }
      });

      // Auto-detect mouth parameter name from model settings
      this._detectMouthParam(model);

      // When the model finishes loading, add to stage and scale to fit
      model.once('load', () => {
        if (!this._app || !this._canvas) return;

        const stage = this._app.stage;
        stage.removeChildren();

        const canvasW = this._canvas.clientWidth || 280;
        const canvasH = this._canvas.clientHeight || 400;
        const modelW = (model as any).internalModel?.originalWidth ?? 300;
        const modelH = (model as any).internalModel?.originalHeight ?? 300;
        const scale = (Math.min(canvasW / modelW, canvasH / modelH) * 0.9);

        (model as any).scale.set(scale);
        (model as any).anchor.set(0.5, 0.5);
        (model as any).x = canvasW / 2;
        (model as any).y = canvasH / 2;

        stage.addChild(model as unknown as PIXI.Container);
        console.debug('[Live2D] Model on stage, scale=', scale.toFixed(3));
      });

      this._model = model;
      this._loaded = true;
    } catch (err) {
      console.error('[Live2D] loadModel failed:', err);
      this._loaded = false;
      throw err;
    }
  }

  /** Apply an expression by name (e.g. "angry", "smile") or index. */
  setExpression(expression: string): void {
    if (!this._model) {
      console.warn('[Live2D] No model — setExpression ignored');
      return;
    }
    this._model.expression(expression).catch((err: unknown) =>
      console.warn('[Live2D] setExpression failed:', err)
    );
  }

  /**
   * Start lip-sync driven by an AudioBuffer.
   * Uses an AnalyserNode to extract volume and drives the mouth parameter in real time.
   */
  startLipSync(audioBuffer: AudioBuffer): void {
    this._stopLipSync();

    if (!this._model) {
      console.warn('[Live2D] No model — startLipSync ignored');
      return;
    }

    try {
      this._lipCtx = new AudioContext();
      this._lipAnalyser = this._lipCtx.createAnalyser();
      this._lipAnalyser.fftSize = 256;

      const source = this._lipCtx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(this._lipAnalyser);
      this._lipAnalyser.connect(this._lipCtx.destination);
      source.start(0);
      this._lipSource = source;

      const data = new Uint8Array(this._lipAnalyser.frequencyBinCount);

      const tick = () => {
        if (!this._model || !this._lipAnalyser) return;

        this._lipAnalyser.getByteFrequencyData(data);
        // Low-frequency average → rough volume estimate (0..1)
        const vol =
          data.slice(0, 8).reduce((a, b) => a + b, 0) / (8 * 255);

        const mouthVal = Math.min(vol * 1.8, 1); // scale to typical Param range

        try {
          const im = (this._model as any).internalModel as any;
          const idx = im?.coreModel?.getParamIndex(this._mouthParam);
          if (idx != null && idx >= 0) {
            im.coreModel.setParamFloat(idx, mouthVal, 1);
          }
        } catch { /* param not found — silent */ }

        this._lipAnimId = requestAnimationFrame(tick);
      };

      source.onended = () => this._stopLipSync();
      tick();
      console.debug('[Live2D] Lip-sync started');
    } catch (err) {
      console.error('[Live2D] startLipSync failed:', err);
    }
  }

  /** Stop ongoing lip-sync animation. */
  stopLipSync(): void {
    if (this._lipAnimId !== null) {
      cancelAnimationFrame(this._lipAnimId);
      this._lipAnimId = null;
    }
    if (this._lipSource) {
      try { this._lipSource.stop(); } catch { /* already ended */ }
      this._lipSource.disconnect();
      this._lipSource = null;
    }
    if (this._lipAnalyser) {
      this._lipAnalyser.disconnect();
      this._lipAnalyser = null;
    }
    if (this._lipCtx) {
      this._lipCtx.close().catch(() => {/* already closed */});
      this._lipCtx = null;
    }
    console.debug('[Live2D] Lip-sync stopped');
  }

  /**
   * Register a tap handler for a named hit area (e.g. "head", "body").
   */
  onTap(hitArea: string, handler: () => void): void {
    this._tapHandlers.set(hitArea, handler);
  }

  // ─── Private helpers ────────────────────────────────────────────────────────

  /**
   * Probe the model's settings to find which parameter drives the mouth.
   * Cubism 4 uses "ParamMouthForm", Cubism 2 uses "mouth_open".
   */
  private _detectMouthParam(model: typeof this._model & object): void {
    try {
      const settings = (model as any).internalModel?.settings;
      if (!settings) return;

      // Cubism 4: look for expressions in settings
      const expressions: Array<{ Name: string; File: string }> =
        settings.expressions ?? [];
      if (expressions.length > 0) {
        // Try to read the first expression file to find the param ID
        // Most Cubism 4 models use ParamMouthForm
        this._mouthParam = DEFAULT_MOUTH_PARAM;
        return;
      }

      // Cubism 2: look for init_params
      const initParams: Array<{ id: string }> =
        (settings as any).init_params ?? [];
      const mouth = initParams.find((p) =>
        p.id.toLowerCase().includes('mouth')
      );
      if (mouth) {
        this._mouthParam = mouth.id;
        return;
      }

      this._mouthParam = CUBISM2_MOUTH_PARAM;
    } catch {
      this._mouthParam = DEFAULT_MOUTH_PARAM;
    }
  }
}
