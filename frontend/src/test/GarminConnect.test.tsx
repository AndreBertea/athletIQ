import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi, describe, test, expect, beforeEach } from 'vitest'
import GarminConnect from '../pages/GarminConnect'
import { ToastProvider } from '../contexts/ToastContext'
import type { GarminStatus, GarminDailyEntry } from '../services/garminService'

// Mock du service Garmin
vi.mock('../services/garminService', () => ({
  garminService: {
    loginGarmin: vi.fn(),
    getGarminStatus: vi.fn(),
    disconnectGarmin: vi.fn(),
    syncGarminDaily: vi.fn(),
    getGarminDaily: vi.fn(),
  },
}))

import { garminService } from '../services/garminService'

const mockStatusDisconnected: GarminStatus = {
  connected: false,
}

const mockStatusConnected: GarminStatus = {
  connected: true,
  display_name: 'TestRunner',
  token_created_at: '2026-02-01T10:00:00Z',
  last_sync_at: '2026-02-06T08:30:00Z',
}

const mockDailyData: GarminDailyEntry[] = [
  { date: '2026-02-06', hrv_rmssd: 55, training_readiness: 72, sleep_score: 85, sleep_duration_min: 450, resting_hr: 52, stress_score: 30, body_battery_max: 90 },
  { date: '2026-02-05', hrv_rmssd: 48, training_readiness: 35, sleep_score: 60, sleep_duration_min: 380, resting_hr: 55, stress_score: 45, body_battery_max: 70 },
  { date: '2026-02-04', hrv_rmssd: null, training_readiness: null, sleep_score: null, sleep_duration_min: null, resting_hr: null, stress_score: null, body_battery_max: null },
]

const renderWithProviders = (component: React.ReactElement) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastProvider>
          {component}
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

describe('GarminConnect — Non connecte', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(garminService.getGarminStatus).mockResolvedValue(mockStatusDisconnected)
    vi.mocked(garminService.getGarminDaily).mockResolvedValue([])
  })

  test('affiche le formulaire login quand non connecte', async () => {
    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByText('Connexion Garmin')).toBeInTheDocument()
    })

    expect(screen.getByLabelText('Email Garmin')).toBeInTheDocument()
    expect(screen.getByLabelText('Mot de passe Garmin')).toBeInTheDocument()
    expect(screen.getByText('Connecter Garmin')).toBeInTheDocument()
  })

  test('affiche la notice de securite (identifiants non stockes)', async () => {
    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByText(/Vos identifiants ne sont pas stock/)).toBeInTheDocument()
    })
  })

  test('affiche le status "Garmin non connecte"', async () => {
    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByText('Garmin non connecte')).toBeInTheDocument()
    })
  })

  test('le bouton submit est desactive si email ou password vides', async () => {
    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByText('Connecter Garmin')).toBeInTheDocument()
    })

    const submitButton = screen.getByText('Connecter Garmin')
    expect(submitButton).toBeDisabled()
  })

  test('le bouton submit est active quand email et password remplis', async () => {
    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByLabelText('Email Garmin')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Email Garmin'), { target: { value: 'test@garmin.com' } })
    fireEvent.change(screen.getByLabelText('Mot de passe Garmin'), { target: { value: 'secret123' } })

    const submitButton = screen.getByText('Connecter Garmin')
    expect(submitButton).not.toBeDisabled()
  })

  test('appelle loginGarmin au submit du formulaire', async () => {
    vi.mocked(garminService.loginGarmin).mockResolvedValue({ message: 'OK' })

    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByLabelText('Email Garmin')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Email Garmin'), { target: { value: 'test@garmin.com' } })
    fireEvent.change(screen.getByLabelText('Mot de passe Garmin'), { target: { value: 'secret123' } })
    fireEvent.click(screen.getByText('Connecter Garmin'))

    await waitFor(() => {
      expect(garminService.loginGarmin).toHaveBeenCalledWith('test@garmin.com', 'secret123')
    })
  })

  test('affiche le loading pendant la connexion', async () => {
    vi.mocked(garminService.loginGarmin).mockImplementation(() => new Promise(() => {}))

    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByLabelText('Email Garmin')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Email Garmin'), { target: { value: 'test@garmin.com' } })
    fireEvent.change(screen.getByLabelText('Mot de passe Garmin'), { target: { value: 'secret123' } })
    fireEvent.click(screen.getByText('Connecter Garmin'))

    await waitFor(() => {
      expect(screen.getByText('Connexion en cours...')).toBeInTheDocument()
    })
  })

  test('ne montre PAS les controles sync/deconnexion quand non connecte', async () => {
    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByText('Garmin non connecte')).toBeInTheDocument()
    })

    expect(screen.queryByText('Synchronisation des donnees')).not.toBeInTheDocument()
    expect(screen.queryByText('Deconnecter Garmin')).not.toBeInTheDocument()
  })
})

