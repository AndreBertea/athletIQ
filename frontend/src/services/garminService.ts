import axios from 'axios'

const VITE_API_URL = (import.meta as any).env?.VITE_API_URL
const API_BASE_URL = VITE_API_URL ? `${VITE_API_URL}/api/v1` : '/api/v1'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

// --- Types ---

export interface GarminStatus {
  connected: boolean
  display_name?: string
  token_created_at?: string
  last_sync_at?: string
}

export interface GarminDailyEntry {
  date: string
  hrv_rmssd: number | null
  training_readiness: number | null
  sleep_score: number | null
  sleep_duration_min: number | null
  resting_hr: number | null
  stress_score: number | null
  body_battery_max: number | null
}

// --- Service ---

export const garminService = {
  async loginGarmin(email: string, password: string): Promise<{ message: string }> {
    const res = await api.post('/auth/garmin/login', { email, password })
    return res.data
  },

  async getGarminStatus(): Promise<GarminStatus> {
    const res = await api.get('/auth/garmin/status')
    return res.data
  },

  async disconnectGarmin(): Promise<{ message: string }> {
    const res = await api.delete('/auth/garmin/disconnect')
    return res.data
  },

  async syncGarminDaily(daysBack: number = 30): Promise<{ message: string; days_synced: number }> {
    const res = await api.post(`/sync/garmin?days_back=${daysBack}`)
    return res.data
  },

  async getGarminDaily(dateFrom?: string, dateTo?: string): Promise<GarminDailyEntry[]> {
    const params: Record<string, string> = {}
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    const res = await api.get('/garmin/daily', { params })
    return res.data
  },
}
