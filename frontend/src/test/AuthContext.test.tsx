import { render, screen, act, waitFor } from '@testing-library/react'
import { vi, describe, test, expect, beforeEach } from 'vitest'
import { AuthProvider, useAuth } from '../contexts/AuthContext'

// Mock authService
vi.mock('../services/authService', () => ({
  authService: {
    login: vi.fn(),
    signup: vi.fn(),
    getCurrentUser: vi.fn(),
    refreshToken: vi.fn(),
    logout: vi.fn(),
  },
}))

import { authService } from '../services/authService'

const mockUser = {
  id: '1',
  email: 'test@example.com',
  full_name: 'Test User',
  created_at: '2024-01-01T00:00:00Z',
}

const mockTokens = {
  access_token: 'access-token-123',
  refresh_token: 'refresh-token-456',
  token_type: 'bearer',
  expires_in: 3600,
}

// Composant helper pour acceder au contexte dans les tests
function AuthConsumer({ onAuth }: { onAuth: (auth: ReturnType<typeof useAuth>) => void }) {
  const auth = useAuth()
  onAuth(auth)
  return <div data-testid="consumer">loaded</div>
}

describe('AuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('initialise avec loading=true puis passe a loading=false sans session', async () => {
    // getCurrentUser echoue => pas de session cookie valide
    vi.mocked(authService.getCurrentUser).mockRejectedValue(new Error('Unauthorized'))

    let authState: ReturnType<typeof useAuth> | null = null

    await act(async () => {
      render(
        <AuthProvider>
          <AuthConsumer onAuth={(auth) => { authState = auth }} />
        </AuthProvider>
      )
    })

    expect(authState!.loading).toBe(false)
    expect(authState!.user).toBeNull()
  })

  test('charge le user depuis le cookie existant (via getCurrentUser)', async () => {
    vi.mocked(authService.getCurrentUser).mockResolvedValue(mockUser)

    let authState: ReturnType<typeof useAuth> | null = null

    await act(async () => {
      render(
        <AuthProvider>
          <AuthConsumer onAuth={(auth) => { authState = auth }} />
        </AuthProvider>
      )
    })

    expect(authService.getCurrentUser).toHaveBeenCalled()
    expect(authState!.user).toEqual(mockUser)
    expect(authState!.loading).toBe(false)
  })

  test('user reste null si getCurrentUser echoue a l initialisation', async () => {
    vi.mocked(authService.getCurrentUser).mockRejectedValue(new Error('Unauthorized'))

    let authState: ReturnType<typeof useAuth> | null = null

    await act(async () => {
      render(
        <AuthProvider>
          <AuthConsumer onAuth={(auth) => { authState = auth }} />
        </AuthProvider>
      )
    })

    // Pas de manipulation de localStorage, le cookie est gere par le navigateur
    expect(authService.getCurrentUser).toHaveBeenCalled()
    expect(authState!.user).toBeNull()
  })

  test('login appelle authService.login puis charge le user', async () => {
    vi.mocked(authService.login).mockResolvedValue(mockTokens)
    vi.mocked(authService.getCurrentUser)
      .mockRejectedValueOnce(new Error('Unauthorized'))  // init
      .mockResolvedValueOnce(mockUser)  // apres login

    let authState: ReturnType<typeof useAuth> | null = null

    await act(async () => {
      render(
        <AuthProvider>
          <AuthConsumer onAuth={(auth) => { authState = auth }} />
        </AuthProvider>
      )
    })

    await act(async () => {
      await authState!.login('test@example.com', 'password123')
    })

    expect(authService.login).toHaveBeenCalledWith('test@example.com', 'password123')
    // Le backend pose les cookies httpOnly, le frontend n'a plus a stocker les tokens
    expect(authState!.user).toEqual(mockUser)
  })

  test('signup appelle authService.signup puis charge le user', async () => {
    vi.mocked(authService.signup).mockResolvedValue(mockTokens)
    vi.mocked(authService.getCurrentUser)
      .mockRejectedValueOnce(new Error('Unauthorized'))  // init
      .mockResolvedValueOnce(mockUser)  // apres signup

    let authState: ReturnType<typeof useAuth> | null = null

    await act(async () => {
      render(
        <AuthProvider>
          <AuthConsumer onAuth={(auth) => { authState = auth }} />
        </AuthProvider>
      )
    })

    await act(async () => {
      await authState!.signup('test@example.com', 'password123', 'Test User')
    })

    expect(authService.signup).toHaveBeenCalledWith('test@example.com', 'password123', 'Test User')
    expect(authState!.user).toEqual(mockUser)
  })

  test('logout appelle authService.logout et remet user a null', async () => {
    vi.mocked(authService.getCurrentUser).mockResolvedValue(mockUser)

    let authState: ReturnType<typeof useAuth> | null = null

    await act(async () => {
      render(
        <AuthProvider>
          <AuthConsumer onAuth={(auth) => { authState = auth }} />
        </AuthProvider>
      )
    })

    expect(authState!.user).toEqual(mockUser)

    act(() => {
      authState!.logout()
    })

    // Le logout appelle le backend qui supprime les cookies httpOnly
    expect(authService.logout).toHaveBeenCalled()
    expect(authState!.user).toBeNull()
  })

  test('refreshToken appelle authService.refreshToken', async () => {
    vi.mocked(authService.getCurrentUser).mockRejectedValue(new Error('Unauthorized'))
    vi.mocked(authService.refreshToken).mockResolvedValue({ access_token: 'new-access-token' })

    let authState: ReturnType<typeof useAuth> | null = null

    await act(async () => {
      render(
        <AuthProvider>
          <AuthConsumer onAuth={(auth) => { authState = auth }} />
        </AuthProvider>
      )
    })

    await act(async () => {
      await authState!.refreshToken()
    })

    expect(authService.refreshToken).toHaveBeenCalled()
  })

  test('useAuth lance une erreur en dehors d AuthProvider', () => {
    function Orphan() {
      useAuth()
      return null
    }

    expect(() => render(<Orphan />)).toThrow('useAuth must be used within an AuthProvider')
  })
})
