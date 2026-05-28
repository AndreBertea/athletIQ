import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { errorResponse, handleCors } from "../_shared/cors.ts";
import { requireUser } from "../_shared/supabase.ts";

const EXPORT_TABLES = [
  "profiles",
  "activities",
  "activity_weather",
  "garmin_daily",
  "fit_metrics",
  "segments",
  "segment_features",
  "training_load",
  "daily_checkins",
  "athletic_profiles",
  "reference_tests",
  "gpx_routes",
  "gpx_route_settings",
  "race_predictions",
  "sync_jobs",
  "job_events",
] as const;

serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;
  if (req.method !== "GET") return errorResponse("Method not allowed", 405);

  try {
    const { user, serviceClient } = await requireUser(req);
    const exportData: Record<string, unknown> = {
      exported_at: new Date().toISOString(),
      user: { id: user.id, email: user.email },
      tables: {},
    };

    for (const table of EXPORT_TABLES) {
      const column = table === "profiles" ? "id" : "user_id";
      const { data, error } = await serviceClient
        .from(table)
        .select("*")
        .eq(column, user.id);
      if (error) throw error;
      (exportData.tables as Record<string, unknown>)[table] = data ?? [];
    }

    return new Response(JSON.stringify(exportData, null, 2), {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/json",
        "Content-Disposition": `attachment; filename="agon-export-${user.id}.json"`,
      },
    });
  } catch (err) {
    if (err instanceof Response) return err;
    return errorResponse(err instanceof Error ? err.message : "Export failed", 500);
  }
});
