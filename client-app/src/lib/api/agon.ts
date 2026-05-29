import { api } from '@/lib/api';

export interface PaginatedResponse<T> {
  items: T[];
  total?: number;
  page?: number;
  pages?: number;
  per_page?: number;
}

export interface EnrichedActivity {
  id?: string;
  activity_id: string | number;
  source?: string;
  strava_id?: number | null;
  garmin_activity_id?: number | null;
  name: string;
  sport_type: string;
  start_date_utc: string;
  distance_m?: number | null;
  moving_time_s?: number | null;
  elapsed_time_s?: number | null;
  elev_gain_m?: number | null;
  avg_heartrate_bpm?: number | null;
  max_heartrate_bpm?: number | null;
  avg_cadence?: number | null;
  calories_kcal?: number | null;
  avg_speed_m_s?: number | null;
  max_speed_m_s?: number | null;
  avg_speed_mps?: number | null;
  max_speed_mps?: number | null;
  description?: string | null;
  location_city?: string | null;
  location_country?: string | null;
  has_strava?: boolean;
  has_garmin?: boolean;
  has_fit_metrics?: boolean;
  has_streams?: boolean;
  has_weather?: boolean;
  summary_polyline?: string | null;
  polyline?: string | null;
  start_latlng?: [number, number] | null;
  end_latlng?: [number, number] | null;
  [key: string]: unknown;
}

export interface EnrichedActivityStats {
  total_activities: number;
  total_distance_km: number;
  total_time_hours: number;
  activities_by_sport_type?: Record<string, number>;
  distance_by_sport_type?: Record<string, number>;
  time_by_sport_type?: Record<string, number>;
  average_pace_by_sport?: Record<string, number>;
}

export interface ActivityStats {
  total_activities: number;
  total_distance: number;
  total_time: number;
  average_pace: number;
  activities_by_type: Record<string, number>;
  distance_by_month: Record<string, number>;
}

export interface GarminDailyEntry {
  date: string;
  hrv_rmssd: number | null;
  training_readiness: number | null;
  sleep_score: number | null;
  sleep_duration_min: number | null;
  deep_sleep_seconds: number | null;
  light_sleep_seconds: number | null;
  rem_sleep_seconds: number | null;
  awake_sleep_seconds: number | null;
  sleep_start_time: string | null;
  sleep_end_time: string | null;
  average_respiration: number | null;
  avg_sleep_stress: number | null;
  resting_hr: number | null;
  stress_score: number | null;
  body_battery_max: number | null;
  spo2: number | null;
  total_steps: number | null;
  total_kilocalories: number | null;
  active_kilocalories: number | null;
  vo2max_estimated: number | null;
  lactate_threshold_speed_mps: number | null;
  lactate_threshold_hr: number | null;
  race_prediction_5k_seconds: number | null;
  race_prediction_10k_seconds: number | null;
  race_prediction_half_seconds: number | null;
  race_prediction_marathon_seconds: number | null;
  weight_kg: number | null;
  body_battery_min: number | null;
  training_status: string | null;
}

export interface TrainingLoadEntry {
  id: string;
  user_id: string;
  date: string;
  ctl_42d: number | null;
  atl_7d: number | null;
  tsb: number | null;
  rhr_delta_7d: number | null;
  edwards_trimp_daily: number | null;
  ctl_42d_edwards: number | null;
  atl_7d_edwards: number | null;
  tsb_edwards: number | null;
  created_at: string;
  updated_at: string;
}

export interface ActivityStreamsResponse {
  activity_id: string | number;
  streams?: {
    time?: number[];
    distance?: number[];
    altitude?: number[];
    heartrate?: number[];
    velocity_smooth?: number[];
    cadence?: number[];
    latlng?: [number, number][];
    [key: string]: unknown;
  };
  laps_data?: unknown[];
}

export interface ActivityWeather {
  id: string;
  activity_id: string;
  temperature_c: number | null;
  humidity_pct: number | null;
  wind_speed_kmh: number | null;
  wind_direction_deg: number | null;
  pressure_hpa: number | null;
  precipitation_mm: number | null;
  cloud_cover_pct: number | null;
  weather_code: number | null;
  sampled_at?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  elevation_m?: number | null;
  hourly_snapshot?: Record<string, unknown> | null;
}

