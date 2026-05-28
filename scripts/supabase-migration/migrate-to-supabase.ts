import "dotenv/config";
import { randomUUID } from "node:crypto";
import { Buffer } from "node:buffer";
import process from "node:process";
import { Client } from "pg";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

type LegacyRow = Record<string, unknown>;
type UserMap = Map<string, string>;

const env = {
  legacyUrl: mustEnv("DATABASE_URL_LEGACY"),
  supabaseUrl: mustEnv("SUPABASE_URL"),
  serviceRoleKey: mustEnv("SUPABASE_SERVICE_ROLE_KEY"),
  defaultPassword: process.env.SUPABASE_MIGRATION_DEFAULT_PASSWORD || randomPassword(),
  userIdMapJson: process.env.SUPABASE_USER_ID_MAP_JSON || "{}",
  sendResetPassword: process.env.SEND_RESET_PASSWORD === "true",
  legacyTokenMode: process.env.LEGACY_TOKEN_MODE || "metadata",
};

const legacy = new Client({ connectionString: env.legacyUrl });
const supabase = createClient(env.supabaseUrl, env.serviceRoleKey, {
  auth: { autoRefreshToken: false, persistSession: false },
});

const report: {
  users: { source: number; target: number; mapped: number; created: number };
  tables: Record<string, { source: number; target: number; errors: number }>;
  storage: { files: number; bytes: number };
  errors: string[];
} = {
  users: { source: 0, target: 0, mapped: 0, created: 0 },
  tables: {},
  storage: { files: 0, bytes: 0 },
  errors: [],
};

async function main(): Promise<void> {
  await legacy.connect();
  try {
    const manualMap = parseUserMap(env.userIdMapJson);
    const userMap = await migrateUsers(manualMap);

    await migrateActivities(userMap);
    await migrateSimpleTable("activityweather", "activity_weather", userMap, mapActivityWeather);
    await migrateSimpleTable("garmindaily", "garmin_daily", userMap, mapGarminDaily);
    await migrateSimpleTable("fitmetrics", "fit_metrics", userMap, mapFitMetrics);
    await migrateSimpleTable("segment", "segments", userMap, mapSegment);
    await migrateSimpleTable("segmentfeatures", "segment_features", userMap, mapSegmentFeatures);
    await migrateSimpleTable("trainingload", "training_load", userMap, mapTrainingLoad);
    await migrateSimpleTable("dailycheckin", "daily_checkins", userMap, mapDailyCheckin);
    await migrateSimpleTable("athleticprofile", "athletic_profiles", userMap, mapAthleticProfile);
    await migrateSimpleTable("referencetest", "reference_tests", userMap, mapReferenceTest);
    await migrateSimpleTable("gpxroute", "gpx_routes", userMap, mapGpxRoute);
    await migrateSimpleTable("gpxrouteusersettings", "gpx_route_settings", userMap, mapGpxRouteSettings);
    await migrateSimpleTable("raceprediction", "race_predictions", userMap, mapRacePrediction);
    await migrateExternalAuth(userMap);

    await verifyNoOrphans();
    printReport();
  } finally {
    await legacy.end();
  }
}

async function migrateUsers(manualMap: UserMap): Promise<UserMap> {
  const users = await legacySelect("user");
  report.users.source = users.length;
  const userMap = new Map(manualMap);

  for (const row of users) {
    const legacyId = stringValue(row.id);
    if (!legacyId) continue;
    const email = stringValue(row.email);
    if (!email) {
      report.errors.push(`User ${legacyId} skipped: missing email`);
      continue;
    }

    if (userMap.has(legacyId)) {
      await upsertProfile(userMap.get(legacyId)!, row);
      report.users.mapped += 1;
      continue;
    }

    const existing = await findAuthUserByEmail(email);
    if (existing) {
      userMap.set(legacyId, existing.id);
      await upsertProfile(existing.id, row);
      report.users.mapped += 1;
      continue;
    }

    const { data, error } = await supabase.auth.admin.createUser({
      email,
      password: env.defaultPassword,
      email_confirm: true,
      user_metadata: { full_name: stringValue(row.full_name) ?? "" },
    });
    if (error || !data.user) {
      report.errors.push(`User ${email} create failed: ${error?.message ?? "unknown"}`);
      continue;
    }

    userMap.set(legacyId, data.user.id);
    await upsertProfile(data.user.id, row);
    if (env.sendResetPassword) {
      await supabase.auth.admin.generateLink({ type: "recovery", email });
    }
    report.users.created += 1;
  }

  report.users.target = userMap.size;
  return userMap;
}

