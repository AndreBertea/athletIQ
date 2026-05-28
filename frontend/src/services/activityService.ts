import { api as supabaseApi } from './supabaseApi'

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

export interface LapData {
  distance: number
  moving_time: number
  elapsed_time: number
  total_elevation_gain: number
  average_speed: number
  max_speed: number
  average_cadence?: number
  average_heartrate?: number
  max_heartrate?: number
  start_index: number
  end_index: number
  [key: string]: any
}

interface ActivityStreams {
  activity_id: string
  streams_data: Record<string, any>
  laps_data: LapData[]
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

// ============ RÉSUMÉS CONSOLIDÉS ET DONNÉES DÉTAILLÉES ============

export interface EnrichedActivity {
  id?: string
  activity_id: string | number
  source?: 'strava' | 'garmin' | 'manual' | string
  strava_id?: number
  garmin_activity_id?: number
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
  // Flags sources de données
  has_strava?: boolean
  has_garmin?: boolean
  has_fit_metrics?: boolean
  has_streams?: boolean
  has_weather?: boolean
  // Données GPS
  summary_polyline?: string
  start_latlng?: [number, number]
  end_latlng?: [number, number]
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

export interface SavedRacePrediction {
  id: string
  name: string
  filename?: string
  engine_version?: string
  analysis_mode: string
  ravito_mode: string
  history_start_date?: string | null
  total_distance_km?: number
  total_elevation_gain_m?: number
  moving_time_min?: number
  total_pause_min?: number
  total_time_min?: number
  avg_pace?: number
  prediction_data: Record<string, any>
  created_at: string
  updated_at: string
}

export interface SavedRacePredictionComparison {
  id: string
  name: string
  prediction_id: string
  activity_id?: string | null
  prediction_name?: string | null
  activity_name?: string | null
  comparison_data: Record<string, any>
  total_delta_min?: number | null
  moving_delta_min?: number | null
  pause_delta_min?: number | null
  avg_abs_segment_delta_min?: number | null
  comparable_distance_km?: number | null
  created_at: string
  updated_at: string
}

export interface RaceValidationReference {
  id: string
  activity_id: string
  category: string
  notes?: string | null
  potential_gain_min_low?: number | null
  potential_gain_min_high?: number | null
  created_at: string
  updated_at: string
}

export type ApiError = Error & { response?: { data?: { detail?: string }; status?: number } }

// ============ V2.2 PREDICTOR - PROFIL ATHLETIQUE & TESTS DE REFERENCE ============

export type AthleticSex = 'male' | 'female' | 'unspecified'
export type ActivityLevel = 'sedentary' | 'light' | 'moderate' | 'active' | 'very_active'
export type ExperienceLevel = 'beginner' | 'regular' | 'competitor' | 'elite'
export type PracticeDominant = 'road' | 'trail' | 'mixed'
// Race Predictor V2.3.1 (R4) : alignement avec le backend
// (`backend/app/domain/entities/athletic_profile.py::WeeklyVolumeBand`). Les
// anciennes valeurs frontend (`lt_10km`, `10_30km`, ...) etaient rejetees par
// le PUT /user/me/athletic-profile en 422 silencieusement.
export type WeeklyVolumeBand =
  | 'under_20km'
  | '20_40km'
  | '40_60km'
  | '60_80km'
  | 'over_80km'

export interface AthleticProfile {
  id: string
  user_id: string
  sex?: AthleticSex | null
  birth_date?: string | null
  height_cm?: number | null
  weight_kg?: number | null
  activity_level?: ActivityLevel | null
  experience_level?: ExperienceLevel | null
  practice_dominant?: PracticeDominant | null
  weekly_volume_band?: WeeklyVolumeBand | null
  created_at?: string
  updated_at?: string
}

export type ReferenceTestType = 'road_5k' | 'road_10k' | 'long_steady' | 'hill_climb' | 'vertical_km'
export type ReferenceTestSurface = 'asphalt' | 'gravel' | 'dirt' | 'technical_trail' | 'track'
export type ReferenceTestQuality = 'valid' | 'questionable' | 'invalidated'

export interface ReferenceTest {
  id: string
  user_id?: string
  test_type: ReferenceTestType
  performed_at: string
  duration_seconds: number
  distance_m?: number | null
  elevation_gain_m?: number | null
  temperature_c?: number | null
  surface?: ReferenceTestSurface | null
  conditions_notes?: string | null
  quality_status: ReferenceTestQuality
  created_at?: string
  updated_at?: string
}

export interface CreateReferenceTestPayload {
  test_type: ReferenceTestType
  performed_at: string
  duration_seconds: number
  distance_m?: number | null
  elevation_gain_m?: number | null
  temperature_c?: number | null
  surface?: ReferenceTestSurface | null
  conditions_notes?: string | null
}

export interface V22ParameterDistribution {
  parameter?: string
  mean?: number
  std?: number
  p10?: number
  p50?: number
  p90?: number
  // Backend canonique (V2.3+ via robust_updater) : poids en pourcentage [0,1]
  // exposes dans `posterior_snapshot.breakdown_by_parameter`. Le frontend lit
  // ces cles en priorite et retombe sur les anciennes `prior_weight` /
  // `evidence_weight` pour la retro-compatibilite avec les predictions V2.2
  // archivees.
  prior_weight_pct?: number
  evidence_weight_pct?: number
  prior_weight?: number
  evidence_weight?: number
  evidence_count?: number
  quality_flags?: string[]
}

export interface V22RecommendedEvidence {
  evidence_type?: string
  label?: string
  description?: string
  impact_minutes?: number
  impact_text?: string
  priority?: number
}

export interface V22AthleteModel {
  prior?: Record<string, V22ParameterDistribution>
  posterior?: Record<string, V22ParameterDistribution>
  evidence_summary?: {
    total_observations?: number
    profile_only?: boolean
    has_reference_tests?: boolean
    has_clean_activities?: boolean
    prior_weight_share?: number
    evidence_weight_share?: number
    source_breakdown?: Array<{
      source: string
      label?: string
      count?: number
      weight_share?: number
    }>
    [key: string]: any
  }
  recommended_next_evidence?: V22RecommendedEvidence[]
}

export interface V22EventIntensity {
  capacity_wkg?: number
  sustainable_fraction?: number
  target_power_wkg?: number
  iterations?: Array<{
    iteration?: number
    predicted_duration_min?: number
    sustainable_fraction?: number
    target_power_wkg?: number
  }>
}

export interface V22UncertaintyBlock {
  p10?: number
  p50?: number
  p90?: number
}

export interface V22PredictionResult {
  engine_version?: string
  filename?: string
  summary?: {
    total_time_min?: number
    moving_time_min?: number
    total_pause_min?: number
    avg_moving_pace?: number
    [key: string]: any
  }
  environment?: {
    temperature_c?: number
    temperature_min_c?: number
    temperature_max_c?: number
    weather_source?: string
    weather_mode?: string
    peak_heat_penalty_percent?: number
    heat_penalty_percent?: number
    [key: string]: any
  }
  ravitos?: { points?: any[] } | null
  ravito_points?: any[]
  segments?: any[]
  uncertainty?: {
    total_time?: V22UncertaintyBlock
    moving_time?: V22UncertaintyBlock
    [key: string]: any
  }
  athlete_model?: V22AthleteModel
  event_intensity?: V22EventIntensity
  warnings?: string[]
  calibration?: Record<string, any>
  prediction_data?: Record<string, any>
  [key: string]: any
}

// V2.3 reutilise la meme structure de reponse que V2.2 (minus event_intensity dans le pipeline principal).
// Alias pour minimiser le diff et garder la coherence des composants UI.
export type V23ParameterDistribution = V22ParameterDistribution
export type V23RecommendedEvidence = V22RecommendedEvidence
export type V23AthleteModel = V22AthleteModel
export type V23UncertaintyBlock = V22UncertaintyBlock
export type V23PredictionResult = V22PredictionResult

class ActivityService {
  private api = supabaseApi

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