export interface FitMetrics {
  id: string;
  activity_id: string;
  ground_contact_time_avg: number | null;
  vertical_oscillation_avg: number | null;
  stance_time_balance_avg: number | null;
  stance_time_percent_avg: number | null;
  step_length_avg: number | null;
  vertical_ratio_avg: number | null;
  power_avg: number | null;
  power_max: number | null;
  normalized_power: number | null;
  cadence_avg: number | null;
  cadence_max: number | null;
  heart_rate_avg: number | null;
  heart_rate_max: number | null;
  speed_avg: number | null;
  speed_max: number | null;
  temperature_avg: number | null;
  temperature_max: number | null;
  aerobic_training_effect: number | null;
  anaerobic_training_effect: number | null;
  total_calories: number | null;
  total_strides: number | null;
  total_ascent: number | null;
  total_descent: number | null;
  total_distance: number | null;
  total_timer_time: number | null;
  total_elapsed_time: number | null;
  record_count: number | null;
  fit_downloaded_at: string | null;
}

export interface SegmentData {
  id: string;
  activity_id: string;
  segment_index: number;
  distance_m: number;
  elapsed_time_s: number;
  avg_grade_percent: number | null;
  elevation_gain_m: number | null;
  elevation_loss_m: number | null;
  altitude_m: number | null;
  avg_hr: number | null;
  avg_cadence: number | null;
  lat: number | null;
  lon: number | null;
  pace_min_per_km: number | null;
}

export interface SegmentFeaturesData {
  id: string;
  segment_id: string;
  activity_id: string;
  cumulative_distance_km: number;
  elapsed_time_min: number;
  cumulative_elev_gain_m: number | null;
  cumulative_elev_loss_m: number | null;
  race_completion_pct: number | null;
  intensity_proxy: number | null;
  minetti_cost: number | null;
  cardiac_drift: number | null;
  cadence_decay: number | null;
  grade_variability: number | null;
  efficiency_factor: number | null;
}

export interface SegmentWithFeatures {
  segment: SegmentData;
  features: SegmentFeaturesData | null;
}

export interface SegmentResponse {
  activity_id: string;
  segment_count: number;
  segments: SegmentWithFeatures[];
}

export interface GarminStatus {
  connected: boolean;
  email?: string | null;
  last_sync?: string | null;
  [key: string]: unknown;
}

export interface GarminEnrichmentStatus {
  total_garmin_activities?: number;
  enriched_activities?: number;
  pending_activities?: number;
  [key: string]: unknown;
}

export interface WeatherStatus {
  total_activities?: number;
  with_coordinates?: number;
  eligible_weather_activities?: number;
  with_weather?: number;
  with_weather_payload?: number;
  with_weather_timeline?: number;
  pending_weather?: number;
  pending_weather_payload?: number;
  pending_weather_timeline?: number;
  archive_required_activities?: number;
  forecast_supported_activities?: number;
  [key: string]: unknown;
}

export interface WeatherEnrichmentResult {
  processed: number;
  skipped: number;
  errors: number;
  remaining?: number;
  archive_required?: number;
}

export interface GarminImportPreview {
  days_back: number;
  period_started_at: string;
  total_activities: number;
  existing_activities: number;
  missing_activities: number;
}

export interface GarminImportStatus {
  days_back: number;
  period_started_at: string;
  total_activities: number;
  fit_total: number;
  fit_done: number;
  fit_pending: number;
  weather_total: number;
  weather_recorded: number;
  weather_done: number;
  weather_pending: number;
  weather_without_coordinates: number;
}

export interface AthleticProfile {
  id?: string;
  user_id?: string;
  sex?: 'male' | 'female' | 'unspecified' | null;
  birth_date?: string | null;
  height_cm?: number | null;
  weight_kg?: number | null;
  activity_level?: 'sedentary' | 'light' | 'moderate' | 'active' | 'very_active' | null;
  experience_level?: 'beginner' | 'regular' | 'competitor' | 'elite' | null;
  practice_dominant?: 'road' | 'trail' | 'mixed' | null;
  weekly_volume_band?: 'under_20km' | '20_40km' | '40_60km' | '60_80km' | 'over_80km' | null;
}

