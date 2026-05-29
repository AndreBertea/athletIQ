import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
// @deno-types="https://esm.sh/jszip@3.10.1/index.d.ts"
import JSZip from "https://esm.sh/jszip@3.10.1?target=deno";
// fit-file-parser does not publish Deno types through esm.sh.
// deno-lint-ignore ban-ts-comment
// @ts-ignore
import FitParser from "https://esm.sh/fit-file-parser@3.0.1?target=deno";
import type { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";
import { errorResponse, handleCors, jsonResponse } from "../_shared/cors.ts";
import { loadGarminClient } from "../_shared/garmin.ts";
import { requireUser } from "../_shared/supabase.ts";

type Row = Record<string, unknown>;

const SEMICIRCLE_TO_DEG = 180 / (2 ** 31);

serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;
  if (req.method !== "POST") return errorResponse("Method not allowed", 405);

  try {
    const { user, serviceClient } = await requireUser(req);
    const body = await req.json().catch(() => ({}));
    const maxActivities = Math.max(1, Math.min(Number(body.max_activities ?? 1), 5));
    const activityId = body.activity_id ? String(body.activity_id) : null;
    const { client } = await loadGarminClient(serviceClient, user.id);

    let query = serviceClient
      .from("activities")
      .select("id,garmin_activity_id,name,start_date_utc")
      .eq("user_id", user.id)
      .not("garmin_activity_id", "is", null)
      .order("start_date_utc", { ascending: false });
    if (activityId) query = query.eq("id", activityId);
    else query = query.limit(maxActivities);

    const { data: candidateRows, error: candidateError } = await query;
    if (candidateError) throw candidateError;

    const candidates = await filterWithoutFitMetrics(serviceClient, candidateRows ?? [], activityId != null);
    let enriched = 0;
    let errors = 0;

    const errorSamples: string[] = [];
    for (const activity of candidates.slice(0, maxActivities)) {
      try {
        const result = await enrichOne(serviceClient, client, user.id, activity);
        if (result.fit_metrics_stored) enriched += 1;
        else {
          errors += 1;
          const msg = `activity ${activity.id} (garmin ${activity.garmin_activity_id}): pas d'octets FIT (download vide ou zip sans .fit)`;
          console.error(`[fit-enrich] ${msg}`);
          if (errorSamples.length < 5) errorSamples.push(msg);
        }
      } catch (e) {
        errors += 1;
        const msg = `activity ${activity.id} (garmin ${activity.garmin_activity_id}): ${e instanceof Error ? e.message : String(e)}`;
        console.error(`[fit-enrich] EXCEPTION ${msg}`);
        if (errorSamples.length < 5) errorSamples.push(msg);
      }
    }

    return jsonResponse({
      enriched,
      errors,
      total: candidates.slice(0, maxActivities).length,
      error_samples: errorSamples,
    });
  } catch (err) {
    if (err instanceof Response) return err;
    return errorResponse(err instanceof Error ? err.message : "Garmin FIT enrich failed", 500);
  }
});

async function filterWithoutFitMetrics(
  serviceClient: SupabaseClient,
  rows: Row[],
  includeExisting: boolean,
): Promise<Row[]> {
  if (rows.length === 0 || includeExisting) return rows;
  const ids = rows.map((row) => String(row.id));
  const { data, error } = await serviceClient
    .from("fit_metrics")
    .select("activity_id")
    .in("activity_id", ids);
  if (error) throw error;
  const done = new Set((data ?? []).map((row) => String(row.activity_id)));
  return rows.filter((row) => !done.has(String(row.id)));
}