  async getEnrichedActivity(id: number | string): Promise<EnrichedActivity> {
    const response = await this.api.get(`/activities/enriched/${id}`)
    return response.data
  }

  async getEnrichedActivityStreams(activityId: number | string): Promise<{
    activity_id: number | string;
    streams: {
      heartrate?: number[];
      time?: number[];
      distance?: number[];
      altitude?: number[];
      velocity_smooth?: number[];
      cadence?: number[];
      latlng?: [number, number][];
      [key: string]: number[] | [number, number][] | undefined;
    };
    laps_data?: LapData[];
  }> {
    const response = await this.api.get(`/activities/enriched/${activityId}/streams`)
    return response.data
  }

  async updateActivityType(activityId: string, activityType: string): Promise<any> {
    const formData = new FormData()
    formData.append('activity_type', activityType)
    const response = await this.api.patch(`/activities/${activityId}/type`, formData)
    return response.data
  }

  async autoCorrectActivityTypes(): Promise<any> {
    const response = await this.api.post('/activities/auto-correct')
    return response.data
  }

  async applyCorrections(corrections: Array<{activity_id: string; suggested_type: string}>): Promise<any> {
    const response = await this.api.post('/activities/apply-corrections', {
      corrections: corrections
    })
    return response.data
  }

  async getSavedRacePredictions(): Promise<{ items: SavedRacePrediction[] }> {
    const response = await this.api.get('/prediction/saved')
    return response.data
  }

