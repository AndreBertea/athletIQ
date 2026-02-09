import axios from 'axios'

const VITE_API_URL = (import.meta as any).env?.VITE_API_URL
const API_BASE_URL = VITE_API_URL ? `${VITE_API_URL}/api/v1` : '/api/v1'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

// --- Types ---

export interface ActivityWeather {
  id: string
  activity_id: string
  temperature_c: number | null
  humidity_pct: number | null
  wind_speed_kmh: number | null
  wind_direction_deg: number | null
  pressure_hpa: number | null
  precipitation_mm: number | null
  cloud_cover_pct: number | null
  weather_code: number | null
}

export interface TrainingLoadEntry {
  id: string
  user_id: string
  date: string
  ctl_42d: number | null
  atl_7d: number | null
  tsb: number | null
  rhr_delta_7d: number | null
  edwards_trimp_daily: number | null
  ctl_42d_edwards: number | null
  atl_7d_edwards: number | null
  tsb_edwards: number | null
  created_at: string
  updated_at: string
}

// --- Service ---

export const dataService = {
  async getWeather(activityId: string): Promise<ActivityWeather> {
    const res = await api.get(`/weather/${activityId}`)
    return res.data
  },

  async getTrainingLoad(dateFrom?: string, dateTo?: string): Promise<TrainingLoadEntry[]> {
    const params: Record<string, string> = {}
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    const res = await api.get('/training-load', { params })
    return res.data
  },
}