async function migrateActivities(userMap: UserMap): Promise<void> {
  const table = "activity";
  const rows = await legacySelect(table);
  initTableReport("activities", rows.length);
  const tableReport = tableReportFor("activities");

  for (const row of rows) {
    try {
      const legacyUserId = stringValue(row.user_id);
      const userId = legacyUserId ? userMap.get(legacyUserId) : undefined;
      if (!userId) throw new Error(`missing user map for ${legacyUserId}`);

      const legacyActivityId = stringValue(row.id) ?? randomUUID();
      const streamsPath = await uploadJsonIfPresent(
        "activity-raw",
        `${userId}/activities/${legacyActivityId}/streams.json`,
        row.streams_data,
      );
      const lapsPath = await uploadJsonIfPresent(
        "activity-raw",
        `${userId}/activities/${legacyActivityId}/laps.json`,
        row.laps_data,
      );

      await upsert("activities", {
        id: legacyActivityId,
        user_id: userId,
        legacy_id: legacyActivityId,
        source: row.source ?? "unknown",
        strava_id: nullableNumber(row.strava_id),
        garmin_activity_id: nullableNumber(row.garmin_activity_id),
        name: row.name ?? "Activité",
        sport_type: row.activity_type_override ?? row.activity_type ?? "Run",
        activity_type: row.activity_type ?? null,
        activity_type_override: row.activity_type_override ?? null,
        start_date_utc: row.start_date ?? null,
        timezone: row.timezone ?? null,
        location_city: row.location_city ?? null,
        location_country: row.location_country ?? null,
        distance_m: nullableNumber(row.distance),
        moving_time_s: nullableNumber(row.moving_time),
        elapsed_time_s: nullableNumber(row.elapsed_time),
        elev_gain_m: nullableNumber(row.total_elevation_gain),
        avg_speed_m_s: nullableNumber(row.average_speed),
        max_speed_m_s: nullableNumber(row.max_speed),
        avg_heartrate_bpm: nullableNumber(row.average_heartrate),
        max_heartrate_bpm: nullableNumber(row.max_heartrate),
        avg_cadence: nullableNumber(row.average_cadence),
        calories_kcal: nullableNumber(row.calories),
        description: row.description ?? null,
        summary_polyline: row.summary_polyline ?? null,
        polyline: row.polyline ?? null,
        start_latlng: normalizeJson(row.start_latlng),
        end_latlng: normalizeJson(row.end_latlng),
        has_strava: Boolean(row.strava_id),
        has_garmin: Boolean(row.garmin_activity_id),
        has_streams: Boolean(streamsPath),
        raw_streams_path: streamsPath,
        raw_laps_path: lapsPath,
        raw_summary: stripHeavy(row, ["streams_data", "laps_data"]),
        created_at: row.created_at ?? new Date().toISOString(),
        updated_at: row.updated_at ?? new Date().toISOString(),
      });
      tableReport.target += 1;
    } catch (error) {
      tableReport.errors += 1;
      report.errors.push(`activities:${row.id}: ${message(error)}`);
    }
  }
}

async function migrateSimpleTable(
  source: string,
  target: string,
  userMap: UserMap,
  mapper: (row: LegacyRow, userMap: UserMap) => Promise<LegacyRow | null> | LegacyRow | null,
): Promise<void> {
  const rows = await legacySelect(source);
  initTableReport(target, rows.length);
  const tableReport = tableReportFor(target);

  for (const row of rows) {
    try {
      const mapped = await mapper(row, userMap);
      if (!mapped) continue;
      await upsert(target, mapped);
      tableReport.target += 1;
    } catch (error) {
      tableReport.errors += 1;
      report.errors.push(`${target}:${row.id}: ${message(error)}`);
    }
  }
}

