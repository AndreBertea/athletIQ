import axios from 'axios'

// Utiliser l'URL de l'API configurée via VITE_API_URL ou fallback sur relative
const VITE_API_URL = (import.meta as any).env?.VITE_API_URL
const API_URL = VITE_API_URL ? 
  (VITE_API_URL.endsWith('/api/v1') ? VITE_API_URL : `${VITE_API_URL}/api/v1`) : 
  '/api/v1'

// Types pour Google Calendar
export interface GoogleCalendar {
  id: string
  summary: string
  description?: string
  primary: boolean
  accessRole: string
}

export interface GoogleAuthStatus {
  connected: boolean
  google_user_id?: string
  scope?: string
  expires_at?: string
  is_expired?: boolean
}

export interface GoogleCalendarExportResult {
  success: boolean
  message: string
  exported_count: number
  total_count: number
  errors: string[]
}

export interface GoogleCalendarImportResult {
  success: boolean
  message: string
  imported_count: number
  total_count: number
  errors: string[]
}



const api = axios.create({
  baseURL: API_URL,
  withCredentials: true,
})

// Service pour Google Calendar
export const googleCalendarService = {
  // Initier la connexion OAuth Google
  async initiateGoogleLogin(): Promise<{ authorization_url: string }> {
    try {
      const response = await api.get('/auth/google/login')
      console.log('Réponse Google login:', response.data)

      if (!response.data.auth_url) {
        throw new Error('URL d\'autorisation manquante dans la réponse')
      }

      return { authorization_url: response.data.auth_url }
    } catch (error) {
      console.error('Erreur lors de l\'initiation Google login:', error)
      throw error
    }
  },

  // Vérifier le statut de la connexion Google
  async getGoogleStatus(): Promise<GoogleAuthStatus> {
    const response = await api.get('/auth/google/status')
    return response.data
  },

  // Rafraîchir automatiquement le token Google
  async refreshGoogleToken(): Promise<{ success: boolean; message: string; expires_at?: string }> {
    const response = await api.post('/auth/google/refresh')
    return response.data
  },

  // Récupérer la liste des calendriers Google
  async getGoogleCalendars(): Promise<GoogleCalendar[]> {
    const response = await api.get('/google-calendar/calendars')
    return response.data.calendars
  },

  // Exporter les plans d'entraînement vers Google Calendar
  async exportWorkoutPlansToGoogle(calendarId: string = "primary"): Promise<GoogleCalendarExportResult> {
    const response = await api.post('/google-calendar/export', { calendar_id: calendarId })
    return response.data
  },

  // Importer un calendrier Google comme plans d'entraînement
  async importGoogleCalendarAsWorkoutPlans(
    calendarId: string = "primary",
    startDate?: string,
    endDate?: string
  ): Promise<GoogleCalendarImportResult> {
    const params = new URLSearchParams()
    params.append('calendar_id', calendarId)
    if (startDate) params.append('start_date', startDate)
    if (endDate) params.append('end_date', endDate)

    const response = await api.post('/google-calendar/import', params, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    })
    return response.data
  },


}

// Utilitaires pour Google Calendar
export const googleCalendarUtils = {
  // Formater le nom du calendrier pour l'affichage
  formatCalendarName(calendar: GoogleCalendar): string {
    if (calendar.primary) {
      return `${calendar.summary} (Principal)`
    }
    return calendar.summary
  },

  // Obtenir la couleur CSS pour le type de calendrier
  getCalendarColor(calendar: GoogleCalendar): string {
    if (calendar.primary) {
      return 'text-blue-600'
    }
    return 'text-gray-700'
  },

  // Vérifier si l'utilisateur peut écrire dans le calendrier
  canWriteToCalendar(calendar: GoogleCalendar): boolean {
    return ['owner', 'writer'].includes(calendar.accessRole)
  },

  // Formater la date pour l'API Google
  formatDateForGoogle(date: Date): string {
    return date.toISOString().split('T')[0]
  },

  // Parser la date depuis l'API Google
  parseGoogleDate(dateString: string): Date {
    return new Date(dateString)
  }
} 