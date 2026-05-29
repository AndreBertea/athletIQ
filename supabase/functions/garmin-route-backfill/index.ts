/**
 * garmin-route-backfill — recalcule `summary_polyline` pour les activités
 * déjà enrichies (has_streams) dont la polyline est encore vide.
 *
 * Lit le `streams.json` DÉJÀ présent dans le storage (`activity-raw`), encode
 * la trace latlng en polyline Google, et met à jour la ligne activité.
 * AUCUN appel Garmin (donc pas de quota, pas besoin du relais maison).
 *
 * Idempotent : ne traite que les activités où `summary_polyline is null`.
 * Appeler en boucle jusqu'à `remaining = 0` (batch de `max_activities`).
 */

import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { errorResponse, handleCors, jsonResponse } from "../_shared/cors.ts";
import { requireUser } from "../_shared/supabase.ts";
import { encodePolyline } from "../_shared/polyline.ts";

serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;
  if (req.method !== "POST") return errorResponse("Method not allowed", 405);

  try {
    const { user, serviceClient } = await requireUser(req);
    const body = await req.json().catch(() => ({}));
    const maxActivities = Math.max(1, Math.min(Number(body.max_activities ?? 200), 500));

    const { data: rows, error } = await serviceClient
      .from("activities")
      .select("id,raw_streams_path")
      .eq("user_id", user.id)
      .eq("has_streams", true)
      .is("summary_polyline", null)
      .not("raw_streams_path", "is", null)
      .order("start_date_utc", { ascending: false })
      .limit(maxActivities);
    if (error) throw error;

    let updated = 0;
    let skipped = 0;
    let failed = 0;

    for (const row of rows ?? []) {
      const path = row.raw_streams_path as string | null;
      if (!path) {
        skipped += 1;
        continue;
      }
      try {
        const blob = await serviceClient.storage.from("activity-raw").download(path);
        if (blob.error || !blob.data) {
          failed += 1;
          continue;
        }
        const streams = JSON.parse(await blob.data.text());
        const latlng = streams?.latlng?.data as
          | Array<[number, number] | null>
          | undefined;
        const polyline = encodePolyline(latlng);
        if (!polyline) {
          // Pas de GPS exploitable : marquer pour ne pas re-tenter en boucle.
          await serviceClient
            .from("activities")
            .update({ summary_polyline: "" })
            .eq("id", row.id)
            .eq("user_id", user.id);
          skipped += 1;
          continue;
        }
        const { error: updateError } = await serviceClient
          .from("activities")
          .update({ summary_polyline: polyline })
          .eq("id", row.id)
          .eq("user_id", user.id);
        if (updateError) throw updateError;
        updated += 1;
      } catch (e) {
        console.error(`[route-backfill] ${row.id}: ${e instanceof Error ? e.message : String(e)}`);
        failed += 1;
      }
    }

    // Combien reste-t-il après ce batch ?
    const { count: remaining } = await serviceClient
      .from("activities")
      .select("id", { count: "exact", head: true })
      .eq("user_id", user.id)
      .eq("has_streams", true)
      .is("summary_polyline", null);

    return jsonResponse({
      processed: (rows ?? []).length,
      updated,
      skipped,
      failed,
      remaining: remaining ?? 0,
    });
  } catch (e) {
    if (e instanceof Response) return e;
    return errorResponse(e instanceof Error ? e.message : String(e), 500);
  }
});
