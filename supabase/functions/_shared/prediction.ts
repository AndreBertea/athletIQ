import type { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

export interface GpxPoint {
  lat: number;
  lon: number;
  ele: number;
  time?: string;
}

export interface SegmentPrediction {
  index: number;
  start_km: number;
  end_km: number;
  distance_km: number;
  elevation_gain_m: number;
  elevation_loss_m: number;
  grade_pct: number;
  altitude_m: number;
  mode: "run" | "walk";
  predicted_time_min: number;
  pace_min_per_km: number;
  cumulative_time_min: number;
  cumulative_distance_km: number;
}

export interface RacePredictionResult {
  engine_version: "v3_hybrid";
  filename: string;
  analysis_mode: string;
  ravito_mode: string;
  history_start_date?: string | null;
  total_distance_km: number;
  total_elevation_gain_m: number;
  moving_time_min: number;
  moving_time_formatted: string;
  total_pause_min: number;
  total_pause_formatted: string;
  total_time_min: number;
  total_time_formatted: string;
  avg_pace: number;
  avg_moving_pace: number;
  segments: SegmentPrediction[];
  ravito_points: RavitoPoint[];
  ravitos: { points: RavitoPoint[]; total_pause_min: number };
  calibration: Record<string, unknown>;
  environment: Record<string, unknown>;
  fatigue: Record<string, unknown>;
  warnings: string[];
}

interface BuildOptions {
  userId: string;
  filename: string;
  analysisMode?: string;
  effortMode?: string;
  ravitoMode?: string;
  weatherMode?: string;
  manualTemperatureC?: number | null;
  historyStartDate?: string | null;
  customRavitos?: RavitoPoint[];
  serviceClient: SupabaseClient;
}

export interface RavitoPoint {
  km: number;
  name: string;
  pause_min: number;
}

interface SegmentGeometry {
  index: number;
  startKm: number;
  endKm: number;
  distanceM: number;
  elevGainM: number;
  elevLossM: number;
  grade: number;
  altitudeM: number;
}

interface AthleteCalibration {
  source: "activities" | "fallback";
  route_profile: "road" | "trail";
  activities_used: number;
  road_activities_used: number;
  trail_activities_used: number;
  power_wkg: number;
  road_power_wkg?: number;
  trail_power_wkg?: number;
  trail_factor: number;
  note?: string;
}

const GPX_MAX_BYTES = 2 * 1024 * 1024;
// Garde-fou de securite uniquement (le runtime Deno encaisse des dizaines de
// milliers de points sans souci). On garde la pleine resolution du GPX pour ne
// pas fausser distance et D+ sur les longues courses.
const MAX_POINTS = 50000;
const MIN_SEGMENT_M = 200;
const MAX_SEGMENT_M = 1000;
const GRADE_CHANGE_CUT = 0.04;
// Seuil anti-bruit GPS (hysteresis) pour le calcul du denivele.
const ELE_THRESHOLD_M = 2;

export function assertGpxSize(sizeBytes: number): void {
  if (sizeBytes > GPX_MAX_BYTES) {
    throw new Error("GPX trop gros: limite MVP 2 MB.");
  }
}

export function parseGpx(gpxText: string): GpxPoint[] {
  // Le runtime Edge (Deno) n'expose pas DOMParser : on parse le GPX par regex.
  // GPX reste un XML regulier ; on extrait chaque trkpt/rtept, auto-fermant ou paire.
  const points: GpxPoint[] = [];
  const pointRe = /<(trkpt|rtept)\b([^>]*?)(?:\/>|>([\s\S]*?)<\/\1\s*>)/gi;
  let match: RegExpExecArray | null;
  while ((match = pointRe.exec(gpxText)) !== null) {
    const attrs = match[2] ?? "";
    const body = match[3] ?? "";
    const lat = Number(attrs.match(/\blat\s*=\s*["']([^"']+)["']/i)?.[1]);
    const lon = Number(attrs.match(/\blon\s*=\s*["']([^"']+)["']/i)?.[1]);
    const eleText = body.match(/<ele[^>]*>([^<]+)<\/ele\s*>/i)?.[1];
    const time = body.match(/<time[^>]*>([^<]+)<\/time\s*>/i)?.[1];
    points.push({
      lat,
      lon,
      ele: eleText == null ? 0 : Number(eleText),
      time: time ?? undefined,
    });
  }

  const valid = points.filter((point) =>
    Number.isFinite(point.lat) &&
    Number.isFinite(point.lon) &&
    Math.abs(point.lat) <= 90 &&
    Math.abs(point.lon) <= 180
  );

  if (valid.length < 2) throw new Error("Le GPX doit contenir au moins 2 points.");
  return downsample(valid, MAX_POINTS);
}

export async function buildRacePrediction(
  gpxText: string,
  options: BuildOptions,
): Promise<RacePredictionResult> {
  const points = parseGpx(gpxText);
  const segments = buildSegments(points);
  if (segments.length === 0) throw new Error("Impossible de segmenter ce GPX.");

  const totalDistanceKm = sum(segments.map((segment) => segment.distanceM)) / 1000;
  const totalElevationGainM = sum(segments.map((segment) => segment.elevGainM));
  const routeProfile = inferRouteProfile(options.analysisMode ?? "auto", totalDistanceKm, totalElevationGainM);
  const calibration = await calibrateAthlete(
    options.serviceClient,
    options.userId,
    routeProfile,
    options.historyStartDate,
  );
  const ravitos = resolveRavitos(totalDistanceKm, options.ravitoMode ?? "auto", options.customRavitos ?? []);
  const manualTemperature = options.manualTemperatureC ?? null;
  const effortMultiplier = effortToMultiplier(options.effortMode ?? "steady");
  const warnings: string[] = [];

  if (points.length >= MAX_POINTS) {
    warnings.push(`GPX très volumineux : échantillonné à ${MAX_POINTS} points (garde-fou de sécurité).`);
  }
  if (calibration.source === "fallback") {
    warnings.push("Calibration historique insuffisante: modèle athlète MVP par défaut utilisé.");
  }

  let cumulativeTimeMin = 0;
  let cumulativeDistanceKm = 0;

  const predictedSegments = segments.map((segment) => {
    const completion = totalDistanceKm > 0 ? cumulativeDistanceKm / totalDistanceKm : 0;
    const altitudeFactor = segment.altitudeM > 1500
      ? 1 + ((segment.altitudeM - 1500) / 1000) * 0.06
      : 1;
    const fatigueFactor = 1 + completion * (routeProfile === "trail" ? 0.20 : 0.12) +
      Math.max(0, segment.elevGainM) * (routeProfile === "trail" ? 0.00018 : 0.00010);
    const temperatureFactor = temperatureToFactor(manualTemperature);
    const mode = segment.grade > 0.16 ? "walk" : "run";
    const cost = mode === "walk" ? minettiWalkCost(segment.grade) : minettiRunCost(segment.grade);
    const powerWkg = Number(calibration.power_wkg) * effortMultiplier;
    const speedMps = clamp(powerWkg / cost / altitudeFactor / fatigueFactor / temperatureFactor, 0.55, 5.2);
    const predictedTimeMin = segment.distanceM / speedMps / 60;

    cumulativeTimeMin += predictedTimeMin;
    cumulativeDistanceKm += segment.distanceM / 1000;

    return {
      index: segment.index,
      start_km: round(segment.startKm, 2),
      end_km: round(segment.endKm, 2),
      distance_km: round(segment.distanceM / 1000, 3),
      elevation_gain_m: round(segment.elevGainM, 0),
      elevation_loss_m: round(segment.elevLossM, 0),
      grade_pct: round(segment.grade * 100, 1),
      altitude_m: round(segment.altitudeM, 0),
      mode,
      predicted_time_min: round(predictedTimeMin, 1),
      pace_min_per_km: round(predictedTimeMin / Math.max(segment.distanceM / 1000, 0.001), 2),
      cumulative_time_min: round(cumulativeTimeMin, 1),
      cumulative_distance_km: round(cumulativeDistanceKm, 2),
    } satisfies SegmentPrediction;
  });

  const movingTimeMin = sum(predictedSegments.map((segment) => segment.predicted_time_min));
  const totalPauseMin = sum(ravitos.map((ravito) => ravito.pause_min));
  const totalTimeMin = movingTimeMin + totalPauseMin;

  return {
    engine_version: "v3_hybrid",
    filename: options.filename,
    analysis_mode: options.analysisMode ?? "auto",
    ravito_mode: options.ravitoMode ?? "auto",
    history_start_date: options.historyStartDate ?? null,
    total_distance_km: round(totalDistanceKm, 2),
    total_elevation_gain_m: round(totalElevationGainM, 0),
    moving_time_min: round(movingTimeMin, 1),
    moving_time_formatted: formatDuration(movingTimeMin),
    total_pause_min: round(totalPauseMin, 1),
    total_pause_formatted: formatDuration(totalPauseMin),
    total_time_min: round(totalTimeMin, 1),
    total_time_formatted: formatDuration(totalTimeMin),
    avg_pace: round(totalTimeMin / Math.max(totalDistanceKm, 0.001), 2),
    avg_moving_pace: round(movingTimeMin / Math.max(totalDistanceKm, 0.001), 2),
    segments: predictedSegments,
    ravito_points: ravitos,
    ravitos: { points: ravitos, total_pause_min: round(totalPauseMin, 1) },
    calibration,
    environment: {
      weather_mode: options.weatherMode ?? "manual",
      temperature_c: manualTemperature,
      temperature_factor: round(temperatureToFactor(manualTemperature), 3),
    },
    fatigue: {
      model: "distance_completion_plus_segment_climb",
      max_distance_penalty_pct: routeProfile === "trail" ? 20 : 12,
    },
    warnings,
  };
}

function buildSegments(points: GpxPoint[]): SegmentGeometry[] {
  const segments: SegmentGeometry[] = [];
  let startIndex = 0;
  let startKm = 0;
  let currentDistanceM = 0;
  let currentGainM = 0;
  let currentLossM = 0;
  let lastGrade = 0;
  let totalDistanceM = 0;
  // Reference d'altitude avec hysteresis : on ne comptabilise D+/D- qu'au-dela
  // du seuil, pour ignorer le bruit GPS tout en gardant la pleine resolution.
  let refEle = points[0]?.ele ?? 0;

  for (let i = 1; i < points.length; i += 1) {
    const prev = points[i - 1];
    const point = points[i];
    const dist = haversine(prev, point);
    if (!Number.isFinite(dist) || dist <= 0) continue;

    currentDistanceM += dist;
    totalDistanceM += dist;
    const deltaEle = point.ele - refEle;
    if (deltaEle >= ELE_THRESHOLD_M) {
      currentGainM += deltaEle;
      refEle = point.ele;
    } else if (deltaEle <= -ELE_THRESHOLD_M) {
      currentLossM += -deltaEle;
      refEle = point.ele;
    }

    const grade = (point.ele - points[startIndex].ele) / Math.max(currentDistanceM, 1);
    const shouldCut =
      currentDistanceM >= MAX_SEGMENT_M ||
      (currentDistanceM >= MIN_SEGMENT_M && Math.abs(grade - lastGrade) >= GRADE_CHANGE_CUT);

    if (shouldCut || i === points.length - 1) {
      segments.push({
        index: segments.length + 1,
        startKm,
        endKm: totalDistanceM / 1000,
        distanceM: currentDistanceM,
        elevGainM: currentGainM,
        elevLossM: currentLossM,
        grade,
        altitudeM: average(points.slice(startIndex, i + 1).map((p) => p.ele)),
      });
      startIndex = i;
      startKm = totalDistanceM / 1000;
      currentDistanceM = 0;
      currentGainM = 0;
      currentLossM = 0;
      lastGrade = grade;
    }
  }

  return segments.filter((segment) => segment.distanceM > 0);
}

async function calibrateAthlete(
  client: SupabaseClient,
  userId: string,
  routeProfile: "road" | "trail",
  historyStartDate?: string | null,
): Promise<AthleteCalibration> {
  let query = client
    .from("activities")
    .select("distance_m,moving_time_s,elev_gain_m,sport_type,start_date_utc")
    .eq("user_id", userId)
    .in("sport_type", ["Run", "TrailRun"])
    .gt("distance_m", 2000)
    .gt("moving_time_s", 600)
    .order("start_date_utc", { ascending: false })
    .limit(200);

  if (historyStartDate) query = query.gte("start_date_utc", historyStartDate);

  const { data, error } = await query;
  if (error) throw error;

  const usable = (data ?? [])
    .map((activity) => {
      const distance = Number(activity.distance_m ?? 0);
      const movingTime = Number(activity.moving_time_s ?? 0);
      const elevGain = Number(activity.elev_gain_m ?? 0);
      if (distance <= 0 || movingTime <= 0) return null;
      const speed = distance / movingTime;
      const climbPenalty = 1 + Math.min(elevGain / Math.max(distance, 1), 0.15) * 1.8;
      return {
        sportType: String(activity.sport_type ?? ""),
        powerWkg: clamp(speed * 3.6 * climbPenalty, 6.5, 13.5),
      };
    })
    .filter((value): value is { sportType: string; powerWkg: number } =>
      value != null && Number.isFinite(value.powerWkg)
    );

  if (usable.length < 3) {
    return {
      source: "fallback",
      activities_used: usable.length,
      road_activities_used: usable.filter((activity) => activity.sportType === "Run").length,
      trail_activities_used: usable.filter((activity) => activity.sportType === "TrailRun").length,
      route_profile: routeProfile,
      power_wkg: 9.5,
      trail_factor: routeProfile === "trail" ? 1.2 : 1,
      note: "Profil MVP neutre faute d'historique suffisant.",
    };
  }

  const roadPowers = usable
    .filter((activity) => activity.sportType === "Run")
    .map((activity) => activity.powerWkg);
  const trailPowers = usable
    .filter((activity) => activity.sportType === "TrailRun")
    .map((activity) => activity.powerWkg);
  const allPowers = usable.map((activity) => activity.powerWkg);
  const allMedian = median(allPowers);
  const roadMedian = roadPowers.length >= 3 ? median(roadPowers) : allMedian;
  const trailMedianRaw = trailPowers.length >= 5 ? median(trailPowers) : null;
  const priorTrailFactor = 1.2;
  const trailFactor = trailMedianRaw != null && roadMedian > 0
    ? clamp(roadMedian / trailMedianRaw, 1.05, 1.35)
    : priorTrailFactor;
  const selectedPower = routeProfile === "trail"
    ? trailMedianRaw ?? (roadMedian / priorTrailFactor)
    : roadMedian;

  return {
    source: "activities",
    activities_used: usable.length,
    road_activities_used: roadPowers.length,
    trail_activities_used: trailPowers.length,
    route_profile: routeProfile,
    power_wkg: round(selectedPower, 2),
    road_power_wkg: round(roadMedian, 2),
    trail_power_wkg: trailMedianRaw == null ? undefined : round(trailMedianRaw, 2),
    trail_factor: round(trailFactor, 3),
    note: routeProfile === "trail"
      ? "Calibration trail: puissance issue des activites TrailRun si disponibles, sinon puissance route divisee par le prior trail."
      : "Calibration route: puissance issue des activites Run uniquement.",
  };
}

function resolveRavitos(
  totalDistanceKm: number,
  mode: string,
  customRavitos: RavitoPoint[],
): RavitoPoint[] {
  if (mode === "manual" && customRavitos.length > 0) {
    return customRavitos
      .filter((ravito) => ravito.km > 0 && ravito.km < totalDistanceKm)
      .sort((a, b) => a.km - b.km);
  }

  if (customRavitos.length > 0) {
    return customRavitos
      .filter((ravito) => ravito.km > 0 && ravito.km < totalDistanceKm)
      .map((ravito, index) => ({
        ...ravito,
        pause_min: autoPauseForAidPoint(totalDistanceKm, ravito, index),
      }))
      .sort((a, b) => a.km - b.km);
  }

  if (totalDistanceKm < 35) return [];
  const interval = totalDistanceKm >= 80 ? 12.5 : 15;
  const points: RavitoPoint[] = [];
  for (let km = interval; km < totalDistanceKm - 3; km += interval) {
    points.push({
      km: round(km, 1),
      name: `Ravito ${points.length + 1}`,
      pause_min: autoPauseForAidPoint(totalDistanceKm, { km, name: "", pause_min: 0 }, points.length),
    });
  }
  return points;
}

export function parseCustomRavitos(value: FormDataEntryValue | null): RavitoPoint[] {
  if (typeof value !== "string" || value.trim().length === 0) return [];
  const parsed = JSON.parse(value) as Array<Record<string, unknown>>;
  return parsed.map((item, index) => ({
    km: Number(item.km ?? item.distance_km ?? 0),
    name: String(item.name ?? `Ravito ${index + 1}`),
    pause_min: Number(item.pause_min ?? item.pauseMin ?? 0),
  })).filter((item) => Number.isFinite(item.km) && Number.isFinite(item.pause_min));
}

function inferRouteProfile(
  analysisMode: string,
  totalDistanceKm: number,
  totalElevationGainM: number,
): "road" | "trail" {
  if (analysisMode === "road") return "road";
  if (analysisMode === "trail") return "trail";
  const dPlusPerKm = totalElevationGainM / Math.max(totalDistanceKm, 1);
  return dPlusPerKm >= 15 || totalDistanceKm >= 35 ? "trail" : "road";
}

function autoPauseForAidPoint(
  totalDistanceKm: number,
  ravito: Pick<RavitoPoint, "km" | "name" | "pause_min">,
  index: number,
): number {
  if (totalDistanceKm < 35) return 0;

  const km = Number(ravito.km ?? 0);
  const name = normalizeText(ravito.name);
  const isLongUltra = totalDistanceKm >= 80;
  const isDrinkOnly = name.includes("verrieres");
  const isHotOrBase =
    name.includes("gorges") ||
    name.includes("places") ||
    name.includes("chapeau") ||
    name.includes("roche");

  if (!isLongUltra) {
    return round(km >= 30 ? 5 : 4, 1);
  }

  if (isDrinkOnly) return 6;

  let pause = 12;
  if (km >= 40) pause += 2;
  if (km >= 70) pause += Math.min(8, (km - 70) * 0.16);
  if (isHotOrBase) pause += 10;
  if (index >= 8) pause += 2;

  return round(clamp(pause, 10, 28), 1);
}

function normalizeText(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

function downsample(points: GpxPoint[], maxPoints: number): GpxPoint[] {
  if (points.length <= maxPoints) return points;
  const sampled: GpxPoint[] = [];
  const step = (points.length - 1) / (maxPoints - 1);
  for (let i = 0; i < maxPoints; i += 1) {
    sampled.push(points[Math.round(i * step)]);
  }
  return sampled;
}

function haversine(a: GpxPoint, b: GpxPoint): number {
  const radius = 6371000;
  const dLat = toRad(b.lat - a.lat);
  const dLon = toRad(b.lon - a.lon);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * radius * Math.asin(Math.sqrt(h));
}

function minettiRunCost(grade: number): number {
  const g = clamp(grade, -0.35, 0.35);
  return clamp(
    155.4 * g ** 5 - 30.4 * g ** 4 - 43.3 * g ** 3 + 46.3 * g ** 2 + 19.5 * g + 3.6,
    2.7,
    32,
  );
}

function minettiWalkCost(grade: number): number {
  const g = clamp(grade, -0.35, 0.45);
  return clamp(
    280.5 * g ** 5 - 58.7 * g ** 4 - 76.8 * g ** 3 + 51.9 * g ** 2 + 19.6 * g + 2.5,
    2.2,
    36,
  );
}

function effortToMultiplier(mode: string): number {
  if (mode === "endurance") return 0.92;
  if (mode === "aggressive") return 1.07;
  return 1;
}

function temperatureToFactor(temperatureC: number | null): number {
  if (temperatureC == null || !Number.isFinite(temperatureC)) return 1;
  if (temperatureC > 24) return 1 + (temperatureC - 24) * 0.012;
  if (temperatureC < 2) return 1 + (2 - temperatureC) * 0.006;
  return 1;
}

function formatDuration(minutes: number): string {
  const rounded = Math.round(minutes);
  const h = Math.floor(rounded / 60);
  const m = rounded % 60;
  return `${h}h${String(m).padStart(2, "0")}`;
}

function average(values: number[]): number {
  if (values.length === 0) return 0;
  return sum(values) / values.length;
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) return sorted[middle];
  return (sorted[middle - 1] + sorted[middle]) / 2;
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function round(value: number, decimals: number): number {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

function toRad(value: number): number {
  return value * Math.PI / 180;
}
