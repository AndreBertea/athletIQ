import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { errorResponse, handleCors, jsonResponse } from "../_shared/cors.ts";
import { decryptSecret, encryptSecret } from "../_shared/crypto.ts";
import { addJobEvent, createJob, updateJob } from "../_shared/jobs.ts";
import { requireUser } from "../_shared/supabase.ts";

interface StravaActivity {
  id: number;
  name: string;
  type?: string;
  sport_type?: string;
  start_date?: string;
  timezone?: string;
  location_city?: string | null;
  location_country?: string | null;
  distance?: number;
  moving_time?: number;
  elapsed_time?: number;
  total_elevation_gain?: number;
  average_speed?: number;
  max_speed?: number;
  average_heartrate?: number;
  max_heartrate?: number;
  average_cadence?: number;
  calories?: number;
  visibility?: string;
  private?: boolean;
  description?: string | null;
  map?: { summary_polyline?: string; polyline?: string };
  start_latlng?: [number, number];
  end_latlng?: [number, number];
}

interface StoredToken {
  id: string;
  access_token_encrypted: string;
  refresh_token_encrypted: string;
  expires_at: string | null;
}

async function refreshAccessToken(refreshToken: string): Promise<{
  access_token: string;
  refresh_token: string;
  expires_at: number;
}> {
  const clientId = Deno.env.get("STRAVA_CLIENT_ID");
  const clientSecret = Deno.env.get("STRAVA_CLIENT_SECRET");
  if (!clientId || !clientSecret) throw new Error("Missing Strava secrets");

  const response = await fetch("https://www.strava.com/oauth/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: clientId,
      client_secret: clientSecret,
      grant_type: "refresh_token",
      refresh_token: refreshToken,
    }),
  });
  if (!response.ok) throw new Error(`Strava refresh failed: ${response.status}`);
  return await response.json();
}

serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;
  if (req.method !== "POST") return errorResponse("Method not allowed", 405);

  let jobId: string | null = null;
  try {
    const { user, serviceClient } = await requireUser(req);
    const body = await req.json().catch(() => ({}));
    const daysBack = Number(body.days_back ?? 30);
    const after = Math.floor((Date.now() - daysBack * 24 * 60 * 60 * 1000) / 1000);

    jobId = await createJob(serviceClient, user.id, "strava_sync", { days_back: daysBack });
    await addJobEvent(serviceClient, jobId, user.id, "started", "Synchronisation Strava démarrée");

    const { data: tokenRow, error: tokenError } = await serviceClient
      .from("external_auth_tokens")
      .select("id,access_token_encrypted,refresh_token_encrypted,expires_at")
      .eq("user_id", user.id)
      .eq("provider", "strava")
      .single();
    if (tokenError || !tokenRow) throw new Error("Compte Strava non connecté.");

    const storedToken = tokenRow as StoredToken;
    let accessToken = await decryptSecret<string>(storedToken.access_token_encrypted);
    const refreshToken = await decryptSecret<string>(storedToken.refresh_token_encrypted);

    if (!storedToken.expires_at || new Date(storedToken.expires_at).getTime() < Date.now() + 60_000) {
      const refreshed = await refreshAccessToken(refreshToken);
      accessToken = refreshed.access_token;
      await serviceClient
        .from("external_auth_tokens")
        .update({
          access_token_encrypted: await encryptSecret(refreshed.access_token),
          refresh_token_encrypted: await encryptSecret(refreshed.refresh_token),
          expires_at: new Date(refreshed.expires_at * 1000).toISOString(),
        })
        .eq("id", storedToken.id);
    }

    const imported: string[] = [];
    let page = 1;
    while (page <= 5) {
      const url = new URL("https://www.strava.com/api/v3/athlete/activities");
      url.searchParams.set("per_page", "100");
      url.searchParams.set("page", String(page));
      url.searchParams.set("after", String(after));

      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!response.ok) throw new Error(`Strava activities failed: ${response.status}`);
      const activities = await response.json() as StravaActivity[];
      if (activities.length === 0) break;

      for (const activity of activities) {
        const row = {
          user_id: user.id,
          source: "strava",
          strava_id: activity.id,
          name: activity.name || "Activité Strava",
          sport_type: activity.sport_type ?? activity.type ?? "Run",
          activity_type: activity.type ?? activity.sport_type ?? null,
          start_date_utc: activity.start_date ?? null,
          timezone: activity.timezone ?? null,
          location_city: activity.location_city ?? null,
          location_country: activity.location_country ?? null,
          distance_m: activity.distance ?? null,
          moving_time_s: activity.moving_time ?? null,
          elapsed_time_s: activity.elapsed_time ?? null,
          elev_gain_m: activity.total_elevation_gain ?? null,
          avg_speed_m_s: activity.average_speed ?? null,
          max_speed_m_s: activity.max_speed ?? null,
          avg_heartrate_bpm: activity.average_heartrate ?? null,
          max_heartrate_bpm: activity.max_heartrate ?? null,
          avg_cadence: activity.average_cadence ?? null,
          calories_kcal: activity.calories ?? null,
          visibility: activity.visibility ?? null,
          private: activity.private ?? false,
          description: activity.description ?? null,
          summary_polyline: activity.map?.summary_polyline ?? null,
          polyline: activity.map?.polyline ?? null,
          start_latlng: activity.start_latlng ?? null,
          end_latlng: activity.end_latlng ?? null,
          has_strava: true,
          raw_summary: activity,
        };

        const { data: existing } = await serviceClient
          .from("activities")
          .select("id")
          .eq("user_id", user.id)
          .eq("strava_id", activity.id)
          .maybeSingle();

        if (existing?.id) {
          await serviceClient.from("activities").update(row).eq("id", existing.id);
          imported.push(existing.id);
        } else {
          const { data: inserted, error: insertError } = await serviceClient
            .from("activities")
            .insert(row)
            .select("id")
            .single();
          if (insertError) throw insertError;
          imported.push(inserted.id);
        }
      }

      await updateJob(serviceClient, jobId, {
        progress: Math.min(90, page * 18),
        stage: "activities",
        message: `${imported.length} activités importées`,
      });
      page += 1;
    }

    await serviceClient
      .from("external_auth_tokens")
      .update({ last_sync_at: new Date().toISOString() })
      .eq("user_id", user.id)
      .eq("provider", "strava");

    await addJobEvent(serviceClient, jobId, user.id, "finished", "Synchronisation Strava terminée", {
      imported_count: imported.length,
    });
    await updateJob(serviceClient, jobId, {
      status: "succeeded",
      progress: 100,
      stage: "done",
      result: { imported_count: imported.length },
      finished_at: new Date().toISOString(),
    });

    return jsonResponse({ imported_count: imported.length, job_id: jobId });
  } catch (err) {
    if (err instanceof Response) return err;
    try {
      const { user, serviceClient } = await requireUser(req);
      await updateJob(serviceClient, jobId, {
        status: "failed",
        error: err instanceof Error ? err.message : "Strava sync failed",
        finished_at: new Date().toISOString(),
      });
      await addJobEvent(serviceClient, jobId, user.id, "failed", err instanceof Error ? err.message : undefined);
    } catch {
      // Best-effort job failure update.
    }
    return errorResponse(err instanceof Error ? err.message : "Strava sync failed", 500);
  }
});
