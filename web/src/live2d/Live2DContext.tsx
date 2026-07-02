import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import type { Live2DController, Live2DContextValue } from './Live2DController';
import { PixiLive2DController } from './PixiLive2DController';

/** No-op controller used as the default when no model is loaded. */
const NullController: Live2DController = {
  async loadModel() {
    console.warn('[Live2D] No model loaded — call setController() first');
  },
  setExpression() {},
  startLipSync() {},
  stopLipSync() {},
  onTap() {},
  setCanvas() {},
  destroy() {},
};

const Live2DContext = createContext<Live2DContextValue>({
  controller: null,
  isLoaded: false,
  loadModel: async () => {},
  setExpression: () => {},
  startLipSync: () => {},
  stopLipSync: () => {},
});

export function useLive2D(): Live2DContextValue {
  return useContext(Live2DContext);
}

export interface Live2DProviderProps {
  children: React.ReactNode;
  /** Provide your own controller (e.g. from pixi-live2d-display). */
  controller?: Live2DController | null;
}

export function Live2DProvider({ children, controller: providedController }: Live2DProviderProps) {
  const [isLoaded, setIsLoaded] = useState(false);

  // Create the Pixi controller once, or use provided controller / NullController
  const [controller] = useState<Live2DController | null>(() => {
    if (providedController !== undefined) return providedController;
    if (import.meta.env.VITE_ENABLE_LIVE2D !== 'true') return NullController;
    return new PixiLive2DController();
  });

  // Expose setCanvas so the panel can attach the canvas element
  const setCanvas = useCallback((canvas: HTMLCanvasElement | null) => {
    if (canvas && controller instanceof PixiLive2DController) {
      controller.setCanvas(canvas);
    }
  }, [controller]);

  // Auto-load model from env var when Pixi controller is active
  useEffect(() => {
    const modelUrl = import.meta.env.VITE_LIVE2D_MODEL_URL as string | undefined;
    if (modelUrl && controller && !(controller === NullController)) {
      controller.loadModel(modelUrl).then(() => setIsLoaded(true)).catch(console.error);
    }
  }, [controller]);

  const loadModel = useCallback(async (url: string) => {
    if (!controller) return;
    await controller.loadModel(url);
    setIsLoaded(true);
  }, [controller]);

  const setExpression = useCallback((expression: string) => {
    controller?.setExpression(expression);
  }, [controller]);

  const startLipSync = useCallback((audioBuffer: AudioBuffer) => {
    controller?.startLipSync(audioBuffer);
  }, [controller]);

  const stopLipSync = useCallback(() => {
    controller?.stopLipSync();
  }, [controller]);

  return (
    <Live2DContext.Provider
      value={{ controller, isLoaded, loadModel, setExpression, startLipSync, stopLipSync, setCanvas }}
    >
      {children}
    </Live2DContext.Provider>
  );
}
