/**
 * Live2D Controller backed by pixi-live2d-display.
 * Implements the Live2DController interface contract.
 */
import type { Live2DController } from './Live2DController';
import * as PIXI from 'pixi.js';
// @ts-expect-error - pixi-live2d-display ships no bundled typings
import { Live2D } from 'pixi-live2d-display';

export class PixiLive2DController implements Live2DController {
  private model: Live2D.Model | null = null;
  private app: PIXI.Application | null = null;
  private canvas: HTMLCanvasElement | null = null;

  async loadModel(modelUrl: string): Promise<void> {
    if (!this.canvas) {
      throw new Error('Canvas not set before loading model');
    }

    // Initialize PIXI application if needed
    if (!this.app) {
      this.app = new PIXI.Application();
      await this.app.init({
        canvas: this.canvas,
        width: this.canvas.clientWidth || 280,
        height: this.canvas.clientHeight || 400,
        backgroundColor: 0x000000,
        backgroundAlpha: 0,
        antialias: true,
        resolution: window.devicePixelRatio || 1,
        autoDensity: true,
      });
    }

    // Clean up existing model
    if (this.model) {
      this.app.stage.removeChild(this.model as unknown as PIXI.Container);
      (this.model as unknown as { destroy: () => void }).destroy();
      this.model = null;
    }

    // Load new model
    this.model = await Live2D.Live2DModel.from(modelUrl, {
      autoInteract: true,
    });

    // Scale model to fit canvas
    const scaleX = (this.canvas.clientWidth || 280) / this.model.width;
    const scaleY = (this.canvas.clientHeight || 400) / this.model.height;
    this.model.scale.set(Math.min(scaleX, scaleY));

    this.app.stage.addChild(this.model as unknown as PIXI.Container);

    // Enable tap interaction
    this.model.on('hit', (hitArea: string) => {
      console.log(`[Live2D] Hit: ${hitArea}`);
    });
  }

  setExpression(expression: string): void {
    if (!this.model) return;
    // pixi-live2d-display uses motions and expressions differently
    // Expression names match what's in the model's .model3.json
    try {
      (this.model as unknown as { internalModel: { model: { setExpression: (expr: string) => void } } })
        .internalModel.model.setExpression(expression);
    } catch (err) {
      console.warn(`[Live2D] Failed to set expression "${expression}":`, err);
    }
  }

  startLipSync(audioBuffer: AudioBuffer): void {
    if (!this.model) return;
    // Basic lip-sync: drive mouth open/close from audio amplitude
    // A real implementation would use an audio analyzer to drive
    // the mouth's Y scale in real time. For now this is a placeholder.
    console.log('[Live2D] Lip-sync requested (placeholder)');
  }

  stopLipSync(): void {
    if (!this.model) return;
    console.log('[Live2D] Lip-sync stopped');
  }

  onTap(hitArea: string, handler: () => void): void {
    if (!this.model) return;
    this.model.on('hit', (area: string) => {
      if (area === hitArea) {
        handler();
      }
    });
  }

  setCanvas(canvas: HTMLCanvasElement): void {
    this.canvas = canvas;
  }

  destroy(): void {
    if (this.model) {
      this.app?.stage.removeChild(this.model as unknown as PIXI.Container);
      (this.model as unknown as { destroy: () => void }).destroy();
      this.model = null;
    }
    if (this.app) {
      this.app.destroy(true, { children: true, texture: true });
      this.app = null;
    }
    this.canvas = null;
  }
}
