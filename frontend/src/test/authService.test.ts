import { vi, describe, test, expect, beforeEach } from 'vitest'
import axios from 'axios'

// Mock axios.create pour intercepter la creation de l'instance
vi.mock('axios', async () => {
  const mockInterceptors = {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  }
  const mockAxiosInstance = {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    interceptors: mockInterceptors,
  }
  return {
    default: {
      create: vi.fn(() => mockAxiosInstance),
    },
  }
})

describe('AuthService', () => {
  let authService: any
  let mockApi: any
  let responseInterceptorSuccess: (response: any) => any
  let responseInterceptorError: (error: any) => any

  beforeEach(async () => {
    vi.clearAllMocks()

    // Reset le module pour re-instancier AuthService
    vi.resetModules()

    const axiosModule = await import('axios')
    mockApi = axiosModule.default.create()

    // Importer authService apres le mock
    const module = await import('../services/authService')
    authService = module.authService

    // Recuperer les interceptors enregistres (seulement response, plus de request interceptor)
    responseInterceptorSuccess = vi.mocked(mockApi.interceptors.response.use).mock.calls[0][0]
    responseInterceptorError = vi.mocked(mockApi.interceptors.response.use).mock.calls[0][1]
  })

  describe('axios instance configuration', () => {
    test('cree l instance axios avec withCredentials: true', () => {
      expect(axios.create).toHaveBeenCalledWith(
        expect.objectContaining({ withCredentials: true })
      )
    })
  })

  describe('response interceptor', () => {
    test('passe la reponse directement en cas de succes', () => {
      const response = { data: 'ok', status: 200 }
      expect(responseInterceptorSuccess(response)).toEqual(response)
    })

    test('rejette les erreurs non-401', async () => {
      const error = { response: { status: 500 }, config: {} }

      await expect(responseInterceptorError(error)).rejects.toEqual(error)
    })

    test('ne retry pas si deja retry', async () => {
      const error = {
        response: { status: 401 },
        config: { _retry: true },
      }

      await expect(responseInterceptorError(error)).rejects.toEqual(error)
    })
  })

  describe('login', () => {
    test('envoie les credentials en FormData et retourne la reponse', async () => {
      const mockResponse = {
        data: {
          access_token: 'tok',
          refresh_token: 'ref',
          token_type: 'bearer',
          expires_in: 3600,
        },
      }
      mockApi.post.mockResolvedValue(mockResponse)

      const result = await authService.login('test@example.com', 'pass123')

      expect(mockApi.post).toHaveBeenCalledWith(
        '/auth/login',
        expect.any(FormData),
        { headers: { 'Content-Type': undefined } }
      )
      expect(result).toEqual(mockResponse.data)
    })
  })

  describe('signup', () => {
    test('envoie les donnees en JSON et retourne la reponse', async () => {
      const mockResponse = {
        data: {
          access_token: 'tok',
          refresh_token: 'ref',
          token_type: 'bearer',
          expires_in: 3600,
        },
      }
      mockApi.post.mockResolvedValue(mockResponse)

      const result = await authService.signup('test@example.com', 'pass123', 'Test User')

      expect(mockApi.post).toHaveBeenCalledWith('/auth/signup', {
        email: 'test@example.com',
        password: 'pass123',
        full_name: 'Test User',
      })
      expect(result).toEqual(mockResponse.data)
    })
  })

  describe('getCurrentUser', () => {
    test('retourne les donnees utilisateur', async () => {
      const mockUser = { id: '1', email: 'a@b.com', full_name: 'A B', created_at: '2024-01-01' }
      mockApi.get.mockResolvedValue({ data: mockUser })

      const result = await authService.getCurrentUser()

      expect(mockApi.get).toHaveBeenCalledWith('/auth/me')
      expect(result).toEqual(mockUser)
    })
  })

  describe('refreshToken', () => {
    test('appelle POST /auth/refresh sans body (cookie envoye automatiquement)', async () => {
      mockApi.post.mockResolvedValue({ data: { access_token: 'new-token' } })

      const result = await authService.refreshToken()

      expect(mockApi.post).toHaveBeenCalledWith('/auth/refresh')
      expect(result).toEqual({ access_token: 'new-token' })
    })
  })

  describe('logout', () => {
    test('appelle POST /auth/logout pour supprimer les cookies serveur', async () => {
      mockApi.post.mockResolvedValue({ data: { message: 'Logged out' } })

      await authService.logout()

      expect(mockApi.post).toHaveBeenCalledWith('/auth/logout')
    })
  })

  describe('getStravaStatus', () => {
    test('retourne le statut Strava', async () => {
      const mockStatus = { connected: true, athlete_id: 123 }
      mockApi.get.mockResolvedValue({ data: mockStatus })

      const result = await authService.getStravaStatus()

      expect(mockApi.get).toHaveBeenCalledWith('/auth/strava/status')
      expect(result).toEqual(mockStatus)
    })
  })

  describe('RGPD', () => {
    test('deleteStravaData appelle DELETE /data/strava', async () => {
      const mockResult = { message: 'ok', deleted_activities: 5, strava_auth_deleted: true }
      mockApi.delete.mockResolvedValue({ data: mockResult })

      const result = await authService.deleteStravaData()

      expect(mockApi.delete).toHaveBeenCalledWith('/data/strava')
      expect(result).toEqual(mockResult)
    })

    test('deleteAllUserData appelle DELETE /data/all', async () => {
      const mockResult = { message: 'ok', deleted_activities: 5, deleted_workout_plans: 3, strava_auth_deleted: true }
      mockApi.delete.mockResolvedValue({ data: mockResult })

      const result = await authService.deleteAllUserData()

      expect(mockApi.delete).toHaveBeenCalledWith('/data/all')
      expect(result).toEqual(mockResult)
    })

    test('deleteAccount appelle DELETE /account', async () => {
      const mockResult = { message: 'ok', deleted_activities: 5, deleted_workout_plans: 3, strava_auth_deleted: true, account_deleted: true }
      mockApi.delete.mockResolvedValue({ data: mockResult })

      const result = await authService.deleteAccount()

      expect(mockApi.delete).toHaveBeenCalledWith('/account')
      expect(result).toEqual(mockResult)
    })

    test('exportUserData retourne un blob', async () => {
      const mockBlob = new Blob(['data'], { type: 'application/json' })
      mockApi.get.mockResolvedValue({ data: mockBlob })

      const result = await authService.exportUserData()

      expect(mockApi.get).toHaveBeenCalledWith('/data/export', { responseType: 'blob' })
      expect(result).toEqual(mockBlob)
    })
  })
})
