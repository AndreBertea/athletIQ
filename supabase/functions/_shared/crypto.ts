const encoder = new TextEncoder();
const decoder = new TextDecoder();

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

function base64UrlEncode(value: string): string {
  return btoa(value).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function base64UrlDecode(value: string): string {
  const padded = value.replaceAll("-", "+").replaceAll("_", "/").padEnd(
    Math.ceil(value.length / 4) * 4,
    "=",
  );
  return atob(padded);
}

async function hmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

async function aesKey(secret: string): Promise<CryptoKey> {
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(secret));
  return crypto.subtle.importKey(
    "raw",
    digest,
    { name: "AES-GCM" },
    false,
    ["encrypt", "decrypt"],
  );
}

export async function encryptSecret(value: unknown): Promise<string> {
  const secret = Deno.env.get("ENCRYPTION_KEY");
  if (!secret) throw new Error("Missing ENCRYPTION_KEY");
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const plaintext = encoder.encode(JSON.stringify(value));
  const encrypted = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await aesKey(secret), plaintext),
  );
  const combined = new Uint8Array(iv.length + encrypted.length);
  combined.set(iv, 0);
  combined.set(encrypted, iv.length);
  return bytesToBase64(combined);
}

export async function decryptSecret<T = unknown>(value: string): Promise<T> {
  const secret = Deno.env.get("ENCRYPTION_KEY");
  if (!secret) throw new Error("Missing ENCRYPTION_KEY");
  const combined = base64ToBytes(value);
  const iv = combined.slice(0, 12);
  const payload = combined.slice(12);
  const decrypted = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv },
    await aesKey(secret),
    payload,
  );
  return JSON.parse(decoder.decode(decrypted)) as T;
}

export async function signState(payload: Record<string, unknown>): Promise<string> {
  const secret = Deno.env.get("ENCRYPTION_KEY");
  if (!secret) throw new Error("Missing ENCRYPTION_KEY");
  const encodedPayload = base64UrlEncode(JSON.stringify(payload));
  const signature = new Uint8Array(
    await crypto.subtle.sign("HMAC", await hmacKey(secret), encoder.encode(encodedPayload)),
  );
  return `${encodedPayload}.${bytesToBase64(signature).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "")}`;
}

export async function verifyState<T extends Record<string, unknown>>(state: string): Promise<T> {
  const secret = Deno.env.get("ENCRYPTION_KEY");
  if (!secret) throw new Error("Missing ENCRYPTION_KEY");
  const [encodedPayload, encodedSignature] = state.split(".");
  if (!encodedPayload || !encodedSignature) throw new Error("Invalid OAuth state");

  const signature = base64ToBytes(
    encodedSignature.replaceAll("-", "+").replaceAll("_", "/").padEnd(
      Math.ceil(encodedSignature.length / 4) * 4,
      "=",
    ),
  );

  const valid = await crypto.subtle.verify(
    "HMAC",
    await hmacKey(secret),
    signature,
    encoder.encode(encodedPayload),
  );
  if (!valid) throw new Error("Invalid OAuth state signature");

  const payload = JSON.parse(base64UrlDecode(encodedPayload)) as T;
  const ts = Number(payload.ts ?? 0);
  if (!ts || Date.now() - ts > 15 * 60 * 1000) {
    throw new Error("Expired OAuth state");
  }
  return payload;
}
