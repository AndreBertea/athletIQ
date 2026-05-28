/**
 * Tailwind config AGON — Direction Trail Organique.
 * Palette : terra red primary + moss + stone + sunset + deep night.
 */
import type { Config } from 'tailwindcss'
import forms from '@tailwindcss/forms'
import animate from 'tailwindcss-animate'

const config: Config = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Tokens semantic (CSS vars dans design-system.css)
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        card: 'var(--card)',
        popover: 'var(--popover)',
        muted: {
          DEFAULT: 'var(--surface-2)',
          foreground: 'var(--muted-foreground)',
        },
        border: {
          DEFAULT: 'var(--border)',
          subtle: 'var(--border-subtle)',
        },
        input: 'var(--input-border)',
        ring: 'var(--ring)',
        // Brand AGON
        brand: {
          terra: 'var(--brand-primary)',
          moss: 'var(--brand-moss)',
          stone: 'var(--brand-stone)',
          sunset: 'var(--brand-sunset)',
          night: 'var(--brand-night)',
          ivory: 'var(--brand-ivory)',
          // Alias retro-compat (mapping sur les nouvelles couleurs)
          primary: 'var(--brand-primary)',
          cyan: 'var(--brand-sunset)',
          coral: 'var(--brand-sunset)',
        },
        // Palette primary 50-900 derivee de terra red #A0432E
        primary: {
          50: '#fdf3f0',
          100: '#fae0d8',
          200: '#f4bca9',
          300: '#ec947a',
          400: '#df694b',
          500: '#c75636',
          600: '#A0432E',   // <- AGON terra red
          700: '#823525',
          800: '#66291e',
          900: '#4a1f17',
          DEFAULT: '#A0432E',
        },
        success: {
          DEFAULT: 'var(--success)',
          fg: 'var(--success-fg)',
          bg: 'var(--success-bg)',
        },
        warning: {
          DEFAULT: 'var(--warning)',
          fg: 'var(--warning-fg)',
          bg: 'var(--warning-bg)',
        },
        danger: {
          DEFAULT: 'var(--danger)',
          fg: 'var(--danger-fg)',
          bg: 'var(--danger-bg)',
        },
      },
      fontFamily: {
        sans: ['Inter Tight', 'Inter', 'system-ui', 'sans-serif'],
        display: ['Druk Wide', 'GT America Condensed', 'Space Grotesk', 'Inter Tight', 'sans-serif'],
        text: ['Inter Tight', 'Inter', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        xs: 'var(--radius-xs)',
        sm: 'var(--radius-sm)',
        DEFAULT: 'var(--radius)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
      },
      boxShadow: {
        glow: 'var(--glow-primary)',
        'glow-cyan': 'var(--glow-cyan)',
        'glow-sunset': 'var(--glow-cyan)',
      },
    },
  },
  plugins: [forms, animate],
}

export default config
