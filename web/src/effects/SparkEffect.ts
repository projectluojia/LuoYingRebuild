import { useEffect } from 'react';

interface SparkEffectOptions {
  /** Spark color as RGB string, e.g. "255,145,164" */
  color?: string;
  /** Spark scale factor */
  scale?: number;
  /** Spark opacity */
  opacity?: number;
  /** Animation speed multiplier */
  speed?: number;
  /** Maximum trail length */
  maxTrail?: number;
}

/**
 * 鼠标火花特效
 * 参考 LuoYing-Frontend 的 mouse-spark.js
 * 使用 Canvas 实现粒子特效
 */
export function useSparkEffect(options: SparkEffectOptions = {}) {
  const {
    color = '255,145,164', // pink-primary
    scale = 1.5,
    opacity = 1.0,
    speed = 1.0,
    maxTrail = 16,
  } = options;

  useEffect(() => {
    class MouseSpark {
      private canvas: HTMLCanvasElement;
      private ctx: CanvasRenderingContext2D;
      private sparkPool: Spark[] = [];
      private wavePool: Wave[] = [];
      private waves: Wave[] = [];
      private sparks: Spark[] = [];
      private trail: TrailPoint[] = [];
      private isDown = false;
      private lastPos: { x: number; y: number } | null = null;
      private baseFrameMs = 1000 / 60;
      private maxDeltaMs = 100;
      private lastFrameTime = performance.now();
      private animationId: number | null = null;

      constructor() {
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'baSparkCanvas';
        Object.assign(this.canvas.style, {
          position: 'fixed',
          left: '0',
          top: '0',
          width: '100%',
          height: '100%',
          pointerEvents: 'none',
          zIndex: '2147483647',
          background: 'transparent',
        });
        document.body.appendChild(this.canvas);
        this.ctx = this.canvas.getContext('2d')!;
        this.resize();
        window.addEventListener('resize', () => this.resize());
        this.bindEvents();
        this.loop(performance.now());
      }

      private alpha(value: number): number {
        return Math.max(0, Math.min(1, value * opacity));
      }

      private resize() {
        const dpr = window.devicePixelRatio || 1;
        this.canvas.width = window.innerWidth * dpr;
        this.canvas.height = window.innerHeight * dpr;
        this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      }

      private getPos(e: MouseEvent): { x: number; y: number } {
        return { x: e.clientX, y: e.clientY };
      }

      private dist(a: { x: number; y: number }, b: { x: number; y: number }): number {
        return Math.hypot(a.x - b.x, a.y - b.y);
      }

      private bindEvents() {
        window.addEventListener('mousedown', (e) => {
          this.isDown = true;
          this.lastPos = this.getPos(e);
          this.boom(this.lastPos.x, this.lastPos.y);
        });

        window.addEventListener('mousemove', (e) => {
          if (!this.isDown) return;

          const p = this.getPos(e);
          if (!this.lastPos) this.lastPos = p;

          if (this.lastPos && this.dist(p, this.lastPos) > 2) {
            this.trail.push({ x: p.x, y: p.y, life: 1 });
            this.lastPos = p;
            if (this.trail.length > maxTrail) this.trail.shift();

            if (Math.random() < 0.3) {
              const a = Math.random() * Math.PI * 2;
              const speedAdjust = scale / 1.5;
              this.sparks.push({
                x: p.x + Math.cos(a) * 10 * scale,
                y: p.y + Math.sin(a) * 10 * scale,
                vx: Math.cos(a) * 1.3 * speedAdjust,
                vy: Math.sin(a) * 1.3 * speedAdjust,
                rot: Math.random() * Math.PI * 2,
                rs: 0.16,
                s: 9 * scale,
                a: 0.7,
                f: 0.95,
              });
            }
          }
        });

        window.addEventListener('mouseup', () => {
          this.isDown = false;
        });
      }

      private boom(x: number, y: number) {
        let wave: Wave;
        if (this.wavePool.length > 0) {
          wave = this.wavePool.pop()!;
          wave.x = x;
          wave.y = y;
          wave.life = 0;
          wave.max = 18;
          wave.r = 0;
          wave.ring.ang = Math.random() * Math.PI * 2;
          wave.ring.life = 0;
        } else {
          wave = {
            x,
            y,
            life: 0,
            max: 18,
            r: 0,
            ring: {
              ang: Math.random() * Math.PI * 2,
              segs: [
                { off: -0.25 * Math.PI, len: 1.15 * Math.PI },
                { off: 0.0 * Math.PI, len: 1.15 * Math.PI },
                { off: 0.25 * Math.PI, len: 1.15 * Math.PI },
              ],
              life: 0,
              maxLife: 30,
              rs: 0.08,
            },
          };
        }
        this.waves.push(wave);

        const particleCount = 4;
        const speedAdjust = scale / 1.5;
        for (let i = 0; i < particleCount; i++) {
          const a = Math.random() * Math.PI * 2;
          const spd = (4.8 + Math.random() * 2) * speedAdjust;

          let spark: Spark;
          if (this.sparkPool.length > 0) {
            spark = this.sparkPool.pop()!;
            spark.x = x;
            spark.y = y;
            spark.vx = Math.cos(a) * spd;
            spark.vy = Math.sin(a) * spd;
            spark.rot = Math.random() * Math.PI * 2;
            spark.rs = (Math.random() - 0.5) * 0.28;
            spark.s = (4 + Math.random() * 3) * scale;
            spark.a = 1;
            spark.f = 0.9;
          } else {
            spark = {
              x,
              y,
              vx: Math.cos(a) * spd,
              vy: Math.sin(a) * spd,
              rot: Math.random() * Math.PI * 2,
              rs: (Math.random() - 0.5) * 0.28,
              s: (4 + Math.random() * 3) * scale,
              a: 1,
              f: 0.9,
            };
          }
          this.sparks.push(spark);
        }
      }

      private loop(now: number) {
        const deltaMs = Math.min(now - this.lastFrameTime, this.maxDeltaMs);
        this.lastFrameTime = now;
        const frameScale = (deltaMs / this.baseFrameMs) * speed;

        if (this.waves.length > 0 || this.sparks.length > 0 || this.trail.length > 0) {
          this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
          this.ctx.globalCompositeOperation = 'lighter';

          // Draw trail
          for (let i = this.trail.length - 1; i >= 0; i--) {
            this.trail[i].life -= (this.isDown ? 0.085 : 0.18) * frameScale;
            if (this.trail[i].life <= 0) this.trail.splice(i, 1);
          }

          if (this.trail.length > 1) {
            this.ctx.lineWidth = 5.0;
            this.ctx.shadowColor = `rgba(${color}, 0.6)`;
            this.ctx.shadowBlur = 3;

            const lastIdx = this.trail.length - 1;
            for (let i = 0; i < lastIdx; i++) {
              const alphaStart = i / lastIdx;
              const alphaEnd = (i + 1) / lastIdx;
              const a0 = this.trail[i];
              const a1 = this.trail[i + 1];

              const segGrad = this.ctx.createLinearGradient(a0.x, a0.y, a1.x, a1.y);
              segGrad.addColorStop(0, `rgba(${color}, ${alphaStart})`);
              segGrad.addColorStop(1, `rgba(${color}, ${alphaEnd})`);

              this.ctx.beginPath();
              this.ctx.moveTo(a0.x, a0.y);
              this.ctx.lineTo(a1.x, a1.y);
              this.ctx.strokeStyle = segGrad;
              this.ctx.stroke();
            }
            this.ctx.shadowColor = 'transparent';
          }

          // Draw waves
          for (let i = this.waves.length - 1; i >= 0; i--) {
            const w = this.waves[i];
            w.life += frameScale;
            const progress = w.life / w.max;
            const ease = 1 - Math.pow(1 - Math.min(progress, 1), 3);
            w.r = 26 * scale * ease;
            const alpha = Math.max(0, 1 - progress);

            if (alpha > 0) {
              this.ctx.beginPath();
              this.ctx.arc(w.x, w.y, w.r, 0, Math.PI * 2);
              this.ctx.fillStyle = `rgba(${color},${this.alpha(alpha)})`;
              this.ctx.fill();
            }

            const r = w.ring;
            r.life += frameScale;
            const rProg = Math.min(r.life / r.maxLife, 1);
            r.ang -= r.rs * frameScale;
            r.segs.forEach((seg) => {
              const shrink = Math.max(0, 1 - rProg);
              const len = seg.len * shrink;
              const start = r.ang + seg.off;
              this.ctx.beginPath();
              this.ctx.arc(w.x, w.y, w.r + 3 * scale, start, start + len);
              this.ctx.lineWidth = 3.7;
              this.ctx.strokeStyle = `rgba(255,240,245,${this.alpha(1 - rProg)})`;
              this.ctx.stroke();
            });

            if (progress >= 1 && rProg >= 1) {
              this.wavePool.push(this.waves[i]);
              this.waves.splice(i, 1);
            }
          }

          // Draw sparks
          for (let i = this.sparks.length - 1; i >= 0; i--) {
            const s = this.sparks[i];
            s.x += s.vx * frameScale;
            s.y += s.vy * frameScale;
            s.vx *= Math.pow(s.f, frameScale);
            s.vy *= Math.pow(s.f, frameScale);
            s.rot += s.rs * frameScale;
            s.a -= 0.032 * frameScale;
            if (s.a <= 0) {
              this.sparkPool.push(this.sparks[i]);
              this.sparks.splice(i, 1);
              continue;
            }

            this.ctx.save();
            this.ctx.translate(s.x, s.y);
            this.ctx.rotate(s.rot);

            this.ctx.beginPath();
            const r = s.s * 1.6;
            for (let j = 0; j < 5; j++) {
              this.ctx.rotate((Math.PI * 2) / 5);
              this.ctx.moveTo(0, 0);
              this.ctx.bezierCurveTo(r * 0.3, -r * 0.5, r * 0.3, -r * 0.8, r * 0.3, -r);
              this.ctx.lineTo(0, -r * 0.85);
              this.ctx.lineTo(-r * 0.3, -r);
              this.ctx.bezierCurveTo(-r * 0.5, -r * 0.8, -r * 0.5, -r * 0.5, 0, 0);
            }
            this.ctx.fillStyle = `rgba(255, 183, 197, ${this.alpha(s.a)})`;
            this.ctx.fill();

            this.ctx.beginPath();
            this.ctx.arc(0, 0, r * 0.2, 0, Math.PI * 2);
            this.ctx.fillStyle = `rgba(255, 105, 180, ${this.alpha(s.a)})`;
            this.ctx.fill();

            this.ctx.restore();
          }
          this.ctx.globalCompositeOperation = 'source-over';
        }
        this.animationId = requestAnimationFrame((nextNow) => this.loop(nextNow));
      }

      public destroy() {
        if (this.animationId !== null) {
          cancelAnimationFrame(this.animationId);
        }
        this.canvas.remove();
      }
    }

    interface Spark {
      x: number;
      y: number;
      vx: number;
      vy: number;
      rot: number;
      rs: number;
      s: number;
      a: number;
      f: number;
    }

    interface Wave {
      x: number;
      y: number;
      life: number;
      max: number;
      r: number;
      ring: {
        ang: number;
        segs: { off: number; len: number }[];
        life: number;
        maxLife: number;
        rs: number;
      };
    }

    interface TrailPoint {
      x: number;
      y: number;
      life: number;
    }

    const effect = new MouseSpark();

    return () => {
      effect.destroy();
    };
  }, [color, scale, opacity, speed, maxTrail]);
}