async function mapActivityWeather(row: LegacyRow, userMap: UserMap): Promise<LegacyRow | null> {
  const userId = mapRowUser(row, userMap);
  if (!userId) return null;
  const id = stringValue(row.id) ?? randomUUID();
  const rawWeatherPath = await uploadJsonIfPresent(
    "activity-raw",
    `${userId}/weather/${row.activity_id ?? id}.json`,
    {
      request_params: normalizeJson(row.request_params),
      hourly_units: normalizeJson(row.hourly_units),
      hourly_snapshot: normalizeJson(row.hourly_snapshot),
      timeline_10min: normalizeJson(row.timeline_10min),
    },
  );
  return {
    id,
    user_id: userId,
    activity_id: row.activity_id,
    temperature_c: nullableNumber(row.temperature_c),
    humidity_pct: nullableNumber(row.humidity_pct),
    wind_speed_kmh: nullableNumber(row.wind_speed_kmh),
    wind_direction_deg: nullableNumber(row.wind_direction_deg),
    pressure_hpa: nullableNumber(row.pressure_hpa),
    precipitation_mm: nullableNumber(row.precipitation_mm),
    cloud_cover_pct: nullableNumber(row.cloud_cover_pct),
    weather_code: nullableNumber(row.weather_code),
    sampled_at: row.sampled_at ?? null,
    latitude: nullableNumber(row.latitude),
    longitude: nullableNumber(row.longitude),
    elevation_m: nullableNumber(row.elevation_m),
    source_endpoint: row.source_endpoint ?? null,
    source_url: row.source_url ?? null,
    raw_weather_path: rawWeatherPath,
    created_at: row.created_at ?? new Date().toISOString(),
    updated_at: row.updated_at ?? new Date().toISOString(),
  };
}

function mapGarminDaily(row: LegacyRow, userMap: UserMap): LegacyRow | null {
  const userId = mapRowUser(row, userMap);
  if (!userId) return null;
  return copyWithUser(row, userId, [
    "id",
    "date",
    "hrv_rmssd",
    "training_readiness",
    "sleep_score",
    "sleep_duration_min",
    "deep_sleep_seconds",
    "light_sleep_seconds",
    "rem_sleep_seconds",
    "awake_sleep_seconds",
    "sleep_start_time",
    "sleep_end_time",
    "average_respiration",
    "avg_sleep_stress",
    "resting_hr",
    "stress_score",
    "body_battery_max",
    "body_battery_min",
    "spo2",
    "total_steps",
    "total_kilocalories",
    "active_kilocalories",
    "vo2max_estimated",
    "lactate_threshold_speed_mps",
    "lactate_threshold_hr",
    "race_prediction_5k_seconds",
    "race_prediction_10k_seconds",
    "race_prediction_half_seconds",
    "race_prediction_marathon_seconds",
    "weight_kg",
    "training_status",
    "created_at",
    "updated_at",
  ]);
}

function mapFitMetrics(row: LegacyRow, userMap: UserMap): LegacyRow | null {
  const userId = mapRowUser(row, userMap);
  if (!userId) return null;
  return copyWithUser(row, userId, Object.keys(row).filter((key) => key !== "user_id"));
}

function mapSegment(row: LegacyRow, userMap: UserMap): LegacyRow | null {
  const userId = mapRowUser(row, userMap);
  if (!userId) return null;
  return copyWithUser(row, userId, [
    "id",
    "activity_id",
    "segment_index",
    "distance_m",
    "elapsed_time_s",
    "avg_grade_percent",
    "elevation_gain_m",
    "elevation_loss_m",
    "altitude_m",
    "avg_hr",
    "avg_cadence",
    "lat",
    "lon",
    "pace_min_per_km",
    "created_at",
    "updated_at",
  ]);
}

function mapSegmentFeatures(row: LegacyRow, userMap: UserMap): LegacyRow | null {
  const userId = mapRowUser(row, userMap);
  if (!userId) return null;
  return copyWithUser(row, userId, Object.keys(row).filter((key) => key !== "user_id"));
}

function mapTrainingLoad(row: LegacyRow, userMap: UserMap): LegacyRow | null {
  const userId = mapRowUser(row, userMap);
  return userId ? copyWithUser(row, userId, Object.keys(row).filter((key) => key !== "user_id")) : null;
}

function mapDailyCheckin(row: LegacyRow, userMap: UserMap): LegacyRow | null {
  const userId = mapRowUser(row, userMap);
  return userId ? copyWithUser(row, userId, Object.keys(row).filter((key) => key !== "user_id")) : null;
}

function mapAthleticProfile(row: LegacyRow, userMap: UserMap): LegacyRow | null {
  const userId = mapRowUser(row, userMap);
  return userId ? copyWithUser(row, userId, Object.keys(row).filter((key) => key !== "user_id")) : null;
}

function mapReferenceTest(row: LegacyRow, userMap: UserMap): LegacyRow | null {
  const userId = mapRowUser(row, userMap);
  return userId ? copyWithUser(row, userId, Object.keys(row).filter((key) => key !== "user_id")) : null;
}

