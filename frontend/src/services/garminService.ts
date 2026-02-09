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

export interface FitMetrics {
  id: string
  activity_id: string

  // Running Dynamics
  ground_contact_time_avg: number | null
  vertical_oscillation_avg: number | null
  stance_time_balance_avg: number | null
  stance_time_percent_avg: number | null
  step_length_avg: number | null
  vertical_ratio_avg: number | null

  // Puissance
  power_avg: number | null
  power_max: number | null
  normalized_power: number | null

  // Cadence
  cadence_avg: number | null
  cadence_max: number | null

  // FC
  heart_rate_avg: number | null
  heart_rate_max: number | null

  // Vitesse
  speed_avg: number | null
  speed_max: number | null

  // Température
  temperature_avg: number | null
  temperature_max: number | null

  // Training Effect
  aerobic_training_effect: number | null
  anaerobic_training_effect: number | null

  // Totaux
  total_calories: number | null
  total_strides: number | null
  total_ascent: number | null
  total_descent: number | null
  total_distance: number | null
  total_timer_time: number | null
  total_elapsed_time: number | null

  // Metadata
  record_count: number | null
  fit_downloaded_at: string | null
}

export interface GarminActivitySyncResult {
  created: number
  linked: number
  skipped: number
  errors: number
  total: number
}

export interface FitEnrichResult {
  status: string
  activity_id: string
  streams_keys?: string[]
  fit_metrics_stored?: boolean
  segments_created?: number
  weather_enriched?: boolean
}

export interface BatchEnrichResult {
  enriched: number
  errors: number
  total: number
}

export interface GarminEnrichmentStatus {
  total_garmin_activities: number
  enriched_activities: number
  pending_activities: number
  enrichment_percentage: number
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
  spo2: number | null
  vo2max_estimated: number | null
  weight_kg: number | null
  body_battery_min: number | null
  training_status: string | null
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

  async syncGarminActivities(daysBack: number = 30): Promise<GarminActivitySyncResult> {
    const res = await api.post(`/sync/garmin/activities?days_back=${daysBack}`)
    return res.data
  },

  async enrichGarminFit(activityId: string): Promise<FitEnrichResult> {
    const res = await api.post(`/garmin/activities/${activityId}/enrich-fit`)
    return res.data
  },

  async batchEnrichGarminFit(maxActivities: number = 10): Promise<BatchEnrichResult> {
    const res = await api.post(`/garmin/activities/enrich-fit?max_activities=${maxActivities}`)
    return res.data
  },

  async getActivityFitMetrics(activityId: string): Promise<FitMetrics> {
    const res = await api.get(`/garmin/activities/${activityId}/fit-metrics`)
    return res.data
  },

  async getGarminEnrichmentStatus(): Promise<GarminEnrichmentStatus> {
    const res = await api.get('/garmin/enrichment-status')
    return res.data
  },
}
