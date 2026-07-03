/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive) / <alpha-value>)",
          foreground: "hsl(var(--destructive-foreground) / <alpha-value>)",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        sidebar: {
          DEFAULT: "hsl(var(--sidebar-background))",
          foreground: "hsl(var(--sidebar-foreground))",
          primary: "hsl(var(--sidebar-primary))",
          "primary-foreground": "hsl(var(--sidebar-primary-foreground))",
          accent: "hsl(var(--sidebar-accent))",
          "accent-foreground": "hsl(var(--sidebar-accent-foreground))",
          border: "hsl(var(--sidebar-border))",
          ring: "hsl(var(--sidebar-ring))",
        },
        // Custom design tokens — 机能风 (Mechano style)
        'pink-primary': 'var(--color-pink-primary)',
        'pink-light': 'var(--color-pink-light)',
        'pink-dark': 'var(--color-pink-dark)',
        'blue-light': 'var(--color-blue-light)',
        'blue-lighter': 'var(--color-blue-lighter)',
        'blue-deep': 'var(--color-blue-deep)',
        'bg-pink': 'var(--color-bg-pink)',
        'bg-blue': 'var(--color-bg-blue)',
        'accent-rose': '#E8A0BF',
        'accent-rose-light': '#FADADD',
        'accent-blue': '#4A90D9',
        'accent-blue-glow': '#6BB3FF',
        'text-primary': '#1A1A2E',
        'text-secondary': '#6B6B7B',
        'text-muted': '#9A9AA8',
        'text-inverse': '#FFFFFF',
        'text-rose': '#C97896',
        'border-subtle': 'rgba(26, 26, 46, 0.08)',
        'border-focus': '#4A90D9',
      },
      fontFamily: {
        display: ['"Noto Serif SC"', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'Fira Code', 'monospace'],
      },
      borderRadius: {
        xl: "calc(var(--radius) + 4px)",
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        xs: "calc(var(--radius) - 6px)",
      },
      boxShadow: {
        xs: "0 1px 2px 0 rgb(0 0 0 / 0.05)",
        'soft': '0 4px 24px rgba(26, 26, 46, 0.06)',
        'glow-rose': '0 0 20px rgba(232, 160, 191, 0.3)',
        'glow-pink': 'var(--shadow-glow-pink)',
        'glow-blue': 'var(--shadow-glow-blue)',
        'panel': 'var(--shadow-panel)',
        'card': '0 4px 24px rgba(26, 26, 46, 0.06)',
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "caret-blink": {
          "0%,70%,100%": { opacity: "1" },
          "20%,50%": { opacity: "0" },
        },
        "float": {
          "0%, 100%": { transform: "translateY(0) rotate(0deg)" },
          "50%": { transform: "translateY(-8px) rotate(3deg)" },
        },
        "float-slow": {
          "0%": { transform: "translateY(0) translateX(0) rotate(0deg)", opacity: "0.3" },
          "25%": { transform: "translateY(-20px) translateX(10px) rotate(15deg)", opacity: "0.6" },
          "50%": { transform: "translateY(-40px) translateX(-5px) rotate(30deg)", opacity: "0.5" },
          "75%": { transform: "translateY(-60px) translateX(15px) rotate(45deg)", opacity: "0.4" },
          "100%": { transform: "translateY(-80px) translateX(0) rotate(60deg)", opacity: "0.3" },
        },
        "bounce-down": {
          "0%, 100%": { transform: "translateY(0)", opacity: "0.8" },
          "50%": { transform: "translateY(8px)", opacity: "0.4" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "0.8" },
        },
        "drift": {
          "0%, 100%": { transform: "translate(0, 0)" },
          "50%": { transform: "translate(20px, -20px)" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "caret-blink": "caret-blink 1.25s ease-out infinite",
        "float": "float 4s ease-in-out infinite",
        "float-slow": "float-slow 20s linear infinite",
        "bounce-down": "bounce-down 2s ease-in-out infinite",
        "pulse-soft": "pulse-soft 2s ease-in-out infinite",
        "drift": "drift 8s ease-in-out infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