async function mapGpxRoute(row: LegacyRow, userMap: UserMap): Promise<LegacyRow | null> {
  const userId = mapRowUser(row, userMap);
  if (!userId) return null;
  const id = stringValue(row.id) ?? randomUUID();
  const gpxContent = row.gpx_content ?? row.gpx_text ?? row.content;
  const gpxStoragePath = await uploadTextIfPresent(
    "gpx-files",
    `${userId}/routes/${id}-${stringValue(row.filename) ?? "route.gpx"}`,
    gpxContent,
  );
  return {
    id,
    user_id: userId,
    name: row.name ?? row.filename ?? "Route GPX",
    filename: row.filename ?? "route.gpx",
    is_public: row.is_public ?? false,
    distance_km: nullableNumber(row.distance_km),
    elevation_gain_m: nullableNumber(row.elevation_gain_m),
    gpx_storage_path: gpxStoragePath ?? row.gpx_storage_path ?? null,
    metadata: stripHeavy(row, ["gpx_content", "gpx_text", "content"]),
    created_at: row.created_at ?? new Date().toISOString(),
    updated_at: row.updated_at ?? new Date().toISOString(),
  };
}

function mapGpxRouteSettings(row: LegacyRow, userMap: UserMap): LegacyRow | null {
  const userId = mapRowUser(row, userMap);
  return userId ? copyWithUser(row, userId, Object.keys(row).filter((key) => key !== "user_id")) : null;
}

function mapRacePrediction(row: LegacyRow, userMap: UserMap): LegacyRow | null {
  const userId = mapRowUser(row, userMap);
  if (!userId) return null;
  return {
    id: row.id ?? randomUUID(),
    user_id: userId,
    route_id: row.route_id ?? null,
    name: row.name ?? row.filename ?? "Prédiction",
    filename: row.filename ?? null,
    engine_version: row.engine_version ?? "legacy_python",
    analysis_mode: row.analysis_mode ?? null,
    ravito_mode: row.ravito_mode ?? null,
    history_start_date: row.history_start_date ?? null,
    total_distance_km: nullableNumber(row.total_distance_km),
    total_elevation_gain_m: nullableNumber(row.total_elevation_gain_m),
    moving_time_min: nullableNumber(row.moving_time_min),
    total_pause_min: nullableNumber(row.total_pause_min),
    total_time_min: nullableNumber(row.total_time_min),
    avg_pace: nullableNumber(row.avg_pace),
    prediction_data: normalizeJson(row.prediction_data) ?? stripHeavy(row, []),
    created_at: row.created_at ?? new Date().toISOString(),
    updated_at: row.updated_at ?? new Date().toISOString(),
  };
}

async function migrateExternalAuth(userMap: UserMap): Promise<void> {
  initTableReport("external_auth_tokens", 0);
  const tableReport = tableReportFor("external_auth_tokens");
  await migrateProvider("stravaauth", "strava", userMap, (row) => ({
    provider_user_id: stringValue(row.strava_athlete_id),
    scopes: stringValue(row.scope)?.split(",") ?? [],
    access_token_encrypted: env.legacyTokenMode === "copy" ? row.access_token_encrypted : null,
    refresh_token_encrypted: env.legacyTokenMode === "copy" ? row.refresh_token_encrypted : null,
    expires_at: row.expires_at ?? null,
    token_payload: env.legacyTokenMode === "copy"
      ? { legacy_token_mode: "copy" }
      : { legacy_token_mode: "metadata", reconnect_required: true },
  }));

  await migrateProvider("garminauth", "garmin", userMap, (row) => ({
    display_name: row.garmin_display_name ?? null,
    access_token_encrypted: env.legacyTokenMode === "copy" ? row.oauth_token_encrypted : null,
    refresh_token_encrypted: null,
    last_sync_at: row.last_sync_at ?? null,
    token_payload: env.legacyTokenMode === "copy"
      ? { legacy_token_mode: "copy" }
      : { legacy_token_mode: "metadata", reconnect_required: true },
  }));
}

async function migrateProvider(
  sourceTable: string,
  provider: string,
  userMap: UserMap,
  mapProvider: (row: LegacyRow) => LegacyRow,
): Promise<void> {
  const rows = await legacySelect(sourceTable);
  const tableReport = tableReportFor("external_auth_tokens");
  tableReport.source += rows.length;
  for (const row of rows) {
    try {
      const userId = mapRowUser(row, userMap);
      if (!userId) continue;
      await upsert("external_auth_tokens", {
        user_id: userId,
        provider,
        ...mapProvider(row),
        created_at: row.created_at ?? new Date().toISOString(),
        updated_at: row.updated_at ?? new Date().toISOString(),
      }, "user_id,provider");
      tableReport.target += 1;
    } catch (error) {
      tableReport.errors += 1;
      report.errors.push(`external_auth_tokens:${sourceTable}:${row.id}: ${message(error)}`);
    }
  }
}

