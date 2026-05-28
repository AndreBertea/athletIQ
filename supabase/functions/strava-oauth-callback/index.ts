import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { errorResponse, handleCors } from "../_shared/cors.ts";
import { encryptSecret, verifyState } from "../_shared/crypto.ts";
import { createServiceClient } from "../_shared/supabase.ts";

interface StravaTokenResponse {
  token_type: string;
  expires_at: number;
  expires_in: number;
  refresh_token: string;
  access_token: string;
  athlete?: {
    id?: number;
    username?: string;
    firstname?: string;
    lastname?: string;
  };
  scope?: string;
}

serve(async (req) => {
  const cors = handleCors(req);
  if (cors) return cors;

  try {
    const url = new URL(req.url);
    const code = url.searchParams.get("code");
    const state = url.searchParams.get("state");
    const error = url.searchParams.get("error");
    if (error) throw new Error(`Strava OAuth refused: ${error}`);
    if (!code || !state) throw new Error("Missing Strava code/state");

    const payload = await verifyState<{ uid: string; ts: number }>(state);
    if (!payload.uid) throw new Error("Invalid OAuth user state");

    const clientId = Deno.env.get("STRAVA_CLIENT_ID");
    const clientSecret = Deno.env.get("STRAVA_CLIENT_SECRET");
    if (!clientId || !clientSecret) throw new Error("Missing Strava secrets");

    const tokenResponse = await fetch("https://www.strava.com/oauth/token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_id: clientId,
        client_secret: clientSecret,
        code,
        grant_type: "authorization_code",
      }),
    });
    if (!tokenResponse.ok) {
      throw new Error(`Strava token exchange failed: ${tokenResponse.status}`);
    }

    const token = await tokenResponse.json() as StravaTokenResponse;
    const athleteName = [token.athlete?.firstname, token.athlete?.lastname]
      .filter(Boolean)
      .join(" ")
      .trim();

    const serviceClient = createServiceClient();
    const { error: upsertError } = await serviceClient
      .from("external_auth_tokens")
      .upsert({
        user_id: payload.uid,
        provider: "strava",
        provider_user_id: token.athlete?.id ? String(token.athlete.id) : null,
        display_name: athleteName || token.athlete?.username || null,
        scopes: token.scope?.split(",").filter(Boolean) ?? ["read", "activity:read_all"],
        access_token_encrypted: await encryptSecret(token.access_token),
        refresh_token_encrypted: await encryptSecret(token.refresh_token),
        expires_at: new Date(token.expires_at * 1000).toISOString(),
        token_payload: {
          token_type: token.token_type,
          expires_in: token.expires_in,
          athlete: token.athlete,
        },
      }, { onConflict: "user_id,provider" });
    if (upsertError) throw upsertError;

    const siteUrl = Deno.env.get("PUBLIC_SITE_URL") ?? Deno.env.get("SITE_URL") ?? "/";
    return Response.redirect(`${siteUrl.replace(/\/$/, "")}/profile?strava=connected`, 302);
  } catch (err) {
    if (err instanceof Response) return err;
    return errorResponse(err instanceof Error ? err.message : "Strava callback failed", 500);
  }
});
