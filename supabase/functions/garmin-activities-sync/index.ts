import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { errorResponse, handleCors, jsonResponse } from "../_shared/cors.ts";
import { addJobEvent, createJob, updateJob } from "../_shared/jobs.ts";
import { listGarminActivities, loadGarminClient, mapGarminActivity } from "../_shared/garmin.ts";
import { requireUser } from "../_shared/supabase.ts";

serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;
  if (req.method !== "POST") return errorResponse("Method not allowed", 405);

  let jobId: string | null = null;
  try {
    const { user, serviceClient } = await requireUser(req);
    const body = await req.json().catch(() => ({}));
    const daysBack = Math.max(1, Math.min(Number(body.days_back ?? 30), 365));
    const preview = Boolean(body.preview);

    const { client } = await loadGarminClient(serviceClient, user.id);
    const activities = await listGarminActivities(client, daysBack);
    const garminIds = activities
      .map((activity) => Number(activity.activityId))
      .filter(Number.isFinite);

    let existingIds = new Set<number>();
    if (garminIds.length > 0) {
      const { data, error } = await serviceClient
        .from("activities")
        .select("garmin_activity_id")
        .eq("user_id", user.id)
        .in("garmin_activity_id", garminIds);
      if (error) throw error;
      existingIds = new Set((data ?? []).map((row) => Number(row.garmin_activity_id)));
    }

    if (preview) {
      return jsonResponse({
        days_back: daysBack,
        period_started_at: new Date(Date.now() - daysBack * 24 * 60 * 60 * 1000).toISOString(),
        total_activities: garminIds.length,
        existing_activities: existingIds.size,
        missing_activities: Math.max(0, garminIds.length - existingIds.size),
      });
    }

    jobId = await createJob(serviceClient, user.id, "garmin_activities_sync", { days_back: daysBack });
    await addJobEvent(serviceClient, jobId, user.id, "started", "Import activites Garmin demarre");

    let created = 0;
    let skipped = 0;
    let errors = 0;

    for (let index = 0; index < activities.length; index += 1) {
      const activity = activities[index];
      const garminId = Number(activity.activityId);
      if (!Number.isFinite(garminId)) {
        errors += 1;
        continue;
      }
      try {
        const row = mapGarminActivity(activity, user.id);
        const { data: existing, error: existingError } = await serviceClient
          .from("activities")
          .select("id")
          .eq("user_id", user.id)
          .eq("garmin_activity_id", garminId)
          .maybeSingle();
        if (existingError) throw existingError;

        if (existing?.id) {
          const { error } = await serviceClient.from("activities").update(row).eq("id", existing.id);
          if (error) throw error;
          skipped += 1;
        } else {
          const { error } = await serviceClient.from("activities").insert(row);
          if (error) throw error;
          created += 1;
        }
      } catch {
        errors += 1;
      }

      await updateJob(serviceClient, jobId, {
        progress: Math.min(95, Math.round(((index + 1) / Math.max(activities.length, 1)) * 95)),
        stage: "activities",
        message: `${index + 1}/${activities.length} activite(s) Garmin traitees`,
      });
    }

    const result = {
      created,
      linked: 0,
      merged: 0,
      skipped,
      errors,
      total: activities.length,
    };
    await serviceClient
      .from("external_auth_tokens")
      .update({ last_sync_at: new Date().toISOString() })
      .eq("user_id", user.id)
      .eq("provider", "garmin");
    await updateJob(serviceClient, jobId, {
      status: "succeeded",
      progress: 100,
      stage: "done",
      result,
      finished_at: new Date().toISOString(),
    });
    await addJobEvent(serviceClient, jobId, user.id, "finished", "Import activites Garmin termine", result);

    return jsonResponse({ ...result, job_id: jobId });
  } catch (err) {
    if (err instanceof Response) return err;
    try {
      const { user, serviceClient } = await requireUser(req);
      await updateJob(serviceClient, jobId, {
        status: "failed",
        error: err instanceof Error ? err.message : "Garmin activities sync failed",
        finished_at: new Date().toISOString(),
      });
      await addJobEvent(serviceClient, jobId, user.id, "failed", err instanceof Error ? err.message : undefined);
    } catch {
      // Best-effort failure reporting.
    }
    return errorResponse(err instanceof Error ? err.message : "Garmin activities sync failed", 500);
  }
});
