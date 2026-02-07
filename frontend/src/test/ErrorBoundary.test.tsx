import { render, screen, fireEvent } from '@testing-library/react'
import { vi, describe, test, expect, beforeEach } from 'vitest'
import ErrorBoundary from '../components/ErrorBoundary'

// Mock Sentry
vi.mock('@sentry/react', () => ({
  captureException: vi.fn(),
}))

import * as Sentry from '@sentry/react'

// Composant qui lance une erreur volontairement
function ThrowingComponent({ error }: { error: Error }) {
  throw error
}

// Composant normal
function NormalComponent() {
  return <div data-testid="normal">Everything is fine</div>
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Supprimer les logs d'erreur React (attendus dans ces tests)
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  test('rend les enfants quand il n y a pas d erreur', () => {
    render(
      <ErrorBoundary>
        <NormalComponent />
      </ErrorBoundary>
    )

    expect(screen.getByTestId('normal')).toBeInTheDocument()
  })

  test('affiche le fallback global quand un enfant lance une erreur', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent error={new Error('Test crash')} />
      </ErrorBoundary>
    )

    expect(screen.getByText('Une erreur inattendue est survenue')).toBeInTheDocument()
    expect(screen.getByText('Réessayer')).toBeInTheDocument()
    expect(screen.getByText('Recharger la page')).toBeInTheDocument()
  })

  test('affiche le message d erreur dans le detail', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent error={new Error('Broken component')} />
      </ErrorBoundary>
    )

    expect(screen.getByText(/Broken component/)).toBeInTheDocument()
  })

  test('affiche le fallback par section avec sectionName', () => {
    render(
      <ErrorBoundary sectionName="Tableau de bord">
        <ThrowingComponent error={new Error('Dashboard crash')} />
      </ErrorBoundary>
    )

    expect(screen.getByText('Erreur dans Tableau de bord')).toBeInTheDocument()
    expect(screen.getByText(/Dashboard crash/)).toBeInTheDocument()
  })

  test('utilise le fallback custom quand fourni', () => {
    render(
      <ErrorBoundary fallback={<div data-testid="custom-fallback">Custom Error</div>}>
        <ThrowingComponent error={new Error('Custom')} />
      </ErrorBoundary>
    )

    expect(screen.getByTestId('custom-fallback')).toBeInTheDocument()
  })

  test('remonte l erreur a Sentry', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent error={new Error('Sentry test')} />
      </ErrorBoundary>
    )

    expect(Sentry.captureException).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'Sentry test' }),
      expect.objectContaining({ extra: expect.objectContaining({ componentStack: expect.any(String) }) })
    )
  })

  test('le bouton Reessayer reset l erreur et re-rend les enfants', () => {
    let shouldThrow = true

    function ConditionalThrow() {
      if (shouldThrow) throw new Error('Temporary error')
      return <div data-testid="recovered">Recovered</div>
    }

    render(
      <ErrorBoundary>
        <ConditionalThrow />
      </ErrorBoundary>
    )

    expect(screen.getByText('Une erreur inattendue est survenue')).toBeInTheDocument()

    // Corriger l'erreur avant de cliquer Reessayer
    shouldThrow = false
    fireEvent.click(screen.getByText('Réessayer'))

    expect(screen.getByTestId('recovered')).toBeInTheDocument()
  })

  test('le bouton Recharger la page appelle window.location.reload', () => {
    const reloadMock = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { ...window.location, reload: reloadMock },
      writable: true,
    })

    render(
      <ErrorBoundary>
        <ThrowingComponent error={new Error('Reload test')} />
      </ErrorBoundary>
    )

    fireEvent.click(screen.getByText('Recharger la page'))

    expect(reloadMock).toHaveBeenCalled()
  })
})