async function legacySelect(table: string): Promise<LegacyRow[]> {
  const exists = await legacyTableExists(table);
  if (!exists) return [];
  const result = await legacy.query(`select * from "${table}"`);
  return result.rows;
}

async function legacyTableExists(table: string): Promise<boolean> {
  const result = await legacy.query(
    "select exists (select 1 from information_schema.tables where table_schema='public' and table_name=$1)",
    [table],
  );
  return Boolean(result.rows[0]?.exists);
}

async function upsert(table: string, row: LegacyRow, onConflict = "id"): Promise<void> {
  const { error } = await supabase.from(table).upsert(row, { onConflict });
  if (error) throw error;
}

async function upsertProfile(id: string, row: LegacyRow): Promise<void> {
  await upsert("profiles", {
    id,
    email: row.email,
    full_name: row.full_name ?? "",
    display_name: row.full_name ?? stringValue(row.email)?.split("@")[0] ?? "Athlète",
    created_at: row.created_at ?? new Date().toISOString(),
    updated_at: new Date().toISOString(),
  });
}

async function findAuthUserByEmail(email: string): Promise<{ id: string } | null> {
  let page = 1;
  while (page <= 20) {
    const { data, error } = await supabase.auth.admin.listUsers({ page, perPage: 1000 });
    if (error) throw error;
    const found = data.users.find((user) => user.email?.toLowerCase() === email.toLowerCase());
    if (found) return { id: found.id };
    if (data.users.length < 1000) break;
    page += 1;
  }
  return null;
}

async function uploadJsonIfPresent(
  bucket: string,
  path: string,
  value: unknown,
): Promise<string | null> {
  const normalized = normalizeJson(value);
  if (normalized == null || normalized === "null") return null;
  return uploadTextIfPresent(bucket, path, JSON.stringify(normalized));
}

async function uploadTextIfPresent(
  bucket: string,
  path: string,
  value: unknown,
): Promise<string | null> {
  if (value == null || value === "null") return null;
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (text.trim().length === 0 || text.trim() === "null") return null;
  const bytes = Buffer.byteLength(text);
  const { error } = await supabase.storage.from(bucket).upload(path, text, {
    contentType: path.endsWith(".gpx") ? "application/gpx+xml" : "application/json",
    upsert: true,
  });
  if (error) throw error;
  report.storage.files += 1;
  report.storage.bytes += bytes;
  return path;
}

async function verifyNoOrphans(): Promise<void> {
  const { data, error } = await supabase
    .from("activities")
    .select("id,user_id")
    .limit(1);
  if (error) throw error;
  if (!data) report.errors.push("activities verification returned no data");
}

function initTableReport(table: string, sourceCount: number): void {
  if (!report.tables[table]) {
    report.tables[table] = { source: 0, target: 0, errors: 0 };
  }
  report.tables[table].source += sourceCount;
}

function tableReportFor(table: string): { source: number; target: number; errors: number } {
  initTableReport(table, 0);
  return report.tables[table]!;
}

function mapRowUser(row: LegacyRow, userMap: UserMap): string | null {
  const legacyUserId = stringValue(row.user_id);
  return legacyUserId ? userMap.get(legacyUserId) ?? null : null;
}

function copyWithUser(row: LegacyRow, userId: string, keys: string[]): LegacyRow {
  const out: LegacyRow = { user_id: userId };
  for (const key of keys) {
    if (key in row && key !== "user_id") out[key] = normalizeJson(row[key]);
  }
  return out;
}

function normalizeJson(value: unknown): unknown {
  if (typeof value !== "string") return value ?? null;
  const trimmed = value.trim();
  if (!trimmed || trimmed === "null") return null;
  if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return value;
    }
  }
  return value;
}

function stripHeavy(row: LegacyRow, heavyKeys: string[]): LegacyRow {
  const out: LegacyRow = {};
  for (const [key, value] of Object.entries(row)) {
    if (!heavyKeys.includes(key)) out[key] = normalizeJson(value);
  }
  return out;
}

function parseUserMap(json: string): UserMap {
  const parsed = JSON.parse(json) as Record<string, string>;
  return new Map(Object.entries(parsed));
}

function nullableNumber(value: unknown): number | null {
  if (value == null) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function stringValue(value: unknown): string | null {
  if (value == null) return null;
  return String(value);
}

function randomPassword(): string {
  return `${randomUUID()}aA1!`;
}

function mustEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing ${name}`);
  return value;
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : JSON.stringify(error);
}

function printReport(): void {
  console.log(JSON.stringify(report, null, 2));
  if (report.errors.length > 0) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