async function enrichOne(
  serviceClient: SupabaseClient,
  client: Awaited<ReturnType<typeof loadGarminClient>>["client"],
  userId: string,
  activity: Row,
): Promise<{ fit_metrics_stored: boolean }> {
  const activityId = String(activity.id);
  const garminActivityId = Number(activity.garmin_activity_id);
  if (!Number.isFinite(garminActivityId)) return { fit_metrics_stored: false };

  const raw = await client.download(`/download-service/files/activity/${garminActivityId}`);
  const fitBytes = await extractFitBytes(raw);
  if (!fitBytes.byteLength) return { fit_metrics_stored: false };

  const rawFitPath = `${userId}/fit/${activityId}.fit`;
  await serviceClient.storage.from("activity-raw").upload(rawFitPath, fitBytes, {
    contentType: "application/octet-stream",
    upsert: true,
  });

  const parsed = await parseFit(fitBytes).catch(() => null);
  const detail = await client.connectApi<Row>(`/activity-service/activity/${garminActivityId}`).catch(() => null);
  const records = collectRecords(parsed);
  const sessions = collectSessions(parsed);
  const streams = buildStreams(records);
  const metrics = {
    ...metricsFromRecords(records),
    ...metricsFromSessions(sessions),
    ...metricsFromGarminDetail(detail),
    raw_fit_path: rawFitPath,
    fit_downloaded_at: new Date().toISOString(),
  };

  let rawStreamsPath: string | null = null;
  if (Object.keys(streams).length > 0) {
    rawStreamsPath = `${userId}/activities/${activityId}/streams.json`;
    await serviceClient.storage.from("activity-raw").upload(
      rawStreamsPath,
      JSON.stringify(streams),
      { contentType: "application/json", upsert: true },
    );
  }

  const { error: fitError } = await serviceClient.from("fit_metrics").upsert({
    user_id: userId,
    activity_id: activityId,
    ...metrics,
    updated_at: new Date().toISOString(),
  }, { onConflict: "activity_id" });
  if (fitError) throw fitError;

  const activityPatch: Row = {
    has_fit_metrics: true,
    updated_at: new Date().toISOString(),
  };
  if (rawStreamsPath) {
    activityPatch.has_streams = true;
    activityPatch.raw_streams_path = rawStreamsPath;
  }
  const { error: activityError } = await serviceClient
    .from("activities")
    .update(activityPatch)
    .eq("id", activityId)
    .eq("user_id", userId);
  if (activityError) throw activityError;

  return { fit_metrics_stored: true };
}

async function extractFitBytes(raw: Uint8Array): Promise<Uint8Array> {
  if (raw[0] !== 0x50 || raw[1] !== 0x4b) return raw;
  const zip = await JSZip.loadAsync(raw);
  const fitName = Object.keys(zip.files).find((name) => name.toLowerCase().endsWith(".fit"));
  if (!fitName) return new Uint8Array();
  return await zip.files[fitName].async("uint8array");
}

async function parseFit(fitBytes: Uint8Array): Promise<Row> {
  const parser = new FitParser({
    force: true,
    lengthUnit: "m",
    speedUnit: "m/s",
    temperatureUnit: "celsius",
    elapsedRecordField: true,
    mode: "both",
  });
  return await parser.parseAsync(fitBytes);
}

function collectRecords(parsed: Row | null): Row[] {
  if (!parsed) return [];
  const direct = parsed.records;
  if (Array.isArray(direct)) return direct as Row[];
  const sessions = collectSessions(parsed);
  return sessions.flatMap((session) => {
    const sessionRecords = session.records;
    if (Array.isArray(sessionRecords)) return sessionRecords as Row[];
    const laps = Array.isArray(session.laps) ? session.laps as Row[] : [];
    return laps.flatMap((lap) => Array.isArray(lap.records) ? lap.records as Row[] : []);
  });
}

function collectSessions(parsed: Row | null): Row[] {
  if (!parsed) return [];
  if (Array.isArray(parsed.sessions)) return parsed.sessions as Row[];
  const activity = parsed.activity as Row | undefined;
  if (Array.isArray(activity?.sessions)) return activity.sessions as Row[];
  return [];
}

function buildStreams(records: Row[]): Row {
  if (records.length === 0) return {};
  const start = dateMs(records[0].timestamp);
  const streams: Record<string, { data: unknown[] }> = {};
  const push = (key: string, value: unknown) => {
    if (!streams[key]) streams[key] = { data: [] };
    streams[key].data.push(value ?? null);
  };

  for (const record of records) {
    const time = dateMs(record.timestamp);
    push("time", start != null && time != null ? Math.max(0, (time - start) / 1000) : null);
    push("distance", firstNumber(record.distance));
    push("altitude", firstNumber(record.enhanced_altitude, record.altitude));
    push("heartrate", firstNumber(record.heart_rate, record.heartRate));
    push("cadence", firstNumber(record.cadence, record.running_cadence));
    push("velocity_smooth", firstNumber(record.enhanced_speed, record.speed));
    push("grade_smooth", firstNumber(record.grade));
    push("watts", firstNumber(record.power));
    push("temp", firstNumber(record.temperature));
    push("stance_time", firstNumber(record.stance_time, record.stanceTime));
    push("vertical_oscillation", firstNumber(record.vertical_oscillation, record.verticalOscillation));
    push("step_length", firstNumber(record.step_length, record.stepLength));
    push("vertical_ratio", firstNumber(record.vertical_ratio, record.verticalRatio));

    const lat = semicircleOrDegree(firstNumber(record.position_lat, record.positionLat));
    const lon = semicircleOrDegree(firstNumber(record.position_long, record.positionLong));
    push("latlng", lat != null && lon != null ? [lat, lon] : null);
  }

  return Object.fromEntries(
    Object.entries(streams).filter(([, stream]) => stream.data.some((value) => value != null)),
  );
}