export interface RacePredictionResult {
  engine_version?: string;
  filename?: string;
  analysis_mode?: string;
  ravito_mode?: string;
  history_start_date?: string;
  total_distance_km?: number;
  total_elevation_gain_m?: number;
  moving_time_min?: number;
  moving_time_formatted?: string;
  total_pause_min?: number;
  total_pause_formatted?: string;
  total_time_min?: number;
  total_time_formatted?: string;
  avg_pace?: number;
  avg_moving_pace?: number;
  summary?: Record<string, unknown>;
  uncertainty?: Record<string, unknown>;
  calibration?: Record<string, unknown>;
  environment?: Record<string, unknown>;
  fatigue?: Record<string, unknown>;
  ravitos?: { points?: unknown[]; total_pause_min?: number };
  ravito_points?: unknown[];
  segments?: Array<Record<string, unknown>>;
  warnings?: string[];
  athlete_model?: Record<string, unknown>;
  hybrid_model?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface SavedRacePrediction {
  id: string;
  name: string;
  filename?: string | null;
  engine_version?: string | null;
  analysis_mode?: string | null;
  ravito_mode?: string | null;
  history_start_date?: string | null;
  total_distance_km?: number | null;
  total_elevation_gain_m?: number | null;
  moving_time_min?: number | null;
  total_pause_min?: number | null;
  total_time_min?: number | null;
  avg_pace?: number | null;
  prediction_data: RacePredictionResult;
  created_at: string;
  updated_at: string;
}

export interface SavedRacePredictionComparison {
  id: string;
  name: string;
  prediction_id: string;
  activity_id?: string | null;
  prediction_name?: string | null;
  activity_name?: string | null;
  comparison_data: Record<string, unknown>;
  total_delta_min?: number | null;
  moving_delta_min?: number | null;
  pause_delta_min?: number | null;
  avg_abs_segment_delta_min?: number | null;
  comparable_distance_km?: number | null;
  created_at: string;
  updated_at: string;
}

export interface RaceValidationReference {
  id: string;
  activity_id: string;
  category: string;
  notes?: string | null;
  potential_gain_min_low?: number | null;
  potential_gain_min_high?: number | null;
}

export interface RaceReferenceCandidate {
  id: string;
  activity_id: string;
  suggested_category: string;
  confidence: 'low' | 'medium' | 'high' | string;
  score: number;
  status: 'pending' | 'accepted' | 'rejected' | string;
  reasons?: {
    positive?: string[];
    negative?: string[];
    anomalies?: string[];
    [key: string]: unknown;
  };
  features?: Record<string, unknown>;
  notes?: string | null;
  potential_gain_min_low?: number | null;
  potential_gain_min_high?: number | null;
  activity?: {
    id: string;
    name: string;
    start_date?: string | null;
    distance_km?: number | null;
    moving_time_min?: number | null;
    elevation_gain_m?: number | null;
  };
  created_at: string;
  updated_at: string;
}

export interface GpxRouteSummary {
  id: string;
  user_id?: string | null;
  name: string;
  filename: string;
  is_public: boolean;
  distance_km?: number | null;
  elevation_gain_m?: number | null;
  owned_by_user: boolean;
  attachment_count: number;
  created_at: string;
}

export interface GpxAttachmentRead {
  id: string;
  route_id: string;
  name: string;
  filename: string;
  mime_type: string;
  kind: string;
  created_at: string;
}

export interface GpxRouteDetail {
  id: string;
  user_id?: string | null;
  name: string;
  filename: string;
  is_public: boolean;
  distance_km?: number | null;
  elevation_gain_m?: number | null;
  owned_by_user: boolean;
  attachments: GpxAttachmentRead[];
  /** Ravitos officiels globaux de la course (BDD, lisibles par tous). */
  official_ravitos?: OfficialRavitoPoint[] | null;
  created_at: string;
  updated_at: string;
}

export interface OfficialRavitoPoint {
  km: number;
  name: string;
  service?: string | null;
}

export interface RouteRavitoPoint {
  km: number;
  name: string;
  pause_min: number;
}

export interface GpxRouteUserSettings {
  id?: string;
  route_id: string;
  preferred_engine: 'v1' | 'v2' | 'v3' | string;
  analysis_mode: 'auto' | 'route' | 'trail' | string;
  effort_mode: 'endurance' | 'steady' | 'aggressive' | string;
  ravito_mode: 'auto' | 'manual' | string;
  weather_mode: 'auto' | 'manual' | string;
  manual_temperature_c?: number | null;
  history_start_date?: string | null;
  race_datetime?: string | null;
  custom_ravitos: RouteRavitoPoint[];
  created_at?: string;
  updated_at?: string;
}

export function oneYearAgoIsoDate(now = new Date()): string {
  const date = new Date(now);
  date.setFullYear(date.getFullYear() - 1);
  return date.toISOString().slice(0, 10);
}

export function activityDisplayId(activity: EnrichedActivity): string {
  return String(activity.id ?? activity.activity_id);
}

export const agonApi = {
  async getEnrichedActivities(params: {
    page?: number;
    per_page?: number;
    date_from?: string;
    sport_type?: string;
  } = {}): Promise<PaginatedResponse<EnrichedActivity>> {
    const { data } = await api.get<PaginatedResponse<EnrichedActivity>>('/activities/enriched', { params });
    return data;
  },

  async getAllEnrichedActivities(params: {
    date_from?: string;
    sport_type?: string;
  } = {}): Promise<EnrichedActivity[]> {
    const items: EnrichedActivity[] = [];
    let page = 1;

    while (true) {
      const queryParams: {
        page: number;
        per_page: number;
        date_from?: string;
        sport_type?: string;
      } = { page, per_page: 200 };

      if (params.date_from) queryParams.date_from = params.date_from;
      if (params.sport_type) queryParams.sport_type = params.sport_type;

      const data = await this.getEnrichedActivities(queryParams);
      // Garde défensive : si le backend renvoie `items: null` (jamais un
      // tableau), un spread direct jette "object null is not iterable".
      if (Array.isArray(data?.items)) items.push(...data.items);
      const totalPages = data?.pages ?? page;
      if (page >= totalPages) break;
      page += 1;
    }

    return items;
  },

  async getEnrichedActivityStats(periodDays = 365): Promise<EnrichedActivityStats> {
    const { data } = await api.get<EnrichedActivityStats>('/activities/enriched/stats', {
      params: { period_days: periodDays },
    });
    return data;
  },

  async getActivityStats(periodDays = 30): Promise<ActivityStats> {
    const { data } = await api.get<ActivityStats>('/activities/stats', {
      params: { period_days: periodDays },
    });
    return data;
  },

  async getEnrichedActivity(id: string | number): Promise<EnrichedActivity> {
    const { data } = await api.get<EnrichedActivity>(`/activities/enriched/${id}`);
    return data;
  },

  async getEnrichedActivityStreams(id: string | number): Promise<ActivityStreamsResponse> {
    const { data } = await api.get<ActivityStreamsResponse>(`/activities/enriched/${id}/streams`);
    return data;
  },

  async getActivityWeather(id: string | number): Promise<ActivityWeather> {
    const { data } = await api.get<ActivityWeather>(`/weather/${id}`);
    return data;
  },

  async enrichActivityWeather(id: string | number): Promise<ActivityWeather> {
    const { data } = await api.post<ActivityWeather>(`/weather/${id}/enrich`);
    return data;
  },

  async getActivityFitMetrics(id: string | number): Promise<FitMetrics> {
    const { data } = await api.get<FitMetrics>(`/garmin/activities/${id}/fit-metrics`);
    return data;
  },

  async getActivitySegments(id: string | number): Promise<SegmentResponse> {
    const { data } = await api.get<SegmentResponse>(`/segments/${id}`);
    return data;
  },

  async getGarminStatus(): Promise<GarminStatus> {
    const { data } = await api.get<GarminStatus>('/auth/garmin/status');
    return data;
  },

  async getGarminDaily(dateFrom?: string, dateTo?: string): Promise<GarminDailyEntry[]> {
    const params: Record<string, string> = {};
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    const { data } = await api.get<GarminDailyEntry[]>('/garmin/daily', { params });
    return data;
  },

  async getTrainingLoad(dateFrom?: string, dateTo?: string): Promise<TrainingLoadEntry[]> {
    const params: Record<string, string> = {};
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    const { data } = await api.get<TrainingLoadEntry[]>('/training-load', { params });
    return data;
  },

  async loginGarmin(
    email: string,
    password: string,
    mfaCode?: string,
  ): Promise<{ message?: string; needs_mfa?: boolean }> {
    const { data } = await api.post<{ message?: string; needs_mfa?: boolean }>('/auth/garmin/login', {
      email,
      password,
      mfa_code: mfaCode || undefined,
    });
    return data;
  },

  async disconnectGarmin(): Promise<{ message?: string }> {
    const { data } = await api.delete<{ message?: string }>('/auth/garmin/disconnect');
    return data;
  },

  async syncGarminDaily(daysBack = 365): Promise<Record<string, unknown>> {
    const chunkSize = 30;
    let daysSynced = 0;
    let errors = 0;
    let totalRequested = 0;
    let lastJobId: unknown = null;

    for (let offset = 0; offset < daysBack; offset += chunkSize) {
      const chunkDays = Math.min(chunkSize, daysBack - offset);
      const { data } = await api.post<Record<string, unknown>>('/sync/garmin', null, {
        params: { days_back: chunkDays, start_offset_days: offset },
      });
      daysSynced += Number(data.days_synced ?? 0);
      errors += Number(data.errors ?? 0);
      totalRequested += Number(data.total_requested ?? chunkDays);
      lastJobId = data.job_id ?? lastJobId;
    }

    return {
      days_synced: daysSynced,
      errors,
      total_requested: totalRequested,
      job_id: lastJobId,
    };
  },

  async syncGarminActivities(daysBack = 365): Promise<Record<string, unknown>> {
    const { data } = await api.post<Record<string, unknown>>('/sync/garmin/activities', null, {
      params: { days_back: daysBack },
    });
    return data;
  },

  async previewGarminImport(daysBack = 365): Promise<GarminImportPreview> {
    const { data } = await api.get<GarminImportPreview>('/garmin/activities/import-preview', {
      params: { days_back: daysBack },
    });
    return data;
  },

  async getGarminImportStatus(daysBack = 365): Promise<GarminImportStatus> {
    const { data } = await api.get<GarminImportStatus>('/garmin/activities/import-status', {
      params: { days_back: daysBack },
    });
    return data;
  },

  async enrichGarminFit(maxActivities = 100): Promise<Record<string, unknown>> {
    const { data } = await api.post<Record<string, unknown>>('/garmin/activities/enrich-fit', null, {
      params: { max_activities: maxActivities },
    });
    return data;
  },

  async getGarminEnrichmentStatus(): Promise<GarminEnrichmentStatus> {
    const { data } = await api.get<GarminEnrichmentStatus>('/garmin/enrichment-status');
    return data;
  },

  async getWeatherStatus(): Promise<WeatherStatus> {
    const { data } = await api.get<WeatherStatus>('/weather/status');
    return data;
  },

  async enrichWeather(
    maxActivities = 100,
    includeHistoricalArchive = true,
    daysBack?: number,
  ): Promise<WeatherEnrichmentResult> {
    const params: {
      max_activities: number;
      include_historical_archive: boolean;
      days_back?: number;
    } = {
      max_activities: maxActivities,
      include_historical_archive: includeHistoricalArchive,
    };
    if (daysBack != null) params.days_back = daysBack;

    const { data } = await api.post<WeatherEnrichmentResult>('/weather/enrich', null, {
      params,
    });
    return data;
  },

  async getAthleticProfile(): Promise<AthleticProfile | null> {
    const { data } = await api.get<AthleticProfile | null>('/user/me/athletic-profile');
    return data ?? null;
  },

  async updateAthleticProfile(payload: Partial<AthleticProfile>): Promise<AthleticProfile> {
    const { data } = await api.put<AthleticProfile>('/user/me/athletic-profile', payload);
    return data;
  },

  async predictGpx(engine: 'v1' | 'v2' | 'v3', formData: FormData): Promise<RacePredictionResult> {
    const endpoint =
      engine === 'v1'
        ? '/prediction/gpx-pace-prediction'
        : engine === 'v2'
          ? '/prediction/v2/gpx'
          : '/prediction/v3/gpx';
    const { data } = await api.post<RacePredictionResult>(endpoint, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  async listGpxRoutes(): Promise<GpxRouteSummary[]> {
    const { data } = await api.get<GpxRouteSummary[]>('/gpx-routes');
    return data;
  },

  async uploadGpxRoute(file: File, name?: string): Promise<GpxRouteSummary> {
    const form = new FormData();
    form.append('file', file);
    if (name) form.append('name', name);
    const { data } = await api.post<GpxRouteSummary>('/gpx-routes', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  async getGpxRoute(id: string): Promise<GpxRouteDetail> {
    const { data } = await api.get<GpxRouteDetail>(`/gpx-routes/${id}`);
    return data;
  },

  async getGpxRouteSettings(id: string): Promise<GpxRouteUserSettings> {
    const { data } = await api.get<GpxRouteUserSettings>(`/gpx-routes/${id}/settings`);
    return data;
  },

  async updateGpxRouteSettings(
    id: string,
    payload: Partial<GpxRouteUserSettings>,
  ): Promise<GpxRouteUserSettings> {
    const { data } = await api.put<GpxRouteUserSettings>(`/gpx-routes/${id}/settings`, payload);
    return data;
  },

  async deleteGpxRoute(id: string): Promise<void> {
    await api.delete(`/gpx-routes/${id}`);
  },

  async getGpxRouteAttachmentBlobUrl(routeId: string, attachmentId: string): Promise<string> {
    const response = await api.get<Blob>(`/gpx-routes/${routeId}/attachments/${attachmentId}`, {
      responseType: 'blob',
    });
    return URL.createObjectURL(response.data);
  },

  async getSavedRacePredictions(): Promise<{ items: SavedRacePrediction[] }> {
    const { data } = await api.get<{ items: SavedRacePrediction[] }>('/prediction/saved');
    return data;
  },

  async saveRacePrediction(payload: {
    name: string;
    prediction: RacePredictionResult;
    history_start_date?: string;
  }): Promise<SavedRacePrediction> {
    const { data } = await api.post<SavedRacePrediction>('/prediction/saved', payload);
    return data;
  },

  async deleteSavedRacePrediction(predictionId: string): Promise<{ deleted: boolean; id: string }> {
    const { data } = await api.delete<{ deleted: boolean; id: string }>(`/prediction/saved/${predictionId}`);
    return data;
  },

  async compareRacePrediction(predictionId: string, activityId: string): Promise<Record<string, unknown>> {
    const { data } = await api.get<Record<string, unknown>>(
      `/prediction/saved/${predictionId}/compare/${activityId}`,
    );
    return data;
  },

  async saveRacePredictionComparison(payload: {
    prediction_id: string;
    activity_id: string;
    name?: string;
  }): Promise<SavedRacePredictionComparison> {
    const { data } = await api.post<SavedRacePredictionComparison>('/prediction/comparisons', payload);
    return data;
  },

  async getSavedRacePredictionComparisons(): Promise<{ items: SavedRacePredictionComparison[] }> {
    const { data } = await api.get<{ items: SavedRacePredictionComparison[] }>('/prediction/comparisons');
    return data;
  },

  async getRaceValidationReferences(): Promise<{ items: RaceValidationReference[] }> {
    const { data } = await api.get<{ items: RaceValidationReference[] }>('/prediction/references');
    return data;
  },

  async getRaceReferenceCandidates(statusFilter = 'pending'): Promise<{ items: RaceReferenceCandidate[] }> {
    const { data } = await api.get<{ items: RaceReferenceCandidate[] }>('/prediction/reference-candidates', {
      params: { status_filter: statusFilter },
    });
    return data;
  },

  async detectRaceReferenceCandidates(payload?: {
    history_start_date?: string;
    limit?: number;
    force?: boolean;
  }): Promise<{ items: RaceReferenceCandidate[]; detected_count: number }> {
    const { data } = await api.post<{ items: RaceReferenceCandidate[]; detected_count: number }>(
      '/prediction/reference-candidates/detect',
      payload ?? {},
    );
    return data;
  },

  async resolveRaceReferenceCandidate(
    candidateId: string,
    payload: {
      action: 'accept' | 'reject';
      category?: string;
      notes?: string;
      potential_gain_min_low?: number | null;
      potential_gain_min_high?: number | null;
    },
  ): Promise<RaceReferenceCandidate> {
    const { data } = await api.put<RaceReferenceCandidate>(
      `/prediction/reference-candidates/${candidateId}/resolve`,
      payload,
    );
    return data;
  },

  async exportUserData(): Promise<Blob> {
    const { data } = await api.get<Blob>('/data/export', { responseType: 'blob' });
    return data;
  },

  async deleteAllUserData(): Promise<Record<string, unknown>> {
    const { data } = await api.delete<Record<string, unknown>>('/data/all');
    return data;
  },

  async deleteAccount(): Promise<Record<string, unknown>> {
    const { data } = await api.delete<Record<string, unknown>>('/account');
    return data;
  },
};
