import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { errorResponse, handleCors, jsonResponse } from "../_shared/cors.ts";
import { requireUser } from "../_shared/supabase.ts";
import {
  assertGpxSize,
  buildRacePrediction,
  parseCustomRavitos,
} from "../_shared/prediction.ts";

type ServiceClient = Awaited<ReturnType<typeof requireUser>>["serviceClient"];

function safeFilename(name: string): string {
  return name.replace(/[^a-zA-Z0-9._-]+/g, "_").slice(0, 120) || "route.gpx";
}

// Resout la reference GPX en chemin Storage (sans telecharger), pour enfiler un job.
// route_id -> chemin de la route ; fichier uploade -> upload + creation de la route.
async function resolveGpxRef(
  serviceClient: ServiceClient,
  userId: string,
  routeId: unknown,
  file: unknown,
  routeName: unknown,
): Promise<{ storagePath: string; filename: string; routeId: string | null }> {
  if (typeof routeId === "string" && routeId.length > 0) {
    const { data: route, error } = await serviceClient
      .from("gpx_routes")
      .select("id,filename,gpx_storage_path,is_public,user_id")
      .eq("id", routeId)
      .or(`user_id.eq.${userId},is_public.eq.true`)
      .single();
    if (error || !route) throw new Error("Route GPX introuvable.");
    if (!route.gpx_storage_path) throw new Error("Route GPX sans fichier Storage.");
    return {
      storagePath: route.gpx_storage_path,
      filename: route.filename ?? "route.gpx",
      routeId: route.id,
    };
  }
  if (file instanceof File) {
    assertGpxSize(file.size);
    const filename = safeFilename(file.name || "route.gpx");
    const path = `${userId}/routes/${crypto.randomUUID()}-${filename}`;
    const { error: uploadError } = await serviceClient.storage
      .from("gpx-files")
      .upload(path, file, { contentType: file.type || "application/gpx+xml", upsert: false });
    if (uploadError) throw uploadError;
    const { data: route, error: insertError } = await serviceClient
      .from("gpx_routes")
      .insert({
        user_id: userId,
        name: (typeof routeName === "string" && routeName.trim()) || filename.replace(/\.gpx$/i, ""),
        filename,
        gpx_storage_path: path,
        metadata: { uploaded_via: "predict-race" },
      })
      .select("id")
      .single();
    if (insertError) throw insertError;
    return { storagePath: path, filename, routeId: route?.id ?? null };
  }
  throw new Error("Fichier GPX ou route_id requis.");
}

// --- v1 : MVP inline (rapide, dans Deno) -----------------------------------
async function readGpxText(
  serviceClient: ServiceClient,
  userId: string,
  ref: { storagePath: string },
): Promise<string> {
  const { data: blob, error } = await serviceClient.storage
    .from("gpx-files")
    .download(ref.storagePath);
  if (error || !blob) throw new Error("Impossible de lire le GPX Storage.");
  const text = await blob.text();
  assertGpxSize(new TextEncoder().encode(text).byteLength);
  return text;
}

serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;
  if (req.method !== "POST") return errorResponse("Method not allowed", 405);

  try {
    const { user, serviceClient } = await requireUser(req);
    const form = await req.formData();

    const engine = String(form.get("engine") ?? "v3");
    const ref = await resolveGpxRef(
      serviceClient,
      user.id,
      form.get("route_id"),
      form.get("file"),
      form.get("name"),
    );

    const manualTemperature = Number(
      form.get("manual_temperature_c") ?? form.get("temperature_c") ?? NaN,
    );
    const analysisMode = String(form.get("analysis_mode") ?? "auto");
    const effortMode = String(form.get("effort_mode") ?? "steady");
    const ravitoMode = String(form.get("ravito_mode") ?? "auto");
    const weatherMode = String(form.get("weather_mode") ?? "manual");
    const historyStartDate = typeof form.get("history_start_date") === "string"
      ? String(form.get("history_start_date"))
      : null;
    const predictionName = String(form.get("prediction_name") ?? form.get("name") ?? ref.filename);
    const customRavitos = parseCustomRavitos(form.get("custom_ravitos"));

    // ---- v1 : moteur MVP inline (dans l'Edge) ----
    if (engine === "v1") {
      const text = await readGpxText(serviceClient, user.id, ref);
      const result = await buildRacePrediction(text, {
        userId: user.id,
        filename: ref.filename,
        analysisMode,
        effortMode,
        ravitoMode,
        weatherMode,
        manualTemperatureC: Number.isFinite(manualTemperature) ? manualTemperature : null,
        historyStartDate,
        customRavitos,
        serviceClient,
      });
      const { data: saved } = await serviceClient
        .from("race_predictions")
        .insert({
          user_id: user.id,
          route_id: ref.routeId,
          name: predictionName,
          filename: ref.filename,
          engine_version: result.engine_version,
          analysis_mode: result.analysis_mode,
          ravito_mode: result.ravito_mode,
          history_start_date: result.history_start_date,
          total_distance_km: result.total_distance_km,
          total_elevation_gain_m: result.total_elevation_gain_m,
          moving_time_min: result.moving_time_min,
          total_pause_min: result.total_pause_min,
          total_time_min: result.total_time_min,
          avg_pace: result.avg_pace,
          prediction_data: result,
        })
        .select("id")
        .single();
      return jsonResponse({ ...result, route_id: ref.routeId, saved_prediction_id: saved?.id ?? null });
    }

    // ---- v2 / v3 : enfile un job pour le worker maison (vrai moteur Python) ----
    const { data: job, error: jobError } = await serviceClient
      .from("prediction_jobs")
      .insert({
        user_id: user.id,
        engine,
        route_id: ref.routeId,
        gpx_storage_path: ref.storagePath,
        params: {
          analysis_mode: analysisMode,
          effort_mode: effortMode,
          ravito_mode: ravitoMode,
          weather_mode: weatherMode,
          manual_temperature_c: Number.isFinite(manualTemperature) ? manualTemperature : null,
          history_start_date: historyStartDate,
          custom_ravitos: customRavitos,
          prediction_name: predictionName,
          race_datetime: typeof form.get("race_datetime") === "string"
            ? String(form.get("race_datetime"))
            : null,
          target_heartrate: form.get("target_heartrate")
            ? Number(form.get("target_heartrate"))
            : null,
          filename: ref.filename,
        },
      })
      .select("id")
      .single();
    if (jobError) throw jobError;

    return jsonResponse({ pending: true, job_id: job?.id ?? null, engine });
  } catch (err) {
    if (err instanceof Response) return err;
    return errorResponse(
      err instanceof Error ? err.message : "Prediction failed",
      500,
      err,
    );
  }
});
