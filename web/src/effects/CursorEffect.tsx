import { useEffect } from 'react';

/**
 * 自定义光标Hook
 * 参考 LuoYing-Frontend 的粉色钻石头光标
 */
export function useCursorEffect() {
  useEffect(() => {
    // 创建自定义光标 SVG data URL
    const cursorSvg = `data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32' viewBox='0 0 32 32'><polygon points='4,4 10,26 14,18 24,18' fill='%23ff91a4' stroke='white' stroke-width='1.5' stroke-linejoin='round'/></svg>`;
    const cursorUrl = `url('${cursorSvg}') 4 4, auto`;
    const pointerUrl = `url('${cursorSvg}') 4 4, pointer`;

    // 应用光标样式
    const updateCursor = () => {
      document.documentElement.style.setProperty('--cursor-default', cursorUrl);
      document.documentElement.style.setProperty('--cursor-pointer', pointerUrl);
    };

    updateCursor();

    // 动态添加光标样式
    const styleId = 'custom-cursor-styles';
    let styleEl = document.getElementById(styleId);

    if (!styleEl) {
      styleEl = document.createElement('style');
      styleEl.id = styleId;
      document.head.appendChild(styleEl);
    }

    styleEl.textContent = `
      /* 默认光标 */
      html, body {
        cursor: var(--cursor-default, ${cursorUrl}) !important;
      }

      /* 可点击元素光标 */
      a, button, input, select, textarea,
      [role="button"], label, .btn, .panel, .btn-nav,
      .currency-item, .terminal-module, .nav-btn,
      [onClick], [data-clickable], .clickable {
        cursor: var(--cursor-pointer, ${pointerUrl}) !important;
      }

      /* 输入框光标保持默认 */
      input[type="text"], input[type="email"], input[type="password"],
      input[type="search"], textarea {
        cursor: text !important;
      }
    `;

    return () => {
      styleEl?.remove();
    };
  }, []);
}
