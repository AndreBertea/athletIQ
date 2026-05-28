import { fetchFunctionBlob, invokeFunction, supabase } from '@/lib/supabase';

interface ApiResponse<T> {
  data: T;
}

interface ApiOptions {
  params?: object;
  headers?: Record<string, unknown>;
  responseType?: 'blob' | string;
}

type DbRow = Record<string, any>;

class ApiError extends Error {
  response: { status: number; data: { detail: string } };

  constructor(message: string, status = 400) {
    super(message);
    this.response = { status, data: { detail: message } };
  }
}

function response<T>(data: T): ApiResponse<T> {
  return { data };
}

async function currentUserId(): Promise<string> {
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) throw new ApiError('Session Supabase requise.', 401);
  return data.user.id;
}

function parseUrl(url: string, params?: object): { path: string; params: Record<string, unknown> } {
  const parsed = new URL(url, 'http://agon.local');
  const merged: Record<string, unknown> = {};
  parsed.searchParams.forEach((value, key) => {
    merged[key] = value;
  });
  return { path: parsed.pathname, params: { ...merged, ...((params ?? {}) as Record<string, unknown>) } };
}

function asNumber(value: unknown, fallback: number): number {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function todayLocalDate(now = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

function daysAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString();
}

function mapActivity(row: DbRow): DbRow {
  return {
    ...row,
    activity_id: row.id,
    sport_type: row.activity_type_override ?? row.sport_type ?? row.activity_type ?? 'Run',
    distance_m: row.distance_m ?? 0,
    moving_time_s: row.moving_time_s ?? 0,
    elapsed_time_s: row.elapsed_time_s ?? row.moving_time_s ?? 0,
    elev_gain_m: row.elev_gain_m ?? 0,
    avg_speed_m_s: row.avg_speed_m_s ?? 0,
    max_speed_m_s: row.max_speed_m_s ?? 0,
    avg_heartrate_bpm: row.avg_heartrate_bpm ?? 0,
    max_heartrate_bpm: row.max_heartrate_bpm ?? 0,
    calories_kcal: row.calories_kcal ?? 0,
    visibility: row.visibility ?? 'private',
    private: row.private ?? false,
    description: row.description ?? '',
  };
}

function mapBasicActivity(row: DbRow): DbRow {
  const enriched = mapActivity(row);
  return {
    ...enriched,
    activity_type: enriched.sport_type,
    start_date: row.start_date_utc,
    distance: row.distance_m ?? 0,
    moving_time: row.moving_time_s ?? 0,
    elapsed_time: row.elapsed_time_s ?? row.moving_time_s ?? 0,
    total_elevation_gain: row.elev_gain_m ?? 0,
    average_speed: row.avg_speed_m_s ?? null,
    max_speed: row.max_speed_m_s ?? null,
    average_heartrate: row.avg_heartrate_bpm ?? null,
    max_heartrate: row.max_heartrate_bpm ?? null,
    average_cadence: row.avg_cadence ?? null,
    calories: row.calories_kcal ?? null,
  };
}

async function selectActivities(params: Record<string, unknown> = {}): Promise<DbRow[]> {
  const userId = await currentUserId();
  let query = supabase
    .from('activities')
    .select('*')
    .eq('user_id', userId)
    .order('start_date_utc', { ascending: false });

  if (params.date_from) query = query.gte('start_date_utc', String(params.date_from));
  if (params.sport_type && params.sport_type !== 'all') {
    query = query.eq('sport_type', String(params.sport_type));
  }

  const { data, error } = await query.limit(asNumber(params.limit, 5000));
  if (error) throw error;
  return (data ?? []).map(mapActivity);
}

function buildEnrichedStats(rows: DbRow[]): DbRow {
  const bySport: Record<string, number> = {};
  const distanceBySport: Record<string, number> = {};
  const timeBySport: Record<string, number> = {};
  const paceBySport: Record<string, number[]> = {};

  for (const activity of rows) {
    const sport = String(activity.sport_type ?? 'Run');
    const distanceKm = Number(activity.distance_m ?? 0) / 1000;
    const hours = Number(activity.moving_time_s ?? 0) / 3600;
    bySport[sport] = (bySport[sport] ?? 0) + 1;
    distanceBySport[sport] = (distanceBySport[sport] ?? 0) + distanceKm;
    timeBySport[sport] = (timeBySport[sport] ?? 0) + hours;
    if (distanceKm > 0 && activity.moving_time_s) {
      paceBySport[sport] = [...(paceBySport[sport] ?? []), Number(activity.moving_time_s) / 60 / distanceKm];
    }
  }

  const averagePaceBySport = Object.fromEntries(
    Object.entries(paceBySport).map(([sport, values]) => [
      sport,
      values.reduce((total, value) => total + value, 0) / values.length,
    ]),
  );

  return {
    total_activities: rows.length,
    total_distance_km: rows.reduce((total, row) => total + Number(row.distance_m ?? 0), 0) / 1000,
    total_time_hours: rows.reduce((total, row) => total + Number(row.moving_time_s ?? 0), 0) / 3600,
    activities_by_sport_type: bySport,
    distance_by_sport_type: distanceBySport,
    time_by_sport_type: timeBySport,
    average_pace_by_sport: averagePaceBySport,
  };
}

async function downloadJson(bucket: string, path?: string | null): Promise<unknown | null> {
  if (!path) return null;
  const { data, error } = await supabase.storage.from(bucket).download(path);
  if (error || !data) return null;
  const text = await data.text();
  return JSON.parse(text);
}

async function getCheckinToday(): Promise<DbRow | null> {
  const userId = await currentUserId();
  const { data, error } = await supabase
    .from('daily_checkins')
    .select('*')
    .eq('user_id', userId)
    .eq('entry_date', todayLocalDate())
    .maybeSingle();
  if (error) throw error;
  return data ?? null;
}

async function getCheckinHistory(days = 30): Promise<DbRow[]> {
  const userId = await currentUserId();
  const since = todayLocalDate(new Date(Date.now() - days * 24 * 60 * 60 * 1000));
  const { data, error } = await supabase
    .from('daily_checkins')
    .select('*')
    .eq('user_id', userId)
    .gte('entry_date', since)
    .order('entry_date', { ascending: false });
  if (error) throw error;
  return data ?? [];
}

function computeReadinessScore(today: DbRow | null, history: DbRow[]): DbRow {
  const daysRecorded = history.length;
  if (!today) return { phase: 'no_entries', days_recorded: daysRecorded, days_required: 14, today: null };
  const raw = [today.wellbeing, today.sleep_quality, today.legs, today.motivation]
    .map((value) => Number(value))
    .filter(Number.isFinite);
  const score = raw.length > 0 ? (raw.reduce((total, value) => total + value, 0) / raw.length - 1) * 25 : null;
  return {
    phase: daysRecorded >= 14 ? 'stable' : 'calibration',
    days_recorded: daysRecorded,
    days_required: 14,
    score_0_100: score,
    today,
    insight: daysRecorded >= 14 ? 'Score calculé depuis Supabase.' : 'Calibration en cours.',
  };
}

async function safeStatus(provider: 'strava' | 'garmin'): Promise<DbRow> {
  const { data, error } = await supabase.rpc('get_external_auth_status', { provider_name: provider });
  if (error) return { connected: false };
  const first = Array.isArray(data) ? data[0] : data;
  if (!first) return { connected: false };
  return { ...first, connected: true };
}

async function getWeatherStatus(): Promise<DbRow> {
  const userId = await currentUserId();
  const [{ count: total }, { count: weather }] = await Promise.all([
    supabase.from('activities').select('id', { count: 'exact', head: true }).eq('user_id', userId),
    supabase.from('activity_weather').select('id', { count: 'exact', head: true }).eq('user_id', userId),
  ]);
  return {
    total_activities: total ?? 0,
    eligible_weather_activities: total ?? 0,
    with_weather: weather ?? 0,
    pending_weather: Math.max((total ?? 0) - (weather ?? 0), 0),
  };
}

function isMissingRelationError(error: unknown): boolean {
  return typeof error === 'object'
    && error !== null
    && 'code' in error
    && (error as { code?: string }).code === '42P01';
}

function mapStoredGpxAttachment(row: DbRow): DbRow {
  return {
    id: row.id,
    route_id: row.route_id,
    name: row.name,
    filename: row.filename,
    mime_type: row.mime_type,
    kind: row.kind,
    created_at: row.created_at,
  };
}

function mapGpxFileAttachment(route: DbRow): DbRow | null {
  if (!route.gpx_storage_path) return null;
  return {
    id: 'gpx-file',
    route_id: route.id,
    name: 'GPX',
    filename: route.filename,
    mime_type: 'application/gpx+xml',
    kind: 'gpx',
    created_at: route.created_at,
  };
}

async function get<T = any>(url: string, options: ApiOptions = {}): Promise<ApiResponse<T>> {
  const { path, params } = parseUrl(url, options.params);
  const userId = await currentUserId();

  if (path === '/auth/me') {
    const { data: auth } = await supabase.auth.getUser();
    const { data: profile } = await supabase.from('profiles').select('*').eq('id', userId).maybeSingle();
    return response({ id: userId, email: auth.user?.email ?? profile?.email, full_name: profile?.full_name ?? '', created_at: profile?.created_at } as T);
  }

  if (path === '/checkin/today') return response(await getCheckinToday() as T);
  if (path === '/checkin/history') return response(await getCheckinHistory(asNumber(params.days, 30)) as T);
  if (path === '/checkin/score') return response(computeReadinessScore(await getCheckinToday(), await getCheckinHistory(60)) as T);

  if (path === '/activities') {
    const page = Math.max(asNumber(params.page, 1), 1);
    const perPage = Math.max(asNumber(params.per_page, 30), 1);
    const queryParams = { ...params };
    if (params.activity_type) queryParams.sport_type = params.activity_type;
    const all = await selectActivities(queryParams);
    const start = (page - 1) * perPage;
    return response({
      items: all.slice(start, start + perPage).map(mapBasicActivity),
      total: all.length,
      page,
      per_page: perPage,
      pages: Math.max(Math.ceil(all.length / perPage), 1),
    } as T);
  }

  if (path === '/activities/enrichment-status') {
    const rows = await selectActivities();
    return response({
      total_activities: rows.length,
      strava_activities: rows.filter((row) => row.has_strava).length,
      enriched_activities: rows.filter((row) => row.has_streams).length,
      pending_activities: rows.filter((row) => !row.has_streams).length,
      enrichment_percentage: rows.length ? Math.round(rows.filter((row) => row.has_streams).length / rows.length * 100) : 0,
    } as T);
  }

  if (path === '/activities/enriched') {
    const page = Math.max(asNumber(params.page, 1), 1);
    const perPage = Math.max(asNumber(params.per_page, 30), 1);
    const all = await selectActivities(params);
    const start = (page - 1) * perPage;
    return response({
      items: all.slice(start, start + perPage),
      total: all.length,
      page,
      per_page: perPage,
      pages: Math.max(Math.ceil(all.length / perPage), 1),
    } as T);
  }

  if (path === '/activities/enriched/stats') {
    const periodDays = asNumber(params.period_days, 365);
    return response(buildEnrichedStats(await selectActivities({ date_from: daysAgo(periodDays) })) as T);
  }

  if (path === '/activities/stats') {
    const periodDays = asNumber(params.period_days, 30);
    const rows = await selectActivities({ date_from: daysAgo(periodDays) });
    const enriched = buildEnrichedStats(rows);
    return response({
      total_activities: enriched.total_activities,
      total_distance: enriched.total_distance_km,
      total_time: enriched.total_time_hours * 3600,
      average_pace: enriched.total_distance_km > 0 ? (enriched.total_time_hours * 60) / enriched.total_distance_km : 0,
      activities_by_type: enriched.activities_by_sport_type,
      distance_by_month: {},
    } as T);
  }

  const activityDetail = path.match(/^\/activities\/enriched\/([^/]+)$/);
  if (activityDetail) {
    const { data, error } = await supabase
      .from('activities')
      .select('*')
      .eq('user_id', userId)
      .eq('id', activityDetail[1])
      .single();
    if (error) throw error;
    return response(mapActivity(data) as T);
  }

  const activityBasicDetail = path.match(/^\/activities\/([^/]+)$/);
  if (activityBasicDetail && !path.includes('/streams')) {
    const { data, error } = await supabase
      .from('activities')
      .select('*')
      .eq('user_id', userId)
      .eq('id', activityBasicDetail[1])
      .single();
    if (error) throw error;
    return response(mapBasicActivity(data) as T);
  }

  const activityStreams = path.match(/^\/activities\/enriched\/([^/]+)\/streams$/);
  const activityBasicStreams = path.match(/^\/activities\/([^/]+)\/streams$/);
  if (activityStreams || activityBasicStreams) {
    const activityId = activityStreams?.[1] ?? activityBasicStreams?.[1];
    const { data, error } = await supabase
      .from('activities')
      .select('id,raw_streams_path,raw_laps_path')
      .eq('user_id', userId)
      .eq('id', activityId)
      .single();
    if (error) throw error;
    const streams = await downloadJson('activity-raw', data.raw_streams_path);
    const laps = await downloadJson('activity-raw', data.raw_laps_path);
    return response({ activity_id: data.id, streams, streams_data: streams, laps_data: laps ?? [] } as T);
  }

  if (path === '/weather/status') return response(await getWeatherStatus() as T);

  const weather = path.match(/^\/weather\/([^/]+)$/);
  if (weather) {
    const { data, error } = await supabase
      .from('activity_weather')
      .select('*')
      .eq('user_id', userId)
      .eq('activity_id', weather[1])
      .maybeSingle();
    if (error) throw error;
    return response(data as T);
  }

  const fit = path.match(/^\/garmin\/activities\/([^/]+)\/fit-metrics$/);
  if (fit) {
    const { data, error } = await supabase
      .from('fit_metrics')
      .select('*')
      .eq('user_id', userId)
      .eq('activity_id', fit[1])
      .maybeSingle();
    if (error) throw error;
    return response(data as T);
  }

  const segments = path.match(/^\/segments\/([^/]+)$/);
  if (segments) {
    const { data, error } = await supabase
      .from('segments')
      .select('*, segment_features(*)')
      .eq('user_id', userId)
      .eq('activity_id', segments[1])
      .order('segment_index', { ascending: true });
    if (error) throw error;
    return response({
      activity_id: segments[1],
      segment_count: data?.length ?? 0,
      segments: (data ?? []).map((row) => ({ segment: row, features: row.segment_features?.[0] ?? null })),
    } as T);
  }

  if (path === '/auth/garmin/status') return response(await safeStatus('garmin') as T);
  if (path === '/auth/strava/status') return response(await safeStatus('strava') as T);

  if (path === '/garmin/enrichment-status') {
    const [{ count: total }, { count: enriched }] = await Promise.all([
      supabase.from('activities').select('id', { count: 'exact', head: true }).eq('user_id', userId).eq('has_garmin', true),
      supabase.from('fit_metrics').select('id', { count: 'exact', head: true }).eq('user_id', userId),
    ]);
    return response({
      total_garmin_activities: total ?? 0,
      enriched_activities: enriched ?? 0,
      pending_activities: Math.max((total ?? 0) - (enriched ?? 0), 0),
      enrichment_percentage: total ? Math.round(((enriched ?? 0) / total) * 100) : 0,
    } as T);
  }

  if (path === '/garmin/activities/import-preview') {
    return response(await invokeFunction<T>('garmin-activities-sync', {
      body: { days_back: asNumber(params.days_back, 30), preview: true },
    }));
  }

  if (path === '/garmin/activities/import-status') {
    const rows = await selectActivities({ date_from: daysAgo(asNumber(params.days_back, 30)) });
    const fitDone = rows.filter((row) => row.has_fit_metrics).length;
    const weatherDone = rows.filter((row) => row.has_weather).length;
    return response({
      days_back: asNumber(params.days_back, 30),
      period_started_at: daysAgo(asNumber(params.days_back, 30)),
      total_activities: rows.length,
      fit_total: rows.length,
      fit_done: fitDone,
      fit_pending: Math.max(rows.length - fitDone, 0),
      weather_total: rows.length,
      weather_recorded: weatherDone,
      weather_done: weatherDone,
      weather_pending: Math.max(rows.length - weatherDone, 0),
      weather_without_coordinates: 0,
    } as T);
  }

  if (path === '/garmin/daily') {
    let query = supabase.from('garmin_daily').select('*').eq('user_id', userId).order('date', { ascending: false });
    if (params.date_from) query = query.gte('date', String(params.date_from));
    if (params.date_to) query = query.lte('date', String(params.date_to));
    const { data, error } = await query;
    if (error) throw error;
    return response((data ?? []) as T);
  }

  if (path === '/training-load') {
    let query = supabase.from('training_load').select('*').eq('user_id', userId).order('date', { ascending: true });
    if (params.date_from) query = query.gte('date', String(params.date_from));
    if (params.date_to) query = query.lte('date', String(params.date_to));
    const { data, error } = await query;
    if (error) throw error;
    return response((data ?? []) as T);
  }

  if (path === '/user/me/athletic-profile') {
    const { data, error } = await supabase.from('athletic_profiles').select('*').eq('user_id', userId).maybeSingle();
    if (error) throw error;
    return response(data as T);
  }

  if (path === '/gpx-routes') {
    const { data, error } = await supabase
      .from('gpx_routes')
      .select('*')
      .or(`user_id.eq.${userId},is_public.eq.true`)
      .order('created_at', { ascending: false });
    if (error) throw error;

    const routeIds = (data ?? []).map((route) => route.id).filter(Boolean);
    const attachmentCounts = new Map<string, number>();
    if (routeIds.length > 0) {
      const { data: attachments, error: attachmentError } = await supabase
        .from('gpx_route_attachments')
        .select('route_id')
        .in('route_id', routeIds);
      if (attachmentError && !isMissingRelationError(attachmentError)) throw attachmentError;
      for (const attachment of attachments ?? []) {
        attachmentCounts.set(attachment.route_id, (attachmentCounts.get(attachment.route_id) ?? 0) + 1);
      }
    }

    return response((data ?? []).map((route) => ({
      ...route,
      owned_by_user: route.user_id === userId,
      attachment_count: (route.gpx_storage_path ? 1 : 0) + (attachmentCounts.get(route.id) ?? 0),
    })) as T);
  }

  const gpxRoute = path.match(/^\/gpx-routes\/([^/]+)$/);
  if (gpxRoute) {
    const { data, error } = await supabase
      .from('gpx_routes')
      .select('*')
      .eq('id', gpxRoute[1])
      .or(`user_id.eq.${userId},is_public.eq.true`)
      .single();
    if (error) throw error;
    const { data: storedAttachments, error: attachmentError } = await supabase
      .from('gpx_route_attachments')
      .select('*')
      .eq('route_id', data.id)
      .order('created_at', { ascending: true });
    if (attachmentError && !isMissingRelationError(attachmentError)) throw attachmentError;
    const attachments = [
      mapGpxFileAttachment(data),
      ...((storedAttachments ?? []).map(mapStoredGpxAttachment)),
    ].filter(Boolean);

    return response({
      ...data,
      owned_by_user: data.user_id === userId,
      attachments,
    } as T);
  }

  const gpxSettings = path.match(/^\/gpx-routes\/([^/]+)\/settings$/);
  if (gpxSettings) {
    const { data, error } = await supabase.from('gpx_route_settings').select('*').eq('user_id', userId).eq('route_id', gpxSettings[1]).maybeSingle();
    if (error) throw error;
    return response((data ?? {
      route_id: gpxSettings[1],
      preferred_engine: 'v3',
      analysis_mode: 'auto',
      effort_mode: 'steady',
      ravito_mode: 'auto',
      weather_mode: 'manual',
      custom_ravitos: [],
    }) as T);
  }

  const gpxAttachment = path.match(/^\/gpx-routes\/([^/]+)\/attachments\/([^/]+)$/);
  if (gpxAttachment && options.responseType === 'blob') {
    const { data: route, error } = await supabase
      .from('gpx_routes')
      .select('id,gpx_storage_path')
      .eq('id', gpxAttachment[1])
      .or(`user_id.eq.${userId},is_public.eq.true`)
      .single();
    if (error) throw error;

    let storagePath = route.gpx_storage_path;
    if (gpxAttachment[2] !== 'gpx-file') {
      const { data: attachment, error: attachmentError } = await supabase
        .from('gpx_route_attachments')
        .select('storage_path')
        .eq('route_id', route.id)
        .eq('id', gpxAttachment[2])
        .single();
      if (attachmentError) throw attachmentError;
      storagePath = attachment.storage_path;
    }

    if (!storagePath) throw new ApiError('Pièce jointe introuvable.', 404);
    const { data: blob, error: downloadError } = await supabase.storage.from('gpx-files').download(storagePath);
    if (downloadError || !blob) throw downloadError ?? new ApiError('Fichier GPX introuvable.', 404);
    return response(blob as T);
  }

  if (path === '/prediction/saved') {
    const { data, error } = await supabase.from('race_predictions').select('*').eq('user_id', userId).order('created_at', { ascending: false });
    if (error) throw error;
    return response({ items: data ?? [] } as T);
  }

  if (path === '/prediction/comparisons' || path === '/prediction/references' || path === '/prediction/reference-candidates') {
    return response({ items: [] } as T);
  }

  if (path === '/data/export' && options.responseType === 'blob') {
    return response(await fetchFunctionBlob('data-export') as T);
  }

  throw new ApiError(`Endpoint Supabase non migré: GET ${path}`, 501);
}

async function post<T = any>(url: string, body?: any, options: ApiOptions = {}): Promise<ApiResponse<T>> {
  const { path, params } = parseUrl(url, options.params);
  const userId = await currentUserId();

  if (path === '/checkin') {
    const payload = { ...body, user_id: userId, entry_date: body?.entry_date ?? todayLocalDate(), source: 'manual', client_origin: 'pwa' };
    const { data, error } = await supabase.from('daily_checkins').upsert(payload, { onConflict: 'user_id,entry_date' }).select('*').single();
    if (error) throw error;
    return response(data as T);
  }

  if (path === '/weather/enrich') {
    return response(await invokeFunction<T>('weather-enrich', { body: { max_activities: params.max_activities ?? 25 } }));
  }

  const activityEnrich = path.match(/^\/activities\/([^/]+)\/enrich$/);
  if (activityEnrich) {
    return response({ message: 'Enrichissement détaillé Strava déplacé vers Edge Functions Supabase.', activity_id: activityEnrich[1] } as T);
  }

  if (path === '/activities/enrich-batch' || path === '/activities/auto-enrich/start') {
    return response({ message: 'Enrichissement batch reporté au job Supabase.', enriched_count: 0, failed_count: 0 } as T);
  }

  const prioritize = path.match(/^\/activities\/([^/]+)\/prioritize$/);
  if (prioritize) return response({ activity_id: prioritize[1], prioritized: true } as T);

  if (path === '/activities/auto-correct') return response({ corrections: [] } as T);
  if (path === '/activities/apply-corrections') return response({ applied: 0 } as T);

  const segmentProcess = path.match(/^\/segments\/process\/([^/]+)$/);
  if (segmentProcess) return response({ activity_id: segmentProcess[1], segment_count: 0, segments: [] } as T);

  const singleWeather = path.match(/^\/weather\/([^/]+)\/enrich$/);
  if (singleWeather) {
    await invokeFunction('weather-enrich', { body: { max_activities: 1, activity_id: singleWeather[1] } });
    return await get<T>(`/weather/${singleWeather[1]}`);
  }

  if (path === '/auth/strava/login') return response(await invokeFunction<T>('strava-oauth-start'));
  if (path === '/sync/strava') return response(await invokeFunction<T>('strava-sync', { body: params }));
  if (path === '/sync/garmin') return response(await invokeFunction<T>('garmin-sync', { body: params }));
  if (path === '/sync/garmin/activities') {
    return response(await invokeFunction<T>('garmin-activities-sync', { body: params }));
  }
  if (path === '/garmin/activities/enrich-fit') {
    return response(await invokeFunction<T>('garmin-fit-enrich', { body: params }));
  }

  const singleFit = path.match(/^\/garmin\/activities\/([^/]+)\/enrich-fit$/);
  if (singleFit) {
    return response(await invokeFunction<T>('garmin-fit-enrich', { body: { activity_id: singleFit[1] } }));
  }

  if (path === '/auth/garmin/login') {
    return response(await invokeFunction<T>('garmin-login', { body }));
  }

  if (path === '/user/me/athletic-profile') {
    const { data, error } = await supabase.from('athletic_profiles').upsert({ ...body, user_id: userId }, { onConflict: 'user_id' }).select('*').single();
    if (error) throw error;
    return response(data as T);
  }

  if ((path.includes('/prediction/') && path.endsWith('/gpx')) || path === '/prediction/gpx-pace-prediction') {
    return response(await invokeFunction<T>('predict-race', { body }));
  }

  if (path === '/gpx-routes') {
    const file = body instanceof FormData ? body.get('file') : null;
    if (!(file instanceof File)) throw new ApiError('Fichier GPX requis.', 422);
    const filename = file.name || 'route.gpx';
    const storagePath = `${userId}/routes/${crypto.randomUUID()}-${filename.replace(/[^a-zA-Z0-9._-]+/g, '_')}`;
    const { error: uploadError } = await supabase.storage.from('gpx-files').upload(storagePath, file, { contentType: file.type || 'application/gpx+xml' });
    if (uploadError) throw uploadError;
    const { data, error } = await supabase.from('gpx_routes').insert({
      user_id: userId,
      name: body.get('name') || filename.replace(/\.gpx$/i, ''),
      filename,
      gpx_storage_path: storagePath,
    }).select('*').single();
    if (error) throw error;
    return response({ ...data, owned_by_user: true, attachment_count: 1 } as T);
  }

  if (path === '/prediction/saved') {
    const prediction = body?.prediction ?? body;
    const { data, error } = await supabase.from('race_predictions').insert({
      user_id: userId,
      name: body?.name ?? prediction?.filename ?? 'Prédiction',
      filename: prediction?.filename ?? null,
      engine_version: prediction?.engine_version ?? 'v3_supabase_mvp',
      analysis_mode: prediction?.analysis_mode ?? null,
      ravito_mode: prediction?.ravito_mode ?? null,
      history_start_date: body?.history_start_date ?? prediction?.history_start_date ?? null,
      total_distance_km: prediction?.total_distance_km ?? null,
      total_elevation_gain_m: prediction?.total_elevation_gain_m ?? null,
      moving_time_min: prediction?.moving_time_min ?? null,
      total_pause_min: prediction?.total_pause_min ?? null,
      total_time_min: prediction?.total_time_min ?? null,
      avg_pace: prediction?.avg_pace ?? null,
      prediction_data: prediction,
    }).select('*').single();
    if (error) throw error;
    return response(data as T);
  }

  if (path === '/prediction/comparisons') {
    throw new ApiError('Comparaison de prédiction non migrée dans le MVP Supabase.', 501);
  }

  if (path === '/prediction/reference-candidates/detect') return response({ items: [], detected_count: 0 } as T);

  throw new ApiError(`Endpoint Supabase non migré: POST ${path}`, 501);
}

async function put<T = any>(url: string, body?: any): Promise<ApiResponse<T>> {
  const { path } = parseUrl(url);
  const userId = await currentUserId();

  if (path === '/user/me/athletic-profile') {
    const { data, error } = await supabase.from('athletic_profiles').upsert({ ...body, user_id: userId }, { onConflict: 'user_id' }).select('*').single();
    if (error) throw error;
    return response(data as T);
  }

  const activityType = path.match(/^\/activities\/([^/]+)\/type$/);
  if (activityType) {
    const nextType = body instanceof FormData
      ? body.get('activity_type') ?? body.get('sport_type')
      : body?.activity_type ?? body?.sport_type;
    const { data, error } = await supabase
      .from('activities')
      .update({ activity_type_override: nextType, sport_type: nextType })
      .eq('user_id', userId)
      .eq('id', activityType[1])
      .select('*')
      .single();
    if (error) throw error;
    return response(mapBasicActivity(data) as T);
  }

  const gpxSettings = path.match(/^\/gpx-routes\/([^/]+)\/settings$/);
  if (gpxSettings) {
    const { data, error } = await supabase.from('gpx_route_settings').upsert({
      ...body,
      user_id: userId,
      route_id: gpxSettings[1],
    }, { onConflict: 'user_id,route_id' }).select('*').single();
    if (error) throw error;
    return response(data as T);
  }

  const candidate = path.match(/^\/prediction\/reference-candidates\/([^/]+)\/resolve$/);
  if (candidate) return response({ id: candidate[1], ...body } as T);

  throw new ApiError(`Endpoint Supabase non migré: PUT ${path}`, 501);
}

async function del<T = any>(url: string): Promise<ApiResponse<T>> {
  const { path } = parseUrl(url);
  const userId = await currentUserId();

  if (path === '/auth/garmin/disconnect') {
    await supabase.rpc('disconnect_external_auth', { provider_name: 'garmin' });
    return response({ message: 'Garmin déconnecté.' } as T);
  }

  const gpxRoute = path.match(/^\/gpx-routes\/([^/]+)$/);
  if (gpxRoute) {
    await supabase.from('gpx_routes').delete().eq('user_id', userId).eq('id', gpxRoute[1]);
    return response(undefined as T);
  }

  const saved = path.match(/^\/prediction\/saved\/([^/]+)$/);
  if (saved) {
    await supabase.from('race_predictions').delete().eq('user_id', userId).eq('id', saved[1]);
    return response({ deleted: true, id: saved[1] } as T);
  }

  if (path === '/data/all') {
    await Promise.all([
      supabase.from('activities').delete().eq('user_id', userId),
      supabase.from('garmin_daily').delete().eq('user_id', userId),
      supabase.from('training_load').delete().eq('user_id', userId),
      supabase.from('daily_checkins').delete().eq('user_id', userId),
      supabase.from('race_predictions').delete().eq('user_id', userId),
      supabase.from('gpx_route_attachments').delete().eq('user_id', userId),
      supabase.from('gpx_routes').delete().eq('user_id', userId),
    ]);
    return response({ deleted: true } as T);
  }

  if (path === '/account') return response(await invokeFunction<T>('delete-account', { method: 'DELETE' }));

  throw new ApiError(`Endpoint Supabase non migré: DELETE ${path}`, 501);
}

export const api = {
  get,
  post,
  put,
  patch: put,
  delete: del,
};

export default api;
