import axios from 'axios'

// Utiliser l'URL de l'API configurée via VITE_API_URL ou fallback sur relative
const VITE_API_URL = (import.meta as any).env?.VITE_API_URL
const API_BASE_URL = VITE_API_URL ? `${VITE_API_URL}/api/v1` : '/api/v1'

interface StravaStatus {
  connected: boolean
  athlete_id?: number
  scope?: string
  expires_at?: string
  is_expired?: boolean
  last_sync?: string
}

interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

interface User {
  id: string
  email: string
  full_name: string
  created_at: string
}

class AuthService {
  private api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
      'Content-Type': 'application/json',
    },
    withCredentials: true,
  })

  constructor() {
    // Interceptor pour gérer le refresh token automatique
    this.api.interceptors.response.use(
      (response) => response,
      async (error) => {
        const originalRequest = error.config

        if (
          error.response?.status === 401 &&
          !originalRequest._retry &&
          !originalRequest.url?.includes('/auth/refresh') &&
          !originalRequest.url?.includes('/auth/login')
        ) {
          originalRequest._retry = true

          try {
            await this.refreshToken()
            // Retry la requête originale (le cookie est mis à jour automatiquement)
            return this.api(originalRequest)
          } catch (refreshError) {
            // Refresh token invalide, rediriger vers login
            if (!window.location.pathname.includes('/login') && !window.location.pathname.includes('/signup')) {
              window.location.href = '/login'
            }
          }
        }

        return Promise.reject(error)
      }
    )
  }

  async login(email: string, password: string): Promise<LoginResponse> {
    const formData = new FormData()
    formData.append('email', email)
    formData.append('password', password)

    const response = await this.api.post('/auth/login', formData, {
      headers: {
        'Content-Type': undefined, // Supprimer l'en-tête Content-Type pour FormData
      },
    })
    return response.data
  }

  async signup(email: string, password: string, fullName: string): Promise<LoginResponse> {
    const response = await this.api.post('/auth/signup', {
      email,
      password,
      full_name: fullName,
    })
    return response.data
  }

  async getCurrentUser(): Promise<User> {
    const response = await this.api.get('/auth/me')
    return response.data
  }

  async refreshToken(): Promise<{ access_token: string }> {
    const response = await this.api.post('/auth/refresh')
    return response.data
  }

  async logout(): Promise<void> {
    try {
      await this.api.post('/auth/logout')
    } catch {
      // Ignorer les erreurs de logout (ex: réseau)
    }
  }

  async getStravaStatus(): Promise<StravaStatus> {
    const response = await this.api.get('/auth/strava/status')
    return response.data
  }

  async initiateStravaLogin() {
    const response = await this.api.get('/auth/strava/login')
    return response.data
  }

  // ============ RGPD - SUPPRESSION DES DONNÉES ============

  async deleteStravaData(): Promise<{
    message: string
    deleted_activities: number
    strava_auth_deleted: boolean
  }> {
    const response = await this.api.delete('/data/strava')
    return response.data
  }

  async deleteAllUserData(): Promise<{
    message: string
    deleted_activities: number
    deleted_workout_plans: number
    strava_auth_deleted: boolean
  }> {
    const response = await this.api.delete('/data/all')
    return response.data
  }

  async deleteAccount(): Promise<{
    message: string
    deleted_activities: number
    deleted_workout_plans: number
    strava_auth_deleted: boolean
    account_deleted: boolean
  }> {
    const response = await this.api.delete('/account')
    return response.data
  }

  async exportUserData(): Promise<Blob> {
    const response = await this.api.get('/data/export', {
      responseType: 'blob'
    })
    return response.data
  }
}

export const authService = new AuthService()
