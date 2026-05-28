import "dotenv/config";
import { Buffer } from "node:buffer";
import { execFileSync } from "node:child_process";
import path from "node:path";
import process from "node:process";
import { createClient } from "@supabase/supabase-js";

type SqliteRow = Record<string, unknown>;

const env = {
  sqlitePath: process.env.SQLITE_LEGACY_PATH
    ?? path.resolve(process.cwd(), "../../backend/stridedelta.db"),
  supabaseUrl: mustEnv("SUPABASE_URL"),
  serviceRoleKey: mustEnv("SUPABASE_SERVICE_ROLE_KEY"),
  userIdMapJson: process.env.SUPABASE_USER_ID_MAP_JSON || "{}",
};

const supabase = createClient(env.supabaseUrl, env.serviceRoleKey, {
  auth: { autoRefreshToken: false, persistSession: false },
});

async function main(): Promise<void> {
  const userMap = new Map(Object.entries(JSON.parse(env.userIdMapJson) as Record<string, string>));
  const routes = sqliteJson<SqliteRow>(`
    select
      id,
      user_id,
      is_public,
      name,
      filename,
      distance_km,
      elevation_gain_m,
      created_at,
      updated_at,
      hex(gpx_data) as gpx_hex
    from gpxroute
    order by created_at asc
  `);

  const routeOwners = new Map<string, { userId: string | null; isPublic: boolean }>();
  let migratedRoutes = 0;
  let skippedRoutes = 0;
  let routeBytes = 0;

  for (const row of routes) {
    const routeId = stringValue(row.id);
    if (!routeId) {
      skippedRoutes += 1;
      continue;
    }

    const legacyUserId = stringValue(row.user_id);
    const userId = legacyUserId ? userMap.get(legacyUserId) ?? null : null;
    const isPublic = Boolean(Number(row.is_public)) || !legacyUserId;
    if (!userId && !isPublic) {
      skippedRoutes += 1;
      continue;
    }

    const filename = safeStorageName(stringValue(row.filename) ?? "route.gpx");
    const storagePrefix = userId ?? "public";
    const storagePath = `${storagePrefix}/routes/${routeId}-${filename}`;
    const gpxBuffer = bufferFromHex(row.gpx_hex);
    if (!gpxBuffer) {
      skippedRoutes += 1;
      continue;
    }

    await upload("gpx-files", storagePath, gpxBuffer, "application/gpx+xml");
    routeBytes += gpxBuffer.byteLength;

    const { error } = await supabase.from("gpx_routes").upsert({
      id: routeId,
      user_id: userId,
      name: row.name ?? filename.replace(/\.gpx$/i, ""),
      filename,
      is_public: isPublic,
      distance_km: nullableNumber(row.distance_km),
      elevation_gain_m: nullableNumber(row.elevation_gain_m),
      gpx_storage_path: storagePath,
      metadata: { migrated_from: "sqlite_gpxroute" },
      created_at: row.created_at ?? new Date().toISOString(),
      updated_at: row.updated_at ?? new Date().toISOString(),
    }, { onConflict: "id" });
    if (error) throw error;

    routeOwners.set(routeId, { userId, isPublic });
    migratedRoutes += 1;
  }

  const attachments = sqliteJson<SqliteRow>(`
    select
      id,
      route_id,
      name,
      filename,
      mime_type,
      kind,
      created_at,
      hex(data) as data_hex
    from gpxattachment
    order by created_at asc
  `);

  let migratedAttachments = 0;
  let skippedAttachments = 0;
  let attachmentBytes = 0;

  for (const row of attachments) {
    const id = stringValue(row.id);
    const routeId = stringValue(row.route_id);
    if (!id || !routeId) {
      skippedAttachments += 1;
      continue;
    }

    const owner = routeOwners.get(routeId) ?? await readRouteOwner(routeId);
    if (!owner?.userId && !owner?.isPublic) {
      skippedAttachments += 1;
      continue;
    }

    const filename = safeStorageName(stringValue(row.filename) ?? `${id}.bin`);
    const mimeType = stringValue(row.mime_type) ?? contentTypeForFile(filename);
    const storagePrefix = owner.userId ?? "public";
    const storagePath = `${storagePrefix}/attachments/${routeId}-${id}-${filename}`;
    const data = bufferFromHex(row.data_hex);
    if (!data) {
      skippedAttachments += 1;
      continue;
    }

    await upload("gpx-files", storagePath, data, mimeType);
    attachmentBytes += data.byteLength;

    const { error } = await supabase.from("gpx_route_attachments").upsert({
      id,
      route_id: routeId,
      user_id: owner.userId,
      name: row.name ?? filename,
      filename,
      mime_type: mimeType,
      kind: row.kind ?? kindForAttachment(filename, mimeType),
      storage_path: storagePath,
      created_at: row.created_at ?? new Date().toISOString(),
    }, { onConflict: "id" });
    if (error) throw error;

    migratedAttachments += 1;
  }

  console.log(JSON.stringify({
    sqlite_path: env.sqlitePath,
    routes: {
      source: routes.length,
      migrated: migratedRoutes,
      skipped: skippedRoutes,
      bytes: routeBytes,
    },
    attachments: {
      source: attachments.length,
      migrated: migratedAttachments,
      skipped: skippedAttachments,
      bytes: attachmentBytes,
    },
  }, null, 2));
}

function sqliteJson<T>(sql: string): T[] {
  const output = execFileSync("sqlite3", ["-json", env.sqlitePath, sql], {
    encoding: "utf8",
    maxBuffer: 128 * 1024 * 1024,
  });
  return output.trim() ? JSON.parse(output) as T[] : [];
}

async function readRouteOwner(routeId: string): Promise<{ userId: string | null; isPublic: boolean } | null> {
  const { data, error } = await supabase
    .from("gpx_routes")
    .select("user_id,is_public")
    .eq("id", routeId)
    .maybeSingle();
  if (error) throw error;
  return data ? { userId: data.user_id, isPublic: Boolean(data.is_public) } : null;
}

async function upload(bucket: string, storagePath: string, data: Buffer, contentType: string): Promise<void> {
  const { error } = await supabase.storage.from(bucket).upload(storagePath, data, {
    contentType,
    upsert: true,
  });
  if (error) throw error;
}

function bufferFromHex(value: unknown): Buffer | null {
  const hex = stringValue(value);
  if (!hex) return null;
  const buffer = Buffer.from(hex, "hex");
  return buffer.byteLength > 0 ? buffer : null;
}

function nullableNumber(value: unknown): number | null {
  if (value == null) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function stringValue(value: unknown): string | null {
  if (value == null) return null;
  return String(value);
}

function safeStorageName(name: string): string {
  return name.replace(/[^a-zA-Z0-9._-]+/g, "_").slice(0, 140) || "file.bin";
}

function contentTypeForFile(filename: string): string {
  const lower = filename.toLowerCase();
  if (lower.endsWith(".pdf")) return "application/pdf";
  if (lower.endsWith(".gpx")) return "application/gpx+xml";
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
  if (lower.endsWith(".webp")) return "image/webp";
  return "application/octet-stream";
}

function kindForAttachment(filename: string, mimeType: string): string {
  const lower = filename.toLowerCase();
  if (mimeType === "application/pdf" || lower.endsWith(".pdf")) return "pdf";
  if (mimeType.startsWith("image/")) return "image";
  if (mimeType === "application/gpx+xml" || lower.endsWith(".gpx")) return "gpx";
  return "other";
}

function mustEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing ${name}`);
  return value;
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
