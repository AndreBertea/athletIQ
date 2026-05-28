import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { errorResponse, handleCors, jsonResponse } from "../_shared/cors.ts";
import { GarminClient, GarminError, loginGarmin, storeGarminToken } from "../_shared/garmin.ts";
import { requireUser } from "../_shared/supabase.ts";

const RATE_LIMIT_COOLDOWN_SECONDS = 3 * 60 * 60;
const VALID_TOKEN_GRACE_SECONDS = 10 * 60;

function cooldownMessage(seconds: number): string {
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  return `Garmin bloque temporairement les connexions. Réessaie dans ${minutes} min.`;
}

function rateLimitResponse(seconds = RATE_LIMIT_COOLDOWN_SECONDS): Response {
  return jsonResponse(
    {
      error: cooldownMessage(seconds),
      details: {
        code: "garmin_rate_limited",
        retry_after_seconds: seconds,
      },
    },
    429,
    { "Retry-After": String(seconds) },
  );
}

async function recentGarminCooldown(
  serviceClient: Awaited<ReturnType<typeof requireUser>>["serviceClient"],
  userId: string,
): Promise<number> {
  const { data, error } = await serviceClient
    .from("sync_jobs")
    .select("created_at,result")
    .eq("user_id", userId)
    .eq("type", "garmin_login")
    .eq("status", "failed")
    .order("created_at", { ascending: false })
    .limit(5);

  if (error) return 0;
  for (const row of data ?? []) {
    const result = row.result as Record<string, unknown> | null;
    if (result?.code !== "garmin_rate_limited") continue;
    const retryAfter = Number(result.retry_after_seconds ?? RATE_LIMIT_COOLDOWN_SECONDS);
    const elapsed = Math.floor((Date.now() - Date.parse(String(row.created_at))) / 1000);
    const remaining = Math.max(0, retryAfter - elapsed);
    if (remaining > 0) return remaining;
  }
  return 0;
}

async function existingGarminConnection(
  serviceClient: Awaited<ReturnType<typeof requireUser>>["serviceClient"],
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

async function createLoginJob(
  serviceClient: Awaited<ReturnType<typeof requireUser>>["serviceClient"],
  userId: string,
): Promise<string | null> {
  const { data, error } = await serviceClient
    .from("sync_jobs")
    .insert({
      user_id: userId,
      type: "garmin_login",
      status: "running",
      progress: 0,
      stage: "login",
      message: "Connexion Garmin Connect",
      started_at: new Date().toISOString(),
    })
    .select("id")
    .single();
  if (error) return null;
  return data?.id ?? null;
}

async function finishLoginJob(
  serviceClient: Awaited<ReturnType<typeof requireUser>>["serviceClient"],
  jobId: string | null,
  patch: Record<string, unknown>,
): Promise<void> {
  if (!jobId) return;
  await serviceClient
    .from("sync_jobs")
    .update({
      ...patch,
      finished_at: new Date().toISOString(),
    })
    .eq("id", jobId);
}

serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;
  if (req.method !== "POST") return errorResponse("Method not allowed", 405);

  let serviceClient: Awaited<ReturnType<typeof requireUser>>["serviceClient"] | null = null;
  let jobId: string | null = null;

  try {
    const auth = await requireUser(req);
    const { user } = auth;
    serviceClient = auth.serviceClient;
    const body = await req.json().catch(() => ({}));
    const email = String(body.email ?? "").trim();
    const password = String(body.password ?? "");
    const mfaCode = body.mfa_code ? String(body.mfa_code).trim() : null;
    const forceReconnect = body.force_reconnect === true;

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

    const cooldownSeconds = await recentGarminCooldown(serviceClient, user.id);
    if (cooldownSeconds > 0) return rateLimitResponse(cooldownSeconds);

    jobId = await createLoginJob(serviceClient, user.id);
    const result = await loginGarmin(email, password, mfaCode);
    if (result.needs_mfa) {
      await finishLoginJob(serviceClient, jobId, {
        status: "succeeded",
        progress: 100,
        stage: "mfa_required",
        message: "Code MFA Garmin requis.",
        result: { needs_mfa: true },
      });
      return jsonResponse({
        needs_mfa: true,
        message: "Code MFA Garmin requis.",
      });
    }
    if (!result.token) throw new Error("Token Garmin absent apres login.");

    const client = new GarminClient(result.token);
    const profile = await client.connectApi<Record<string, unknown>>(
      "/userprofile-service/socialProfile",
    );
    await storeGarminToken(serviceClient, user.id, client.token, profile, email);
    await finishLoginJob(serviceClient, jobId, {
      status: "succeeded",
      progress: 100,
      stage: "connected",
      message: "Garmin Connect connecte.",
    });

    return jsonResponse({
      connected: true,
      message: "Garmin Connect connecte.",
      display_name: profile?.displayName ?? profile?.fullName ?? profile?.userName ?? null,
    });
  } catch (err) {
    if (err instanceof Response) return err;
    if (err instanceof GarminError) {
      if (serviceClient) {
        await finishLoginJob(serviceClient, jobId, {
          status: "failed",
          stage: err.status === 429 ? "rate_limited" : "failed",
          error: err.message,
          result: {
            code: err.status === 429 ? "garmin_rate_limited" : err.code,
            garmin_code: err.code,
            status: err.status,
            retry_after_seconds: err.status === 429 ? RATE_LIMIT_COOLDOWN_SECONDS : undefined,
          },
        });
      }
      if (err.status === 429) return rateLimitResponse();
      return errorResponse(err.message, err.status, { code: err.code });
    }
    if (serviceClient) {
      await finishLoginJob(serviceClient, jobId, {
        status: "failed",
        stage: "failed",
        error: err instanceof Error ? err.message : "Connexion Garmin impossible.",
      });
    }
    return errorResponse(
      err instanceof Error ? err.message : "Connexion Garmin impossible.",
      500,
    );
  }
});
