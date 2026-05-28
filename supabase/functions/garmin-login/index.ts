import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { errorResponse, handleCors, jsonResponse } from "../_shared/cors.ts";
import { GarminClient, loginGarmin, storeGarminToken } from "../_shared/garmin.ts";
import { requireUser } from "../_shared/supabase.ts";

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

    if (!email || !password) return errorResponse("Email et mot de passe Garmin requis.", 422);

    const result = await loginGarmin(email, password, mfaCode);
    if (result.needs_mfa) {
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

    return jsonResponse({
      connected: true,
      message: "Garmin Connect connecte.",
      display_name: profile?.displayName ?? profile?.fullName ?? profile?.userName ?? null,
    });
  } catch (err) {
    if (err instanceof Response) return err;
    return errorResponse(
      err instanceof Error ? err.message : "Connexion Garmin impossible.",
      500,
    );
  }
});
