import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { errorResponse, handleCors, jsonResponse } from "../_shared/cors.ts";
import { requireUser } from "../_shared/supabase.ts";

const DELETE_TABLES = [
  "job_events",
  "sync_jobs",
  "race_predictions",
  "gpx_route_settings",
  "gpx_route_attachments",
  "gpx_routes",
  "reference_tests",
  "athletic_profiles",
  "daily_checkins",
  "training_load",
  "segment_features",
  "segments",
  "fit_metrics",
  "activity_weather",
  "garmin_daily",
  "activities",
  "external_auth_tokens",
] as const;

async function removeStoragePrefix(
  serviceClient: Awaited<ReturnType<typeof requireUser>>["serviceClient"],
  bucket: string,
  prefix: string,
): Promise<number> {
  const { data, error } = await serviceClient.storage.from(bucket).list(prefix, {
    limit: 1000,
    sortBy: { column: "name", order: "asc" },
  });
  if (error || !data) return 0;

  const files = data.filter((item) => !item.name.endsWith("/")).map((item) => `${prefix}/${item.name}`);
  const folders = data.filter((item) => item.name.endsWith("/"));

  let removed = 0;
  if (files.length > 0) {
    const { error: removeError } = await serviceClient.storage.from(bucket).remove(files);
    if (removeError) throw removeError;
    removed += files.length;
  }
  for (const folder of folders) {
    removed += await removeStoragePrefix(serviceClient, bucket, `${prefix}/${folder.name.replace(/\/$/, "")}`);
  }
  return removed;
}

serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;
  if (req.method !== "DELETE" && req.method !== "POST") {
    return errorResponse("Method not allowed", 405);
  }

  try {
    const { user, serviceClient } = await requireUser(req);
    const deletedRows: Record<string, number> = {};

    const deletedActivityRaw = await removeStoragePrefix(serviceClient, "activity-raw", user.id);
    const deletedGpx = await removeStoragePrefix(serviceClient, "gpx-files", user.id);

    for (const table of DELETE_TABLES) {
      const { count, error } = await serviceClient
        .from(table)
        .delete({ count: "exact" })
        .eq("user_id", user.id);
      if (error) throw error;
      deletedRows[table] = count ?? 0;
    }

    await serviceClient.from("profiles").delete().eq("id", user.id);
    const { error: authError } = await serviceClient.auth.admin.deleteUser(user.id);
    if (authError) throw authError;

    return jsonResponse({
      deleted: true,
      user_id: user.id,
      deleted_rows: deletedRows,
      deleted_storage_objects: {
        activity_raw: deletedActivityRaw,
        gpx_files: deletedGpx,
      },
    });
  } catch (err) {
    if (err instanceof Response) return err;
    return errorResponse(err instanceof Error ? err.message : "Delete account failed", 500);
  }
});
