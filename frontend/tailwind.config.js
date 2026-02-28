/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        'bg-secondary': 'var(--bg-secondary)',
        surface: 'var(--surface)',
        surface2: 'var(--surface2)',
        border: 'var(--border)',
        text: 'var(--text)',
        'text-muted': 'var(--text-muted)',
        accent: 'var(--accent)',
        'accent-light': 'var(--accent-light)',
        'accent-glow': 'var(--accent-glow)',
        danger: 'var(--danger)',
        warning: 'var(--warning)',
      },
      fontFamily: {
        display: ['"Clash Display"', 'sans-serif'],
        body: ['Satoshi', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
    },
  },
  plugins: [],
  darkMode: ['class', '[data-theme="dark"]'],
}
