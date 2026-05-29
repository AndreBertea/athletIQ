/**
 * Encodage polyline Google (précision 1e5) pour stocker une trace GPS
 * légère sur la ligne activité. Le frontend la décode via `decodePolyline`
 * (client-app/src/routes/activity-detail.tsx) — même algo, ordre lat/lng.
 *
 * But : la carte du détail d'activité s'affiche instantanément depuis cette
 * chaîne, sans attendre le téléchargement du JSON streams (storage).
 */

/** Limite de points conservés (downsampling) — assez pour une trace fluide. */
const MAX_POINTS = 500;

function encodeValue(value: number): string {
  let v = value < 0 ? ~(value << 1) : value << 1;
  let out = "";
  while (v >= 0x20) {
    out += String.fromCharCode((0x20 | (v & 0x1f)) + 63);
    v >>= 5;
  }
  out += String.fromCharCode(v + 63);
  return out;
}

/**
 * Encode une suite de coordonnées `[lat, lng]` (ordre des streams Garmin)
 * en polyline Google. Les éléments null/invalides sont ignorés. La trace est
 * sous-échantillonnée à MAX_POINTS pour rester légère.
 *
 * Retourne `null` s'il y a moins de 2 points valides.
 */
export function encodePolyline(
  coords: Array<[number, number] | null | undefined> | null | undefined,
): string | null {
  if (!Array.isArray(coords)) return null;

  const valid: [number, number][] = [];
  for (const pair of coords) {
    if (
      Array.isArray(pair) &&
      Number.isFinite(pair[0]) &&
      Number.isFinite(pair[1])
    ) {
      valid.push([pair[0], pair[1]]);
    }
  }
  if (valid.length < 2) return null;

  // Downsampling régulier en gardant toujours le dernier point.
  const step = Math.max(1, Math.ceil(valid.length / MAX_POINTS));
  const sampled: [number, number][] = [];
  for (let i = 0; i < valid.length; i += step) sampled.push(valid[i]);
  const last = valid[valid.length - 1];
  if (sampled[sampled.length - 1] !== last) sampled.push(last);

  let prevLat = 0;
  let prevLng = 0;
  let result = "";
  for (const [lat, lng] of sampled) {
    const latE5 = Math.round(lat * 1e5);
    const lngE5 = Math.round(lng * 1e5);
    result += encodeValue(latE5 - prevLat);
    result += encodeValue(lngE5 - prevLng);
    prevLat = latE5;
    prevLng = lngE5;
  }
  return result;
}
