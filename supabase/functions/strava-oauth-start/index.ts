import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { errorResponse, handleCors, jsonResponse } from "../_shared/cors.ts";
import { requireUser } from "../_shared/supabase.ts";
import { signState } from "../_shared/crypto.ts";

serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;
  if (req.method !== "POST" && req.method !== "GET") return errorResponse("Method not allowed", 405);

  try {
    const { user } = await requireUser(req);
    const clientId = Deno.env.get("STRAVA_CLIENT_ID");
    if (!clientId) throw new Error("Missing STRAVA_CLIENT_ID");

    const origin = new URL(req.url).origin;
    const redirectUri = Deno.env.get("STRAVA_REDIRECT_URI") ?? `${origin}/strava-oauth-callback`;
    const state = await signState({
      uid: user.id,
      nonce: crypto.randomUUID(),
      ts: Date.now(),
    });

    const url = new URL("https://www.strava.com/oauth/authorize");
    url.searchParams.set("client_id", clientId);
    url.searchParams.set("redirect_uri", redirectUri);
    url.searchParams.set("response_type", "code");
    url.searchParams.set("approval_prompt", "auto");
    url.searchParams.set("scope", "read,activity:read_all");
    url.searchParams.set("state", state);

    return jsonResponse({ url: url.toString(), redirect_uri: redirectUri });
  } catch (err) {
    if (err instanceof Response) return err;
    return errorResponse(err instanceof Error ? err.message : "Strava OAuth start failed", 500);
  }
});
