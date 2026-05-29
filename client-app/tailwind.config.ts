/**
 * Tailwind config AGON — Direction Violet.
 * Palette : violet primary (logo) + moss + stone + orchid + deep night.
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
        // Palette primary 50-900 derivee du violet du logo #9C49F5
        primary: {
          50: '#f5eefe',
          100: '#e9dbfd',
          200: '#d4bafb',
          300: '#be96f9',
          400: '#ac73f7',
          500: '#9C49F5',   // <- AGON violet (cercle du logo)
          600: '#8a2be2',
          700: '#7321c4',
          800: '#5b1a9b',
          900: '#421372',
          DEFAULT: '#9C49F5',
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
