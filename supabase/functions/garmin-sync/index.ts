import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { errorResponse, handleCors, jsonResponse } from "../_shared/cors.ts";
import { addJobEvent, createJob, updateJob } from "../_shared/jobs.ts";
import { syncGarminDaily } from "../_shared/garmin.ts";
import { requireUser } from "../_shared/supabase.ts";

serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;
  if (req.method !== "POST") return errorResponse("Method not allowed", 405);

  let jobId: string | null = null;
  try {
    const { user, serviceClient } = await requireUser(req);
    const body = await req.json().catch(() => ({}));
    const daysBack = Math.max(1, Math.min(Number(body.days_back ?? 30), 90));
    const startOffsetDays = Math.max(0, Number(body.start_offset_days ?? 0));

    jobId = await createJob(serviceClient, user.id, "garmin_daily_sync", {
      days_back: daysBack,
      start_offset_days: startOffsetDays,
    });
    await addJobEvent(serviceClient, jobId, user.id, "started", "Synchronisation Garmin daily demarree");

    const result = await syncGarminDaily(serviceClient, user.id, daysBack, startOffsetDays, async (done, total) => {
      await updateJob(serviceClient, jobId, {
        progress: Math.min(95, Math.round((done / total) * 95)),
        stage: "daily",
        message: `${done}/${total} jour(s) Garmin traites`,
      });
    });

    await updateJob(serviceClient, jobId, {
      status: "succeeded",
      progress: 100,
      stage: "done",
      result,
      finished_at: new Date().toISOString(),
    });
    await addJobEvent(serviceClient, jobId, user.id, "finished", "Synchronisation Garmin daily terminee", result);

    return jsonResponse({ ...result, job_id: jobId });
  } catch (err) {
    if (err instanceof Response) return err;
    try {
      const { user, serviceClient } = await requireUser(req);
      await updateJob(serviceClient, jobId, {
        status: "failed",
        error: err instanceof Error ? err.message : "Garmin sync failed",
        finished_at: new Date().toISOString(),
      });
      await addJobEvent(serviceClient, jobId, user.id, "failed", err instanceof Error ? err.message : undefined);
    } catch {
      // Best-effort failure reporting.
    }
    return errorResponse(err instanceof Error ? err.message : "Garmin sync failed", 500);
  }
});
