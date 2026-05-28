import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { errorResponse, handleCors, jsonResponse } from "../_shared/cors.ts";
import { requireUser } from "../_shared/supabase.ts";
import {
  assertGpxSize,
  buildRacePrediction,
  parseCustomRavitos,
} from "../_shared/prediction.ts";

function safeFilename(name: string): string {
  return name.replace(/[^a-zA-Z0-9._-]+/g, "_").slice(0, 120) || "route.gpx";
}

async function readGpxFromRoute(
  serviceClient: Awaited<ReturnType<typeof requireUser>>["serviceClient"],
  userId: string,
  routeId: string,
): Promise<{ text: string; filename: string; routeId: string }> {
  const { data: route, error } = await serviceClient
    .from("gpx_routes")
    .select("id,filename,gpx_storage_path,is_public,user_id")
    .eq("id", routeId)
    .or(`user_id.eq.${userId},is_public.eq.true`)
    .single();

  if (error || !route) throw new Error("Route GPX introuvable.");
  if (!route.gpx_storage_path) throw new Error("Route GPX sans fichier Storage.");

  const { data: blob, error: downloadError } = await serviceClient.storage
    .from("gpx-files")
    .download(route.gpx_storage_path);
  if (downloadError || !blob) throw new Error("Impossible de lire le GPX Storage.");

  const text = await blob.text();
  assertGpxSize(new TextEncoder().encode(text).byteLength);
  return { text, filename: route.filename ?? "route.gpx", routeId: route.id };
}

async function readGpxFromUpload(
  serviceClient: Awaited<ReturnType<typeof requireUser>>["serviceClient"],
  userId: string,
  file: File,
  name?: string | null,
): Promise<{ text: string; filename: string; routeId: string | null }> {
  assertGpxSize(file.size);

  const filename = safeFilename(file.name || "route.gpx");
  const path = `${userId}/routes/${crypto.randomUUID()}-${filename}`;
  const { error: uploadError } = await serviceClient.storage
    .from("gpx-files")
    .upload(path, file, {
      contentType: file.type || "application/gpx+xml",
      upsert: false,
    });
  if (uploadError) throw uploadError;

  const text = await file.text();
  const { data: route, error: insertError } = await serviceClient
    .from("gpx_routes")
    .insert({
      user_id: userId,
      name: name?.trim() || filename.replace(/\.gpx$/i, ""),
      filename,
      gpx_storage_path: path,
      metadata: { uploaded_via: "predict-race" },
    })
    .select("id")
    .single();

  if (insertError) throw insertError;
  return { text, filename, routeId: route?.id ?? null };
}

serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;
  if (req.method !== "POST") return errorResponse("Method not allowed", 405);

  try {
    const { user, serviceClient } = await requireUser(req);
    const form = await req.formData();

    const routeId = form.get("route_id");
    const file = form.get("file");
    const routeName = form.get("name");

    let gpx: { text: string; filename: string; routeId: string | null };
    if (typeof routeId === "string" && routeId.length > 0) {
      gpx = await readGpxFromRoute(serviceClient, user.id, routeId);
    } else if (file instanceof File) {
      gpx = await readGpxFromUpload(
        serviceClient,
        user.id,
        file,
        typeof routeName === "string" ? routeName : null,
      );
    } else {
      return errorResponse("Fichier GPX ou route_id requis.", 422);
    }

    const manualTemperature = Number(
      form.get("manual_temperature_c") ?? form.get("temperature_c") ?? NaN,
    );

    const result = await buildRacePrediction(gpx.text, {
      userId: user.id,
      filename: gpx.filename,
      analysisMode: String(form.get("analysis_mode") ?? "auto"),
      effortMode: String(form.get("effort_mode") ?? "steady"),
      ravitoMode: String(form.get("ravito_mode") ?? "auto"),
      weatherMode: String(form.get("weather_mode") ?? "manual"),
      manualTemperatureC: Number.isFinite(manualTemperature) ? manualTemperature : null,
      historyStartDate: typeof form.get("history_start_date") === "string"
        ? String(form.get("history_start_date"))
        : null,
      customRavitos: parseCustomRavitos(form.get("custom_ravitos")),
      serviceClient,
    });

    const { data: saved, error: saveError } = await serviceClient
      .from("race_predictions")
      .insert({
        user_id: user.id,
        route_id: gpx.routeId,
        name: String(form.get("prediction_name") ?? routeName ?? gpx.filename),
        filename: gpx.filename,
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

    if (saveError) throw saveError;

    return jsonResponse({
      ...result,
      route_id: gpx.routeId,
      saved_prediction_id: saved?.id ?? null,
    });
  } catch (err) {
    if (err instanceof Response) return err;
    return errorResponse(
      err instanceof Error ? err.message : "Prediction failed",
      500,
      err,
    );
  }
});
