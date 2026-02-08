import axios from 'axios'

// Utiliser l'URL de l'API configurée via VITE_API_URL ou fallback sur relative
const VITE_API_URL = (import.meta as any).env?.VITE_API_URL
const API_BASE_URL = VITE_API_URL ? `${VITE_API_URL}/api/v1` : '/api/v1'

interface Activity {
  id: string
  name: string
  activity_type: string
  start_date: string
  distance: number
  moving_time: number
  average_pace?: number
  location_city?: string
  strava_id?: number
}

export interface ActivityStats {
  total_activities: number
  total_distance: number
  total_time: number
  average_pace: number
  activities_by_type: Record<string, number>
  distance_by_month: Record<string, number>
}

interface StravaQuotaStatus {
  daily_used: number
  daily_limit: number
  per_15min_used: number
  per_15min_limit: number
  next_15min_reset: string
  daily_reset: string
}

interface EnrichmentStatus {
  total_activities: number
  strava_activities: number
  enriched_activities: number
  pending_activities: number
  enrichment_percentage: number
  quota_status: StravaQuotaStatus
  can_enrich_more: boolean
}

interface ActivityStreams {
  activity_id: string
  streams_data: Record<string, any>
  laps_data: Record<string, any>[]
}

interface EnrichResult {
  message: string
  activity_id?: string
  has_streams?: boolean
  has_laps?: boolean
  enriched_count?: number
  failed_count?: number
  quota_status: StravaQuotaStatus
}

interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}

interface GetActivitiesParams {
  page?: number
  per_page?: number
  activity_type?: string
  date_from?: string
}

// ============ DONNÉES ENRICHIES (activity_detail.db) ============

export interface EnrichedActivity {
  activity_id: number
  name: string
  sport_type: string  // Type corrigé (RacketSport, Workout, etc.)
  distance_m: number
  moving_time_s: number
  elapsed_time_s: number
  elev_gain_m: number
  start_date_utc: string
  visibility: string
  private: boolean
  avg_speed_m_s: number
  max_speed_m_s: number
  avg_heartrate_bpm: number
  max_heartrate_bpm: number
  calories_kcal: number
  description: string
}

export interface EnrichedActivityStats {
  total_activities: number
  total_distance_km: number
  total_time_hours: number
  activities_by_sport_type: Record<string, number>
  distance_by_sport_type: Record<string, number>
  time_by_sport_type: Record<string, number>
  activities_by_month: Record<string, number>
  average_pace_by_sport: Record<string, number>
}

export type ApiError = Error & { response?: { data?: { detail?: string }; status?: number } }

class ActivityService {
  private api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
      'Content-Type': 'application/json',
    },
    withCredentials: true,
  })

  async getActivities(params: GetActivitiesParams = {}): Promise<PaginatedResponse<Activity>> {
    const response = await this.api.get('/activities', { params })
    return response.data
  }

  async getAllActivities(activityType?: string, dateFrom?: string): Promise<Activity[]> {
    const allItems: Activity[] = []
    let page = 1
    const perPage = 200
    let totalPages = 1
    do {
      const params: GetActivitiesParams = { page, per_page: perPage }
      if (activityType) params.activity_type = activityType
      if (dateFrom) params.date_from = dateFrom
      const data = await this.getActivities(params)
      allItems.push(...data.items)
      totalPages = data.pages
      page++
    } while (page <= totalPages)
    return allItems
  }

  async getActivity(id: string): Promise<Activity> {
    const response = await this.api.get(`/activities/${id}`)
    return response.data
  }

  async getActivityStats(periodDays: number = 30): Promise<ActivityStats> {
    const response = await this.api.get('/activities/stats', {
      params: { period_days: periodDays }
    })
    return response.data
  }

  async syncStravaActivities(daysBack: number = 30): Promise<{ 
    message: string; 
    total_activities_fetched: number;
    new_activities_saved: number;
    athlete_id: number;
    period: string;
  }> {
    const response = await this.api.post('/sync/strava', null, {
      params: { days_back: daysBack }
    })
    return response.data
  }

  // ============ DONNÉES DÉTAILLÉES STRAVA ============

  async getStravaQuotaStatus(): Promise<StravaQuotaStatus> {
    const response = await this.api.get('/strava/quota')
    return response.data
  }

  async getEnrichmentStatus(): Promise<EnrichmentStatus> {
    const response = await this.api.get('/activities/enrichment-status')
    return response.data
  }

  async enrichSingleActivity(activityId: string): Promise<EnrichResult> {
    const response = await this.api.post(`/activities/${activityId}/enrich`)
    return response.data
  }

  async enrichBatchActivities(maxActivities: number = 10): Promise<EnrichResult> {
    const response = await this.api.post('/activities/enrich-batch', null, {
      params: { max_activities: maxActivities }
    })
    return response.data
  }

  async getActivityStreams(activityId: string): Promise<ActivityStreams> {
    const response = await this.api.get(`/activities/${activityId}/streams`)
    return response.data
  }

  async startAutoEnrichment(): Promise<{ message: string; activities_added_to_queue: number }> {
    const response = await this.api.post('/activities/auto-enrich/start')
    return response.data
  }

  async prioritizeActivity(activityId: string): Promise<{ message: string; activity_id: string }> {
    const response = await this.api.post(`/activities/${activityId}/prioritize`)
    return response.data
  }

  async getEnrichedActivities(params: GetActivitiesParams = {}): Promise<PaginatedResponse<EnrichedActivity>> {
    const response = await this.api.get('/activities/enriched', { params })
    return response.data
  }

  async getAllEnrichedActivities(sportType?: string, dateFrom?: string): Promise<EnrichedActivity[]> {
    const allItems: EnrichedActivity[] = []
    let page = 1
    const perPage = 200
    let totalPages = 1
    do {
      const params: GetActivitiesParams & { sport_type?: string } = { page, per_page: perPage }
      if (sportType) params.sport_type = sportType
      if (dateFrom) params.date_from = dateFrom
      const data = await this.getEnrichedActivities(params)
      allItems.push(...data.items)
      totalPages = data.pages
      page++
    } while (page <= totalPages)
    return allItems
  }

  async getEnrichedActivityStats(periodDays: number = 30): Promise<EnrichedActivityStats> {
    const response = await this.api.get('/activities/enriched/stats', {
      params: { period_days: periodDays }
    })
    return response.data
  }

  async getEnrichedActivity(id: number): Promise<EnrichedActivity> {
    const response = await this.api.get(`/activities/enriched/${id}`)
    return response.data
  }

  async getEnrichedActivityStreams(activityId: number): Promise<{
    activity_id: number;
    streams: {
      heartrate?: number[];
      time?: number[];
      distance?: number[];
      altitude?: number[];
      velocity_smooth?: number[];
      cadence?: number[];
      [key: string]: number[] | undefined;
    };
  }> {
    const response = await this.api.get(`/activities/enriched/${activityId}/streams`)
    return response.data
  }
}

export const activityService = new ActivityService() 