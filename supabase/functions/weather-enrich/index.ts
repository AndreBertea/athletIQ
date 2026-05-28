import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { errorResponse, handleCors, jsonResponse } from "../_shared/cors.ts";
import { addJobEvent, createJob, updateJob } from "../_shared/jobs.ts";
import { requireUser } from "../_shared/supabase.ts";

interface ActivityRow {
  id: string;
  start_date_utc: string | null;
  start_latlng: [number, number] | null;
  end_latlng: [number, number] | null;
}

function activityCoordinates(activity: ActivityRow): { lat: number; lon: number } | null {
  const value = activity.start_latlng ?? activity.end_latlng;
  if (!Array.isArray(value) || value.length < 2) return null;
  const [lat, lon] = value.map(Number);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  return { lat, lon };
}

function nearestHourlyIndex(hourlyTimes: string[], activityDate: Date): number {
  let best = 0;
  let bestDelta = Number.POSITIVE_INFINITY;
  for (let i = 0; i < hourlyTimes.length; i += 1) {
    const delta = Math.abs(new Date(hourlyTimes[i]).getTime() - activityDate.getTime());
    if (delta < bestDelta) {
      best = i;
      bestDelta = delta;
    }
  }
  return best;
}

serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;
  if (req.method !== "POST") return errorResponse("Method not allowed", 405);

  let jobId: string | null = null;
  try {
    const { user, serviceClient } = await requireUser(req);
    const body = await req.json().catch(() => ({}));
    const maxActivities = Math.min(Number(body.max_activities ?? 25), 100);

    jobId = await createJob(serviceClient, user.id, "weather_enrich", {
      max_activities: maxActivities,
    });

    const { data: activities, error } = await serviceClient
      .from("activities")
      .select("id,start_date_utc,start_latlng,end_latlng")
      .eq("user_id", user.id)
      .eq("has_weather", false)
      .not("start_date_utc", "is", null)
      .order("start_date_utc", { ascending: false })
      .limit(maxActivities);
    if (error) throw error;

    let processed = 0;
    let skipped = 0;
    let errors = 0;
    const baseUrl = Deno.env.get("OPEN_METEO_BASE_URL") ?? "https://api.open-meteo.com/v1/forecast";

    for (const activity of (activities ?? []) as ActivityRow[]) {
      try {
        const coords = activityCoordinates(activity);
        if (!coords || !activity.start_date_utc) {
          skipped += 1;
          continue;
        }

        const date = new Date(activity.start_date_utc);
        const isoDate = date.toISOString().slice(0, 10);
        const url = new URL(baseUrl);
        url.searchParams.set("latitude", String(coords.lat));
        url.searchParams.set("longitude", String(coords.lon));
        url.searchParams.set("start_date", isoDate);
        url.searchParams.set("end_date", isoDate);
        url.searchParams.set(
          "hourly",
          "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,pressure_msl,precipitation,cloud_cover,weather_code",
        );
        url.searchParams.set("timezone", "UTC");

        const response = await fetch(url);
        if (!response.ok) throw new Error(`Open-Meteo ${response.status}`);
        const payload = await response.json();
        const hourly = payload.hourly ?? {};
        const index = nearestHourlyIndex(hourly.time ?? [], date);

        const row = {
          user_id: user.id,
          activity_id: activity.id,
          temperature_c: hourly.temperature_2m?.[index] ?? null,
          humidity_pct: hourly.relative_humidity_2m?.[index] ?? null,
          wind_speed_kmh: hourly.wind_speed_10m?.[index] ?? null,
          wind_direction_deg: hourly.wind_direction_10m?.[index] ?? null,
          pressure_hpa: hourly.pressure_msl?.[index] ?? null,
          precipitation_mm: hourly.precipitation?.[index] ?? null,
          cloud_cover_pct: hourly.cloud_cover?.[index] ?? null,
          weather_code: hourly.weather_code?.[index] ?? null,
          sampled_at: hourly.time?.[index] ? new Date(hourly.time[index]).toISOString() : activity.start_date_utc,
          latitude: coords.lat,
          longitude: coords.lon,
          source_endpoint: baseUrl,
          source_url: url.toString(),
          request_params: Object.fromEntries(url.searchParams.entries()),
          hourly_units: payload.hourly_units ?? null,
          hourly_snapshot: hourly,
        };

        const { error: weatherError } = await serviceClient
          .from("activity_weather")
          .upsert(row, { onConflict: "activity_id" });
        if (weatherError) throw weatherError;

        await serviceClient
          .from("activities")
          .update({ has_weather: true })
          .eq("id", activity.id);

        processed += 1;
      } catch {
        errors += 1;
      }

      const total = Math.max((activities ?? []).length, 1);
      await updateJob(serviceClient, jobId, {
        progress: Math.round(((processed + skipped + errors) / total) * 100),
        stage: "weather",
        message: `${processed} météo enrichies`,
      });
    }

    await addJobEvent(serviceClient, jobId, user.id, "finished", "Enrichissement météo terminé", {
      processed,
      skipped,
      errors,
    });
    await updateJob(serviceClient, jobId, {
      status: errors > 0 && processed === 0 ? "failed" : "succeeded",
      progress: 100,
      stage: "done",
      result: { processed, skipped, errors },
      finished_at: new Date().toISOString(),
    });

    return jsonResponse({ processed, skipped, errors, job_id: jobId });
  } catch (err) {
    if (err instanceof Response) return err;
    return errorResponse(err instanceof Error ? err.message : "Weather enrich failed", 500);
  }
});
