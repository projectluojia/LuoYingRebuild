import { createContext, useContext, useState, useCallback } from 'react';
import type { Live2DContextValue, Live2DController } from './Live2DController';

/** No-op controller used as the default when no model is loaded. */
const NullController: Live2DController = {
  async loadModel() {
    console.warn('[Live2D] No model loaded — call setController() first');
  },
  setExpression() {},
  startLipSync() {},
  stopLipSync() {},
  onTap() {},
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
  const [controller] = useState<Live2DController | null>(
    providedController ?? NullController
  );
  const [isLoaded, setIsLoaded] = useState(false);

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
      value={{ controller, isLoaded, loadModel, setExpression, startLipSync, stopLipSync }}
    >
      {children}
    </Live2DContext.Provider>
  );
}
