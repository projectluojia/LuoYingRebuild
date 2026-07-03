import { useEffect, useRef } from 'react';

interface ParallaxEffectOptions {
  /** Maximum rotation around Y axis in degrees */
  maxRotateY?: number;
  /** Maximum rotation around X axis in degrees */
  maxRotateX?: number;
  /** CSS transform perspective value */
  perspective?: number;
  /** Enable on mouse leave reset */
  resetOnLeave?: boolean;
}

/**
 * 3D视差效果Hook
 * 参考 LuoYing-Frontend 的 ui-parallax.js
 */
export function useParallaxEffect<T extends HTMLElement>(
  options: ParallaxEffectOptions = {}
) {
  const {
    maxRotateY = 4,
    maxRotateX = 2,
    resetOnLeave = true,
  } = options;

  const ref = useRef<T>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const handleMouseMove = (event: MouseEvent) => {
      const { clientX, clientY } = event;
      const { innerWidth, innerHeight } = window;

      const offsetX = (clientX / innerWidth - 0.5) * 2;
      const offsetY = (clientY / innerHeight - 0.5) * 2;

      const rotateX = -(offsetY * maxRotateX);
      const rotateY = offsetX * maxRotateY;

      el.style.transform = `rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
    };

    const handleMouseLeave = () => {
      if (resetOnLeave) {
        el.style.transform = 'rotateX(0deg) rotateY(0deg)';
      }
    };

    window.addEventListener('mousemove', handleMouseMove);
    if (resetOnLeave) {
      document.addEventListener('mouseleave', handleMouseLeave);
    }

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      if (resetOnLeave) {
        document.removeEventListener('mouseleave', handleMouseLeave);
      }
    };
  }, [maxRotateX, maxRotateY, resetOnLeave]);

  return ref;
}