describe('GarminConnect — Connecte', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(garminService.getGarminStatus).mockResolvedValue(mockStatusConnected)
    vi.mocked(garminService.getGarminDaily).mockResolvedValue(mockDailyData)
  })

  test('affiche le status "Garmin connecte" avec display_name', async () => {
    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByText('Garmin connecte')).toBeInTheDocument()
    })

    expect(screen.getByText(/TestRunner/)).toBeInTheDocument()
  })

  test('ne montre PAS le formulaire login quand connecte', async () => {
    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByText('Garmin connecte')).toBeInTheDocument()
    })

    expect(screen.queryByLabelText('Email Garmin')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Mot de passe Garmin')).not.toBeInTheDocument()
  })

  test('affiche le selecteur de jours avec les options', async () => {
    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByLabelText('Periode de synchronisation')).toBeInTheDocument()
    })

    const select = screen.getByLabelText('Periode de synchronisation') as HTMLSelectElement
    expect(select.value).toBe('30')
    expect(screen.getByText('7 derniers jours')).toBeInTheDocument()
    expect(screen.getByText('14 derniers jours')).toBeInTheDocument()
    expect(screen.getByText('30 derniers jours (recommande)')).toBeInTheDocument()
    expect(screen.getByText('2 derniers mois')).toBeInTheDocument()
    expect(screen.getByText('3 derniers mois')).toBeInTheDocument()
  })

  test('change la valeur du selecteur days_back', async () => {
    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByLabelText('Periode de synchronisation')).toBeInTheDocument()
    })

    const select = screen.getByLabelText('Periode de synchronisation') as HTMLSelectElement
    fireEvent.change(select, { target: { value: '7' } })
    expect(select.value).toBe('7')
  })

  test('affiche le bouton sync et appelle syncGarminDaily', async () => {
    vi.mocked(garminService.syncGarminDaily).mockResolvedValue({ message: 'Sync OK', days_synced: 30 })

    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Synchroniser \(30 jours\)/ })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Synchroniser \(30 jours\)/ }))

    await waitFor(() => {
      expect(garminService.syncGarminDaily).toHaveBeenCalledWith(30)
    })
  })

  test('affiche l apercu des 7 derniers jours avec les donnees', async () => {
    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByText('Apercu — 7 derniers jours')).toBeInTheDocument()
    })

    // Verifie les valeurs HRV
    await waitFor(() => {
      expect(screen.getByText('55')).toBeInTheDocument()
      expect(screen.getByText('48')).toBeInTheDocument()
    })

    // Verifie training readiness
    expect(screen.getByText('72')).toBeInTheDocument()
    expect(screen.getByText('35')).toBeInTheDocument()

    // Verifie sleep score
    expect(screen.getByText('85')).toBeInTheDocument()
    expect(screen.getByText('60')).toBeInTheDocument()
  })

  test('affiche des tirets pour les valeurs null', async () => {
    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByText('Apercu — 7 derniers jours')).toBeInTheDocument()
    })

    // La 3e ligne (2026-02-04) a toutes les valeurs null → tirets
    await waitFor(() => {
      const dashes = screen.getAllByText('—')
      expect(dashes.length).toBeGreaterThanOrEqual(3)
    })
  })

  test('applique le code couleur training readiness (vert >= 70, jaune >= 40, rouge < 40)', async () => {
    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByText('72')).toBeInTheDocument()
    })

    // 72 → vert
    expect(screen.getByText('72').className).toContain('text-green-600')
    // 35 → rouge
    expect(screen.getByText('35').className).toContain('text-red-600')
  })

  test('affiche le bouton de deconnexion', async () => {
    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByText('Deconnecter Garmin')).toBeInTheDocument()
    })
  })

  test('appelle disconnectGarmin au clic sur deconnecter', async () => {
    vi.mocked(garminService.disconnectGarmin).mockResolvedValue({ message: 'OK' })

    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByText('Deconnecter')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Deconnecter'))

    await waitFor(() => {
      expect(garminService.disconnectGarmin).toHaveBeenCalled()
    })
  })
})

describe('GarminConnect — Donnees vides', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(garminService.getGarminStatus).mockResolvedValue(mockStatusConnected)
    vi.mocked(garminService.getGarminDaily).mockResolvedValue([])
  })

  test('affiche un message quand aucune donnee disponible', async () => {
    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByText('Aucune donnee disponible. Lancez une synchronisation.')).toBeInTheDocument()
    })
  })
})

describe('GarminConnect — Info securite', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(garminService.getGarminStatus).mockResolvedValue(mockStatusDisconnected)
    vi.mocked(garminService.getGarminDaily).mockResolvedValue([])
  })

  test('affiche la section info securite', async () => {
    renderWithProviders(<GarminConnect />)

    await waitFor(() => {
      expect(screen.getByText('A propos de la connexion Garmin')).toBeInTheDocument()
    })

    expect(screen.getByText(/email et mot de passe Garmin ne sont jamais stock/)).toBeInTheDocument()
    expect(screen.getByText(/HRV, Training Readiness, sommeil/)).toBeInTheDocument()
  })
})
