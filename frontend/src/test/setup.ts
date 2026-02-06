import '@testing-library/jest-dom'
import { vi } from 'vitest'

// Mock de react-plotly.js pour éviter les erreurs dans les tests
vi.mock('react-plotly.js', () => ({
  default: vi.fn(() => {
    const React = require('react')
    return React.createElement('div', { 'data-testid': 'plotly-chart' }, 'Mocked Chart')
  }),
}))

// Mock de window.location pour les tests de navigation
Object.defineProperty(window, 'location', {
  value: {
    href: 'http://localhost:3000',
    search: '',
    pathname: '/',
    replace: vi.fn(),
  },
  writable: true,
})

// Mock de window.history pour les tests
Object.defineProperty(window, 'history', {
  value: {
    replaceState: vi.fn(),
    pushState: vi.fn(),
  },
  writable: true,
})

// Variables d'environnement pour les tests
process.env.VITE_API_URL = 'http://localhost:4100' 