  async saveRacePrediction(payload: {
    name: string
    prediction: Record<string, any>
    history_start_date?: string
  }): Promise<SavedRacePrediction> {
    const response = await this.api.post('/prediction/saved', payload)
    return response.data
  }

  async predictRaceV2Gpx(formData: FormData): Promise<Record<string, any>> {
    const response = await this.api.post('/prediction/v2/gpx', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  }

  async deleteSavedRacePrediction(predictionId: string): Promise<{ deleted: boolean; id: string }> {
    const response = await this.api.delete(`/prediction/saved/${predictionId}`)
    return response.data
  }

  async compareRacePrediction(predictionId: string, activityId: string): Promise<any> {
    const response = await this.api.get(`/prediction/saved/${predictionId}/compare/${activityId}`)
    return response.data
  }

  async getSavedRacePredictionComparisons(): Promise<{ items: SavedRacePredictionComparison[] }> {
    const response = await this.api.get('/prediction/comparisons')
    return response.data
  }

  async getRaceValidationReferences(): Promise<{ items: RaceValidationReference[] }> {
    const response = await this.api.get('/prediction/references')
    return response.data
  }

  async saveRaceValidationReference(activityId: string, payload: {
    category: string
    notes?: string | null
    potential_gain_min_low?: number | null
    potential_gain_min_high?: number | null
  }): Promise<RaceValidationReference> {
    const response = await this.api.put(`/prediction/references/${activityId}`, payload)
    return response.data
  }

  async saveRacePredictionComparison(payload: {
    prediction_id: string
    activity_id: string
    name?: string
  }): Promise<SavedRacePredictionComparison> {
    const response = await this.api.post('/prediction/comparisons', payload)
    return response.data
  }

  async deleteSavedRacePredictionComparison(comparisonId: string): Promise<{ deleted: boolean; id: string }> {
    const response = await this.api.delete(`/prediction/comparisons/${comparisonId}`)
    return response.data
  }

  // ============ V2.2 PREDICTOR - API ============

  async getAthleticProfile(): Promise<AthleticProfile | null> {
    try {
      const response = await this.api.get('/user/me/athletic-profile')
      return response.data
    } catch (error: any) {
      if (error?.response?.status === 404) {
        return null
      }
      throw error
    }
  }

  async updateAthleticProfile(data: Partial<AthleticProfile>): Promise<AthleticProfile> {
    const response = await this.api.put('/user/me/athletic-profile', data)
    return response.data
  }

  async getReferenceTests(testType?: ReferenceTestType, includeInvalidated: boolean = false): Promise<ReferenceTest[]> {
    const params: Record<string, string | boolean> = { include_invalidated: includeInvalidated }
    if (testType) params.test_type = testType
    const response = await this.api.get('/prediction/reference-tests', { params })
    // Tolerant: accept either {items: []} or [] directly
    const data = response.data
    if (Array.isArray(data)) return data
    if (Array.isArray(data?.items)) return data.items
    return []
  }

  async createReferenceTest(data: CreateReferenceTestPayload): Promise<ReferenceTest> {
    const response = await this.api.post('/prediction/reference-tests', data)
    return response.data
  }

  async updateReferenceTest(id: string, data: Partial<ReferenceTest>): Promise<ReferenceTest> {
    const response = await this.api.patch(`/prediction/reference-tests/${id}`, data)
    return response.data
  }

  async invalidateReferenceTest(id: string): Promise<void> {
    await this.api.delete(`/prediction/reference-tests/${id}`)
  }

  async predictRaceV22Gpx(formData: FormData): Promise<V22PredictionResult> {
    const response = await this.api.post('/prediction/v2.2/gpx', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  }

  async predictRaceV23Gpx(formData: FormData): Promise<V23PredictionResult> {
    const response = await this.api.post('/prediction/v2.3/gpx', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  }

  /**
   * Race Predictor V2.3.1 (R4). Utilise le meme endpoint que V2.3 (/v2.3/gpx),
   * mais le backend etiquette desormais la reponse avec
   * `engine_version = v2_3_1_bayesian`. Toute prediction sauvegardee via
   * `saveRacePrediction` apres cet appel sera donc enregistree sous
   * `engine_version = v2_3_1_bayesian`. Les anciennes predictions stockees
   * avec `v2_3_bayesian` restent lisibles via `getSavedRacePredictions`.
   */
  async predictRaceV231Gpx(formData: FormData): Promise<V23PredictionResult> {
    const response = await this.api.post('/prediction/v2.3/gpx', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  }

  async predictRaceV3Gpx(formData: FormData): Promise<V23PredictionResult> {
    const response = await this.api.post('/prediction/v3/gpx', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  }
}

export const activityService = new ActivityService()