function metricsFromRecords(records: Row[]): Row {
  return compact({
    ground_contact_time_avg: avg(records, "stance_time", "stanceTime"),
    vertical_oscillation_avg: avg(records, "vertical_oscillation", "verticalOscillation"),
    stance_time_balance_avg: avg(records, "stance_time_balance", "stanceTimeBalance"),
    stance_time_percent_avg: avg(records, "stance_time_percent", "stanceTimePercent"),
    step_length_avg: avg(records, "step_length", "stepLength"),
    vertical_ratio_avg: avg(records, "vertical_ratio", "verticalRatio"),
    power_avg: avg(records, "power"),
    record_count: records.length,
  });
}

function metricsFromSessions(sessions: Row[]): Row {
  const session = sessions[0] ?? {};
  return compact({
    aerobic_training_effect: firstNumber(session.total_training_effect, session.totalTrainingEffect),
    anaerobic_training_effect: firstNumber(session.total_anaerobic_training_effect, session.totalAnaerobicTrainingEffect),
    heart_rate_avg: firstNumber(session.avg_heart_rate, session.avgHeartRate),
    heart_rate_max: firstNumber(session.max_heart_rate, session.maxHeartRate),
    speed_avg: firstNumber(session.enhanced_avg_speed, session.avg_speed, session.enhancedAvgSpeed),
    speed_max: firstNumber(session.enhanced_max_speed, session.max_speed, session.enhancedMaxSpeed),
    power_avg: firstNumber(session.avg_power, session.avgPower),
    power_max: firstNumber(session.max_power, session.maxPower),
    normalized_power: firstNumber(session.normalized_power, session.normalizedPower),
    cadence_avg: firstNumber(session.avg_running_cadence, session.avgRunningCadence),
    cadence_max: firstNumber(session.max_running_cadence, session.maxRunningCadence),
    temperature_avg: firstNumber(session.avg_temperature, session.avgTemperature),
    temperature_max: firstNumber(session.max_temperature, session.maxTemperature),
    total_calories: firstNumber(session.total_calories, session.totalCalories),
    total_strides: firstNumber(session.total_strides, session.totalStrides),
    total_ascent: firstNumber(session.total_ascent, session.totalAscent),
    total_descent: firstNumber(session.total_descent, session.totalDescent),
    total_distance: firstNumber(session.total_distance, session.totalDistance),
    total_timer_time: firstNumber(session.total_timer_time, session.totalTimerTime),
    total_elapsed_time: firstNumber(session.total_elapsed_time, session.totalElapsedTime),
  });
}

function metricsFromGarminDetail(detail: Row | null): Row {
  const summary = detail?.summary as Row | undefined;
  if (!summary) return {};
  return compact({
    ground_contact_time_avg: firstNumber(summary.groundContactTime),
    vertical_oscillation_avg: firstNumber(summary.verticalOscillation),
    vertical_ratio_avg: firstNumber(summary.verticalRatio),
    aerobic_training_effect: firstNumber(summary.trainingEffect, summary.aerobicTrainingEffect),
    anaerobic_training_effect: firstNumber(summary.anaerobicTrainingEffect),
    power_avg: firstNumber(summary.averagePower),
    power_max: firstNumber(summary.maxPower),
    normalized_power: firstNumber(summary.normalizedPower),
  });
}

function avg(records: Row[], ...keys: string[]): number | null {
  const values = records
    .map((record) => firstNumber(...keys.map((key) => record[key])))
    .filter((value): value is number => value != null);
  return values.length ? Math.round((values.reduce((total, value) => total + value, 0) / values.length) * 10) / 10 : null;
}

function firstNumber(...values: unknown[]): number | null {
  for (const value of values) {
    const number = Number(value);
    if (Number.isFinite(number)) return number;
  }
  return null;
}

function dateMs(value: unknown): number | null {
  if (value instanceof Date) return value.getTime();
  if (typeof value === "string" || typeof value === "number") {
    const ms = Date.parse(String(value));
    return Number.isFinite(ms) ? ms : null;
  }
  return null;
}

function semicircleOrDegree(value: number | null): number | null {
  if (value == null) return null;
  return Math.abs(value) > 1000 ? value * SEMICIRCLE_TO_DEG : value;
}

function compact(row: Row): Row {
  return Object.fromEntries(Object.entries(row).filter(([, value]) => value != null));
}
