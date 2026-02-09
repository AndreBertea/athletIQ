import axios from 'axios'

const VITE_API_URL = (import.meta as any).env?.VITE_API_URL
const API_BASE_URL = VITE_API_URL ? `${VITE_API_URL}/api/v1` : '/api/v1'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

// --- Types ---

export interface SegmentData {
  id: string
  activity_id: string
  segment_index: number
  distance_m: number
  elapsed_time_s: number
  avg_grade_percent: number | null
  elevation_gain_m: number | null
  elevation_loss_m: number | null
  altitude_m: number | null
  avg_hr: number | null
  avg_cadence: number | null
  lat: number | null
  lon: number | null
  pace_min_per_km: number | null
}

export interface SegmentFeaturesData {
  id: string
  segment_id: string
  activity_id: string
  cumulative_distance_km: number
  elapsed_time_min: number
  cumulative_elev_gain_m: number | null
  cumulative_elev_loss_m: number | null
  race_completion_pct: number | null
  intensity_proxy: number | null
  minetti_cost: number | null
  cardiac_drift: number | null
  cadence_decay: number | null
  grade_variability: number | null
  efficiency_factor: number | null
}

export interface SegmentWithFeatures {
  segment: SegmentData
  features: SegmentFeaturesData | null
}

export interface SegmentResponse {
  activity_id: string
  segment_count: number
  segments: SegmentWithFeatures[]
}

// --- API ---

export const segmentService = {
  async getSegments(activityId: string | number): Promise<SegmentResponse> {
    const response = await api.get(`/segments/${activityId}`)
    return response.data
  },

  async processSegments(activityId: string | number): Promise<{ activity_id: string; segments_created: number }> {
    const response = await api.post(`/segments/process/${activityId}`)
    return response.data
  },
}
