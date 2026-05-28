import type { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";
import { decryptSecret, encryptSecret } from "./crypto.ts";

const DOMAIN = "garmin.com";
const SSO_BASE = `https://sso.${DOMAIN}/sso`;
const CONNECT_API_BASE = `https://connectapi.${DOMAIN}`;
const OAUTH_CONSUMER_URL = "https://thegarth.s3.amazonaws.com/oauth_consumer.json";
const GARMIN_USER_AGENT = "com.garmin.android.apps.connectmobile";

interface OAuthConsumer {
  consumer_key: string;
  consumer_secret: string;
}

export interface OAuth1Token {
  oauth_token: string;
  oauth_token_secret: string;
  mfa_token?: string | null;
  mfa_expiration_timestamp?: string | null;
  domain?: string | null;
}

export interface OAuth2Token {
  scope: string;
  jti: string;
  token_type: string;
  access_token: string;
  refresh_token: string;
  expires_in: number;
  expires_at: number;
  refresh_token_expires_in: number;
  refresh_token_expires_at: number;
}

export interface GarminToken {
  oauth1: OAuth1Token;
  oauth2: OAuth2Token;
  domain: string;
}

export interface GarminLoginResult {
  needs_mfa?: boolean;
  token?: GarminToken;
}

export class GarminError extends Error {
  constructor(
    message: string,
    public status = 500,
    public code = "garmin_error",
  ) {
    super(message);
  }
}

let consumerCache: OAuthConsumer | null = null;

function rfc3986(value: string): string {
  return encodeURIComponent(value).replace(/[!'()*]/g, (char) =>
    `%${char.charCodeAt(0).toString(16).toUpperCase()}`
  );
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function parseQueryString(value: string): Record<string, string> {
  const params = new URLSearchParams(value);
  return Object.fromEntries(params.entries());
}

function getTitle(html: string): string | null {
  return html.match(/<title>(.+?)<\/title>/)?.[1] ?? null;
}

function getCsrf(html: string): string {
  const token = html.match(/name="_csrf"\s+value="(.+?)"/)?.[1];
  if (!token) throw new GarminError("Garmin CSRF token introuvable.", 502, "garmin_sso_unexpected");
  return token;
}

function getTicket(html: string): string {
  const ticket = html.match(/embed\?ticket=([^"]+)"/)?.[1];
  if (!ticket) throw new GarminError("Ticket Garmin introuvable apres login.", 502, "garmin_sso_unexpected");
  return ticket;
}

function dateFromUnixSeconds(seconds: number): string {
  return new Date(seconds * 1000).toISOString();
}

function numberOrNull(value: unknown): number | null {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function firstNumber(...values: unknown[]): number | null {
  for (const value of values) {
    const number = numberOrNull(value);
    if (number != null) return number;
  }
  return null;
}

function nested(value: unknown, path: string): unknown {
  let current = value as Record<string, unknown> | null;
  for (const part of path.split(".")) {
    if (!current || typeof current !== "object") return null;
    current = current[part] as Record<string, unknown> | null;
  }
  return current;
}

function timestampToIso(value: unknown): string | null {
  const number = numberOrNull(value);
  if (number == null || number <= 0) return null;
  return new Date(number).toISOString();
}

function garminDateToIso(value: unknown, utc = false): string | null {
  if (!value || typeof value !== "string") return null;
  if (value.includes("T")) return utc && !/[zZ]|[+-]\d\d:\d\d$/.test(value) ? `${value}Z` : value;
  return `${value.replace(" ", "T")}${utc ? "Z" : ""}`;
}

function todayString(offsetDays = 0): string {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - offsetDays);
  return date.toISOString().slice(0, 10);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

class CookieJar {
  private cookies = new Map<string, string>();

  header(): string {
    return [...this.cookies.entries()].map(([key, value]) => `${key}=${value}`).join("; ");
  }

  ingest(headers: Headers): void {
    const getSetCookie = (headers as Headers & { getSetCookie?: () => string[] }).getSetCookie;
    const values = typeof getSetCookie === "function"
      ? getSetCookie.call(headers)
      : (headers.get("set-cookie") ? [headers.get("set-cookie") as string] : []);
    for (const header of values) {
      for (const part of splitSetCookieHeader(header)) {
        const pair = part.split(";", 1)[0];
        const index = pair.indexOf("=");
        if (index <= 0) continue;
        this.cookies.set(pair.slice(0, index).trim(), pair.slice(index + 1).trim());
      }
    }
  }
}

function splitSetCookieHeader(header: string): string[] {
  return header.split(/,(?=\s*[^;,]+=)/g).map((value) => value.trim()).filter(Boolean);
}

class GarminSsoClient {
  private jar = new CookieJar();
  private lastUrl = "";

  async request(url: string, init: RequestInit = {}): Promise<Response> {
    const headers = new Headers(init.headers);
    headers.set("User-Agent", GARMIN_USER_AGENT);
    if (this.jar.header()) headers.set("Cookie", this.jar.header());
    const response = await fetch(url, { ...init, headers, redirect: "follow" });
    this.jar.ingest(response.headers);
    this.lastUrl = response.url;
    if (!response.ok) {
      throw new GarminError(
        `Garmin SSO HTTP ${response.status}`,
        response.status === 401 || response.status === 403 ? 401 : 502,
        "garmin_sso_http",
      );
    }
    return response;
  }

  referer(): string {
    return this.lastUrl;
  }
}

async function fetchConsumer(): Promise<OAuthConsumer> {
  if (consumerCache) return consumerCache;
  const response = await fetch(OAUTH_CONSUMER_URL);
  if (!response.ok) {
    throw new GarminError(
      `Garmin OAuth consumer indisponible: ${response.status}`,
      502,
      "garmin_oauth_consumer_unavailable",
    );
  }
  consumerCache = await response.json() as OAuthConsumer;
  return consumerCache;
}

async function hmacSha1(key: string, value: string): Promise<string> {
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(key),
    { name: "HMAC", hash: "SHA-1" },
    false,
    ["sign"],
  );
  return bytesToBase64(new Uint8Array(
    await crypto.subtle.sign("HMAC", cryptoKey, new TextEncoder().encode(value)),
  ));
}

async function oauthHeader(
  method: string,
  url: string,
  consumer: OAuthConsumer,
  token?: OAuth1Token,
  bodyParams: Record<string, string> = {},
): Promise<string> {
  const parsed = new URL(url);
  const oauthParams: Record<string, string> = {
    oauth_consumer_key: consumer.consumer_key,
    oauth_nonce: crypto.randomUUID().replaceAll("-", ""),
    oauth_signature_method: "HMAC-SHA1",
    oauth_timestamp: String(Math.floor(Date.now() / 1000)),
    oauth_version: "1.0",
  };
  if (token?.oauth_token) oauthParams.oauth_token = token.oauth_token;

  const signatureParams: [string, string][] = [];
  parsed.searchParams.forEach((value, key) => signatureParams.push([key, value]));
  Object.entries(bodyParams).forEach(([key, value]) => signatureParams.push([key, value]));
  Object.entries(oauthParams).forEach(([key, value]) => signatureParams.push([key, value]));
  signatureParams.sort(([aKey, aValue], [bKey, bValue]) =>
    aKey === bKey ? aValue.localeCompare(bValue) : aKey.localeCompare(bKey)
  );

  const normalized = signatureParams
    .map(([key, value]) => `${rfc3986(key)}=${rfc3986(value)}`)
    .join("&");
  const baseUrl = `${parsed.origin}${parsed.pathname}`;
  const baseString = [
    method.toUpperCase(),
    rfc3986(baseUrl),
    rfc3986(normalized),
  ].join("&");
  const signingKey = `${rfc3986(consumer.consumer_secret)}&${rfc3986(token?.oauth_token_secret ?? "")}`;
  oauthParams.oauth_signature = await hmacSha1(signingKey, baseString);

  return "OAuth " + Object.entries(oauthParams)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `${rfc3986(key)}="${rfc3986(value)}"`)
    .join(", ");
}

async function signedOAuthFetch(
  method: string,
  url: string,
  token?: OAuth1Token,
  bodyParams: Record<string, string> = {},
): Promise<Response> {
  const consumer = await fetchConsumer();
  const headers = new Headers({
    "Authorization": await oauthHeader(method, url, consumer, token, bodyParams),
    "User-Agent": GARMIN_USER_AGENT,
  });
  let body: URLSearchParams | undefined;
  if (method !== "GET") {
    headers.set("Content-Type", "application/x-www-form-urlencoded");
    body = new URLSearchParams(bodyParams);
  }
  const response = await fetch(url, { method, headers, body });
  if (!response.ok) {
    throw new GarminError(
      `Garmin OAuth HTTP ${response.status}: ${await response.text()}`,
      response.status === 401 || response.status === 403 ? 401 : response.status === 429 ? 429 : 502,
      "garmin_oauth_http",
    );
  }
  return response;
}

async function getOAuth1(ticket: string): Promise<OAuth1Token> {
  const baseUrl = `${CONNECT_API_BASE}/oauth-service/oauth/preauthorized`;
  const url = `${baseUrl}?ticket=${encodeURIComponent(ticket)}&login-url=${encodeURIComponent(`${SSO_BASE}/embed`)}&accepts-mfa-tokens=true`;
  const response = await signedOAuthFetch("GET", url);
  return { ...parseQueryString(await response.text()), domain: DOMAIN } as OAuth1Token;
}

async function exchangeOAuth2(oauth1: OAuth1Token): Promise<OAuth2Token> {
  const bodyParams = oauth1.mfa_token ? { mfa_token: oauth1.mfa_token } : {};
  const response = await signedOAuthFetch(
    "POST",
    `${CONNECT_API_BASE}/oauth-service/oauth/exchange/user/2.0`,
    oauth1,
    bodyParams,
  );
  const token = await response.json() as Omit<OAuth2Token, "expires_at" | "refresh_token_expires_at"> & {
    expires_at?: number;
    refresh_token_expires_at?: number;
  };
  const now = Math.floor(Date.now() / 1000);
  return {
    ...token,
    expires_at: token.expires_at ?? now + Number(token.expires_in),
    refresh_token_expires_at: token.refresh_token_expires_at ??
      now + Number(token.refresh_token_expires_in),
  };
}

export async function loginGarmin(
  email: string,
  password: string,
  mfaCode?: string | null,
): Promise<GarminLoginResult> {
  const client = new GarminSsoClient();
  const ssoEmbedParams = new URLSearchParams({
    id: "gauth-widget",
    embedWidget: "true",
    gauthHost: SSO_BASE,
  });
  const signinParams = new URLSearchParams({
    id: "gauth-widget",
    embedWidget: "true",
    gauthHost: `${SSO_BASE}/embed`,
    service: `${SSO_BASE}/embed`,
    source: `${SSO_BASE}/embed`,
    redirectAfterAccountLoginUrl: `${SSO_BASE}/embed`,
    redirectAfterAccountCreationUrl: `${SSO_BASE}/embed`,
  });

  await client.request(`${SSO_BASE}/embed?${ssoEmbedParams}`);
  let response = await client.request(`${SSO_BASE}/signin?${signinParams}`, {
    headers: { "referer": client.referer() },
  });
  let html = await response.text();
  let csrf = getCsrf(html);

  response = await client.request(`${SSO_BASE}/signin?${signinParams}`, {
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      "referer": client.referer(),
    },
    body: new URLSearchParams({
      username: email,
      password,
      embed: "true",
      _csrf: csrf,
    }),
  });
  html = await response.text();
  let title = getTitle(html);

  if (title?.includes("MFA")) {
    if (!mfaCode) return { needs_mfa: true };
    csrf = getCsrf(html);
    response = await client.request(`${SSO_BASE}/verifyMFA/loginEnterMfaCode?${signinParams}`, {
      method: "POST",
      headers: {
        "content-type": "application/x-www-form-urlencoded",
        "referer": client.referer(),
      },
      body: new URLSearchParams({
        "mfa-code": mfaCode,
        embed: "true",
        _csrf: csrf,
        fromPage: "setupEnterMfaCode",
      }),
    });
    html = await response.text();
    title = getTitle(html);
  }

  if (title !== "Success") {
    throw new GarminError(
      `Login Garmin refuse: ${title ?? "titre inconnu"}`,
      401,
      "garmin_login_rejected",
    );
  }
  const oauth1 = await getOAuth1(getTicket(html));
  const oauth2 = await exchangeOAuth2(oauth1);
  return { token: { oauth1, oauth2, domain: DOMAIN } };
}

export class GarminClient {
  constructor(public token: GarminToken) {}

  isOAuth2Expired(): boolean {
    return this.token.oauth2.expires_at < Math.floor(Date.now() / 1000) + 60;
  }

  async refreshOAuth2(): Promise<void> {
    this.token.oauth2 = await exchangeOAuth2(this.token.oauth1);
  }

  async connectApi<T = unknown>(path: string, init: RequestInit = {}): Promise<T | null> {
    if (this.isOAuth2Expired()) await this.refreshOAuth2();
    const response = await this.request(path, init);
    if (response.status === 204) return null;
    return await response.json() as T;
  }

  async download(path: string): Promise<Uint8Array> {
    if (this.isOAuth2Expired()) await this.refreshOAuth2();
    const response = await this.request(path);
    return new Uint8Array(await response.arrayBuffer());
  }

  private async request(path: string, init: RequestInit = {}): Promise<Response> {
    const headers = new Headers(init.headers);
    headers.set("Authorization", `${this.token.oauth2.token_type[0].toUpperCase()}${this.token.oauth2.token_type.slice(1)} ${this.token.oauth2.access_token}`);
    headers.set("User-Agent", GARMIN_USER_AGENT);
    const response = await fetch(`${CONNECT_API_BASE}${path}`, { ...init, headers });
    if (!response.ok) {
      throw new GarminError(
        `Garmin Connect API HTTP ${response.status} on ${path}`,
        response.status === 401 || response.status === 403 ? 401 : response.status === 429 ? 429 : 502,
        "garmin_connect_http",
      );
    }
    return response;
  }
}

export async function storeGarminToken(
  serviceClient: SupabaseClient,
  userId: string,
  token: GarminToken,
  profile: Record<string, unknown> | null,
  email?: string | null,
): Promise<void> {
  const { error } = await serviceClient.from("external_auth_tokens").upsert({
    user_id: userId,
    provider: "garmin",
    provider_user_id: String(profile?.profileId ?? profile?.userProfileId ?? profile?.userName ?? ""),
    display_name: String(profile?.displayName ?? profile?.fullName ?? profile?.userName ?? "Garmin"),
    email: email ?? null,
    access_token_encrypted: await encryptSecret(token),
    refresh_token_encrypted: null,
    expires_at: dateFromUnixSeconds(token.oauth2.expires_at),
    token_payload: {
      token_type: "garth_ts",
      refresh_token_expires_at: token.oauth2.refresh_token_expires_at,
    },
    last_sync_at: new Date().toISOString(),
  }, { onConflict: "user_id,provider" });
  if (error) throw error;
}

export async function loadGarminClient(
  serviceClient: SupabaseClient,
  userId: string,
): Promise<{ client: GarminClient; tokenRowId: string }> {
  const { data, error } = await serviceClient
    .from("external_auth_tokens")
    .select("id,access_token_encrypted")
    .eq("user_id", userId)
    .eq("provider", "garmin")
    .single();
  if (error || !data?.access_token_encrypted) throw new Error("Compte Garmin non connecte.");

  const token = await decryptSecret<GarminToken>(data.access_token_encrypted);
  const client = new GarminClient(token);
  if (client.isOAuth2Expired()) {
    await client.refreshOAuth2();
    await serviceClient.from("external_auth_tokens").update({
      access_token_encrypted: await encryptSecret(client.token),
      expires_at: dateFromUnixSeconds(client.token.oauth2.expires_at),
      token_payload: {
        token_type: "garth_ts",
        refresh_token_expires_at: client.token.oauth2.refresh_token_expires_at,
      },
    }).eq("id", data.id);
  }
  return { client, tokenRowId: data.id };
}

export async function fetchGarminDay(
  client: GarminClient,
  username: string,
  day: string,
): Promise<Record<string, unknown> | null> {
  const data: Record<string, unknown> = {};

  const [trainingReadiness, hrv, sleepData, heartRate, summary, weight, maxMetrics, trainingStatus] =
    await Promise.allSettled([
      client.connectApi(`/metrics-service/metrics/trainingreadiness/${day}`),
      client.connectApi(`/hrv-service/hrv/${day}`),
      client.connectApi(`/wellness-service/wellness/dailySleepData/${encodeURIComponent(username)}?nonSleepBufferMinutes=60&date=${day}`),
      client.connectApi(`/wellness-service/wellness/dailyHeartRate/?date=${day}`),
      client.connectApi(`/usersummary-service/usersummary/daily/?calendarDate=${day}`),
      client.connectApi(`/weight-service/weight/dayview/${day}`),
      client.connectApi(`/metrics-service/metrics/maxmet/daily/${day}/${day}`),
      client.connectApi(`/mobile-gateway/usersummary/trainingstatus/latest/${day}`),
    ]);

  const trValue = trainingReadiness.status === "fulfilled" ? trainingReadiness.value : null;
  if (Array.isArray(trValue) && trValue.length > 0) {
    const entry = trValue.find((item) =>
      (item as Record<string, unknown>).inputContext === "AFTER_WAKEUP_RESET"
    ) ?? trValue[0];
    data.training_readiness = firstNumber((entry as Record<string, unknown>).score);
  }

  const hrvValue = hrv.status === "fulfilled" ? hrv.value : null;
  data.hrv_rmssd = firstNumber(nested(hrvValue, "hrvSummary.lastNightAvg"));

  const sleepValue = sleepData.status === "fulfilled" ? sleepData.value : null;
  const sleepDto = nested(sleepValue, "dailySleepDTO") as Record<string, unknown> | null;
  if (sleepDto?.id) {
    data.sleep_score = firstNumber(nested(sleepDto, "sleepScores.overall.value"));
    data.sleep_duration_min = firstNumber(sleepDto.sleepTimeSeconds) != null
      ? Math.round(Number(sleepDto.sleepTimeSeconds) / 60)
      : null;
    data.deep_sleep_seconds = firstNumber(sleepDto.deepSleepSeconds);
    data.light_sleep_seconds = firstNumber(sleepDto.lightSleepSeconds);
    data.rem_sleep_seconds = firstNumber(sleepDto.remSleepSeconds);
    data.awake_sleep_seconds = firstNumber(sleepDto.awakeSleepSeconds);
    data.sleep_start_time = timestampToIso(sleepDto.sleepStartTimestampGMT);
    data.sleep_end_time = timestampToIso(sleepDto.sleepEndTimestampGMT);
    data.average_respiration = firstNumber(sleepDto.averageRespirationValue);
    data.avg_sleep_stress = firstNumber(sleepDto.avgSleepStress);
    data.spo2 = firstNumber(sleepDto.averageSpO2Value);
  }

  const heartValue = heartRate.status === "fulfilled" ? heartRate.value : null;
  data.resting_hr = firstNumber(nested(heartValue, "restingHeartRate"));

  const summaryValue = summary.status === "fulfilled" ? summary.value as Record<string, unknown> | null : null;
  data.stress_score = firstNumber(summaryValue?.averageStressLevel);
  data.body_battery_max = firstNumber(summaryValue?.bodyBatteryHighestValue);
  data.body_battery_min = firstNumber(summaryValue?.bodyBatteryLowestValue);
  data.total_steps = firstNumber(summaryValue?.totalSteps);
  data.total_kilocalories = firstNumber(summaryValue?.totalKilocalories);
  data.active_kilocalories = firstNumber(summaryValue?.activeKilocalories);
  if (data.spo2 == null) data.spo2 = firstNumber(summaryValue?.averageSpO2);

  const weightValue = weight.status === "fulfilled" ? weight.value : null;
  const weightEntry = Array.isArray(nested(weightValue, "dateWeightList"))
    ? (nested(weightValue, "dateWeightList") as Record<string, unknown>[])[0]
    : null;
  const weightGrams = firstNumber(weightEntry?.weight);
  if (weightGrams != null) data.weight_kg = weightGrams / 1000;

  data.vo2max_estimated = extractVo2Max(maxMetrics.status === "fulfilled" ? maxMetrics.value : null);
  data.training_status = extractTrainingStatus(trainingStatus.status === "fulfilled" ? trainingStatus.value : null);

  for (const key of Object.keys(data)) {
    if (data[key] == null) delete data[key];
  }
  return Object.keys(data).length > 0 ? data : null;
}

function extractVo2Max(value: unknown): number | null {
  if (Array.isArray(value)) {
    for (const item of value) {
      const candidate = firstNumber(
        nested(item, "generic.value"),
        nested(item, "value"),
        nested(item, "vo2Max"),
      );
      if (candidate != null) return candidate;
    }
  }
  return firstNumber(nested(value, "vo2Max"), nested(value, "value"));
}

function extractTrainingStatus(value: unknown): string | null {
  const payload = nested(value, "mostRecentTrainingStatus.payload.latestTrainingStatusData");
  if (!payload || typeof payload !== "object") return null;
  for (const device of Object.values(payload as Record<string, unknown>)) {
    if (!device || typeof device !== "object") continue;
    const record = device as Record<string, unknown>;
    return String(
      record.trainingStatusFeedbackPhrase ??
        record.training_status_feedback_phrase ??
        record.trainingStatus ??
        record.training_status ??
        "",
    ) || null;
  }
  return null;
}

export async function syncGarminDaily(
  serviceClient: SupabaseClient,
  userId: string,
  daysBack: number,
  startOffsetDays = 0,
  onProgress?: (done: number, total: number) => Promise<void>,
): Promise<{ days_synced: number; errors: number; total_requested: number }> {
  const { client, tokenRowId } = await loadGarminClient(serviceClient, userId);
  const profile = await client.connectApi<Record<string, unknown>>("/userprofile-service/socialProfile");
  const username = String(profile?.userName ?? "");
  if (!username) throw new Error("Profil Garmin sans username.");

  const total = Math.max(1, Math.min(Math.round(daysBack), 90));
  let daysSynced = 0;
  let errors = 0;
  for (let index = 0; index < total; index += 1) {
    const day = todayString(startOffsetDays + index);
    try {
      const dayData = await fetchGarminDay(client, username, day);
      if (dayData) {
        const { error } = await serviceClient.from("garmin_daily").upsert({
          user_id: userId,
          date: day,
          ...dayData,
          raw_summary: { synced_by: "garmin-sync-edge" },
          updated_at: new Date().toISOString(),
        }, { onConflict: "user_id,date" });
        if (error) throw error;
        daysSynced += 1;
      }
    } catch {
      errors += 1;
    }
    if (onProgress) await onProgress(index + 1, total);
    if (index < total - 1) await sleep(120);
  }

  await serviceClient.from("external_auth_tokens").update({
    access_token_encrypted: await encryptSecret(client.token),
    expires_at: dateFromUnixSeconds(client.token.oauth2.expires_at),
    last_sync_at: new Date().toISOString(),
  }).eq("id", tokenRowId);

  return { days_synced: daysSynced, errors, total_requested: total };
}

export async function listGarminActivities(
  client: GarminClient,
  daysBack: number,
): Promise<Record<string, unknown>[]> {
  const cutoff = Date.now() - daysBack * 24 * 60 * 60 * 1000;
  const all: Record<string, unknown>[] = [];
  const pageSize = 20;
  let start = 0;

  while (start <= 300) {
    const page = await client.connectApi<Record<string, unknown>[]>(
      `/activitylist-service/activities/search/activities?limit=${pageSize}&start=${start}`,
    );
    if (!Array.isArray(page) || page.length === 0) break;
    all.push(...page);
    const last = page[page.length - 1];
    const lastDate = Date.parse(garminDateToIso(last.startTimeGMT, true) ?? garminDateToIso(last.startTimeLocal) ?? "");
    if (Number.isFinite(lastDate) && lastDate < cutoff) break;
    start += pageSize;
    await sleep(120);
  }

  return all.filter((activity) => {
    const date = Date.parse(garminDateToIso(activity.startTimeGMT, true) ?? garminDateToIso(activity.startTimeLocal) ?? "");
    return !Number.isFinite(date) || date >= cutoff;
  });
}

export function mapGarminActivity(activity: Record<string, unknown>, userId: string): Record<string, unknown> {
  const typeKey = String(nested(activity, "activityType.typeKey") ?? "running");
  const sportType = mapGarminSport(typeKey);
  const distance = firstNumber(activity.distance) ?? 0;
  const movingTime = Math.round(firstNumber(activity.movingDuration, activity.duration) ?? 0);
  return {
    user_id: userId,
    source: "garmin",
    garmin_activity_id: firstNumber(activity.activityId),
    name: activity.activityName ?? "Garmin Activity",
    sport_type: sportType,
    activity_type: sportType,
    start_date_utc: garminDateToIso(activity.startTimeGMT, true) ?? garminDateToIso(activity.startTimeLocal),
    timezone: null,
    location_city: activity.locationName ?? null,
    location_country: null,
    distance_m: distance,
    moving_time_s: movingTime,
    elapsed_time_s: Math.round(firstNumber(activity.elapsedDuration, activity.duration) ?? movingTime),
    elev_gain_m: firstNumber(activity.elevationGain),
    avg_speed_m_s: firstNumber(activity.averageSpeed),
    max_speed_m_s: firstNumber(activity.maxSpeed),
    avg_heartrate_bpm: firstNumber(activity.averageHR, activity.averageHr),
    max_heartrate_bpm: firstNumber(activity.maxHR, activity.maxHr),
    avg_cadence: firstNumber(activity.averageRunningCadenceInStepsPerMinute),
    calories_kcal: firstNumber(activity.calories),
    start_latlng: buildLatLng(activity.startLatitude, activity.startLongitude),
    end_latlng: buildLatLng(activity.endLatitude, activity.endLongitude),
    has_garmin: true,
    raw_summary: activity,
    updated_at: new Date().toISOString(),
  };
}

function buildLatLng(lat: unknown, lon: unknown): [number, number] | null {
  const latNumber = firstNumber(lat);
  const lonNumber = firstNumber(lon);
  return latNumber != null && lonNumber != null ? [latNumber, lonNumber] : null;
}

function mapGarminSport(typeKey: string): string {
  const map: Record<string, string> = {
    running: "Run",
    trail_running: "TrailRun",
    treadmill_running: "Run",
    cycling: "Ride",
    indoor_cycling: "Ride",
    mountain_biking: "Ride",
    gravel_cycling: "Ride",
    swimming: "Swim",
    open_water_swimming: "Swim",
    pool_swimming: "Swim",
    walking: "Walk",
    hiking: "Walk",
  };
  return map[typeKey] ?? "Run";
}
