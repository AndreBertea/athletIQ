import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { errorResponse, handleCors, jsonResponse } from "../_shared/cors.ts";
import { requireUser } from "../_shared/supabase.ts";
import { encryptSecret } from "../_shared/crypto.ts";

// Le login Garmin reel est delegue a un worker sur IP residentielle (le "relais
// maison"), car l'oauth-service de Garmin renvoie 429 depuis l'IP datacenter de
// Supabase. Cette fonction ne fait donc plus AUCUN appel a Garmin : elle depose
// une demande dans la file garmin_relay_jobs (identifiants chiffres) et cree un
// sync_jobs que la PWA peut suivre. Le worker fait le login depuis chez toi.

const VALID_TOKEN_GRACE_SECONDS = 10 * 60;

type ServiceClient = Awaited<ReturnType<typeof requireUser>>["serviceClient"];

async function existingGarminConnection(
  serviceClient: ServiceClient,
  userId: string,
): Promise<Record<string, unknown> | null> {
  const { data, error } = await serviceClient
    .from("external_auth_tokens")
    .select("display_name,email,expires_at,last_sync_at")
    .eq("user_id", userId)
    .eq("provider", "garmin")
    .maybeSingle();

  if (error || !data?.expires_at) return null;
  const expiresAt = Date.parse(String(data.expires_at));
  if (!Number.isFinite(expiresAt)) return null;
  if (expiresAt <= Date.now() + VALID_TOKEN_GRACE_SECONDS * 1000) return null;
  return data as Record<string, unknown>;
}

// Soumission du code MFA : on rattache le code au job du relais qui attend, et on
// rouvre le sync_jobs lie pour que la PWA continue de patienter.
async function submitMfaCode(
  serviceClient: ServiceClient,
  userId: string,
  mfaCode: string,
): Promise<Response> {
  const { data: job, error } = await serviceClient
    .from("garmin_relay_jobs")
    .select("id,sync_job_id")
    .eq("user_id", userId)
    .eq("status", "awaiting_mfa")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error || !job) {
    return errorResponse(
      "Aucune connexion Garmin en attente de code. Relance la connexion.",
      409,
    );
  }

  await serviceClient
    .from("garmin_relay_jobs")
    .update({
      mfa_code_encrypted: await encryptSecret(mfaCode),
      status: "mfa_submitted",
      error: null,
    })
    .eq("id", job.id);

  if (job.sync_job_id) {
    await serviceClient
      .from("sync_jobs")
      .update({
        status: "running",
        stage: "mfa_verifying",
        message: "Verification du code Garmin...",
        error: null,
      })
      .eq("id", job.sync_job_id);
  }

  return jsonResponse({
    pending: true,
    job_id: job.sync_job_id,
    message: "Code Garmin transmis, verification en cours.",
  });
}

serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;
  if (req.method !== "POST") return errorResponse("Method not allowed", 405);

  try {
    const { user, serviceClient } = await requireUser(req);
    const body = await req.json().catch(() => ({}));
    const email = String(body.email ?? "").trim();
    const password = String(body.password ?? "");
    const mfaCode = body.mfa_code ? String(body.mfa_code).trim() : null;
    const forceReconnect = body.force_reconnect === true;

    // Etape MFA : un code est fourni -> on le rattache au job en attente.
    if (mfaCode) {
      return await submitMfaCode(serviceClient, user.id, mfaCode);
    }

    if (!email || !password) return errorResponse("Email et mot de passe Garmin requis.", 422);

    if (!forceReconnect) {
      const existing = await existingGarminConnection(serviceClient, user.id);
      if (existing) {
        return jsonResponse({
          connected: true,
          already_connected: true,
          message: "Garmin Connect deja connecte.",
          display_name: existing.display_name ?? null,
          expires_at: existing.expires_at ?? null,
          last_sync_at: existing.last_sync_at ?? null,
        });
      }
    }

    // sync_jobs : suivi visible cote PWA (meme type que l'ancien flow).
    const { data: syncJob, error: syncErr } = await serviceClient
      .from("sync_jobs")
      .insert({
        user_id: user.id,
        type: "garmin_login",
        status: "running",
        progress: 0,
        stage: "queued_relay",
        message: "Connexion Garmin en file d'attente (relais)...",
        started_at: new Date().toISOString(),
      })
      .select("id")
      .single();
    if (syncErr) throw syncErr;
    const syncJobId = syncJob?.id ?? null;

    // File du relais : identifiants chiffres (AES-GCM via ENCRYPTION_KEY).
    const { error: relayErr } = await serviceClient
      .from("garmin_relay_jobs")
      .insert({
        user_id: user.id,
        sync_job_id: syncJobId,
        status: "pending",
        credentials_encrypted: await encryptSecret({ email, password }),
      });
    if (relayErr) {
      if (syncJobId) {
        await serviceClient
          .from("sync_jobs")
          .update({
            status: "failed",
            stage: "failed",
            error: "Impossible de mettre la connexion Garmin en file.",
            finished_at: new Date().toISOString(),
          })
          .eq("id", syncJobId);
      }
      throw relayErr;
    }

    return jsonResponse({
      pending: true,
      job_id: syncJobId,
      message: "Connexion Garmin en cours via le relais.",
    });
  } catch (err) {
    if (err instanceof Response) return err;
    return errorResponse(
      err instanceof Error ? err.message : "Connexion Garmin impossible.",
      500,
    );
  }
});
