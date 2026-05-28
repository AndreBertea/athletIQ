import { api } from './supabaseApi'

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
  sampled_at?: string | null
  latitude?: number | null
  longitude?: number | null
  elevation_m?: number | null
  source_endpoint?: string | null
  source_url?: string | null
  request_params?: Record<string, unknown> | null
  hourly_units?: Record<string, unknown> | null
  hourly_snapshot?: Record<string, unknown> | null
}

export interface WeatherStatus {
  total_activities: number
  with_streams: number
  with_coordinates: number
  eligible_weather_activities: number
  with_weather: number
  with_weather_payload?: number
  pending_weather: number
  pending_weather_payload?: number
  without_coordinates: number
  forecast_supported_activities?: number
  archive_required_activities?: number
}

export interface WeatherEnrichmentResult {
  processed: number
  skipped: number
  errors: number
  remaining?: number
  archive_required?: number
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

  async getWeatherStatus(): Promise<WeatherStatus> {
    const res = await api.get('/weather/status')
    return res.data
  },

  async enrichWeather(
    maxActivities: number = 25,
    includeHistoricalArchive: boolean = false
  ): Promise<WeatherEnrichmentResult> {
    const res = await api.post('/weather/enrich', null, {
      params: {
        max_activities: maxActivities,
        include_historical_archive: includeHistoricalArchive,
      },
    })
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
