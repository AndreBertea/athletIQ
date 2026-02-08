import { useMemo } from 'react'
import { Lightbulb, TrendingUp, TrendingDown, Thermometer, Moon, Heart } from 'lucide-react'
import { format, parseISO, subDays } from 'date-fns'
import type { GarminDailyEntry } from '../../services/garminService'
import type { ActivityWeather } from '../../services/dataService'
import type { EnrichedActivity } from '../../services/activityService'

interface CorrelationInsightsProps {
  activities: EnrichedActivity[]
  garminDaily: GarminDailyEntry[]
  weatherData: Map<string, ActivityWeather>
}

// --- Helpers ---

function dateKey(d: Date): string {
  return format(d, 'yyyy-MM-dd')
}

function buildGarminMap(garminDaily: GarminDailyEntry[]): Map<string, GarminDailyEntry> {
  const map = new Map<string, GarminDailyEntry>()
  for (const entry of garminDaily) {
    map.set(entry.date, entry)
  }
  return map
}

/** Pace en min/km à partir de avg_speed_m_s */
function speedToPace(speedMs: number): number | null {
  if (!speedMs || speedMs <= 0) return null
  return (1000 / speedMs) / 60 // min/km
}

function formatPace(paceMinKm: number): string {
  const mins = Math.floor(paceMinKm)
  const secs = Math.round((paceMinKm - mins) * 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

// --- Carte individuelle ---

interface InsightCardProps {
  title: string
  icon: React.ReactNode
  borderColor: string
  children: React.ReactNode
}

function InsightCard({ title, icon, borderColor, children }: InsightCardProps) {
  return (
    <div className={`bg-white rounded-lg border-l-4 ${borderColor} border border-gray-200 p-5`}>
      <div className="flex items-center space-x-2 mb-3">
        {icon}
        <h4 className="text-sm font-semibold text-gray-800">{title}</h4>
      </div>
      {children}
    </div>
  )
}

function InsufficientData({ message }: { message?: string }) {
  return (
    <p className="text-sm text-gray-400 italic">
      {message || 'Pas assez de données (min. 5 activités)'}
    </p>
  )
}

function GarminNotConnected() {
  return (
    <div className="text-sm text-gray-400">
      <p className="italic mb-2">Connectez Garmin pour activer cet insight.</p>
      <a
        href="/parametres"
        className="text-primary-600 hover:text-primary-700 font-medium underline"
      >
        Aller dans les Paramètres
      </a>
    </div>
  )
}

// --- Calculs des 4 cartes ---

interface RecoveryPerformanceResult {
  hasData: boolean
  highReadinessCount: number
  lowReadinessCount: number
  highReadinessAvgPace: number | null
  lowReadinessAvgPace: number | null
  deltaPct: number | null
}

function computeRecoveryPerformance(
  activities: EnrichedActivity[],
  garminMap: Map<string, GarminDailyEntry>,
): RecoveryPerformanceResult {
  const paired: { readiness: number; pace: number }[] = []

  for (const act of activities) {
    if (!act.avg_speed_m_s || act.avg_speed_m_s <= 0) continue
    const pace = speedToPace(act.avg_speed_m_s)
    if (!pace) continue

    const actDate = dateKey(parseISO(act.start_date_utc))
    const garmin = garminMap.get(actDate)
    if (!garmin || garmin.training_readiness === null) continue

    paired.push({ readiness: garmin.training_readiness, pace })
  }

  if (paired.length < 5) {
    return { hasData: false, highReadinessCount: 0, lowReadinessCount: 0, highReadinessAvgPace: null, lowReadinessAvgPace: null, deltaPct: null }
  }

  const high = paired.filter(p => p.readiness >= 60)
  const low = paired.filter(p => p.readiness < 60)

  const avgPace = (items: typeof paired) =>
    items.length > 0 ? items.reduce((s, i) => s + i.pace, 0) / items.length : null

  const highAvg = avgPace(high)
  const lowAvg = avgPace(low)

  let deltaPct: number | null = null
  if (highAvg !== null && lowAvg !== null && lowAvg > 0) {
    // Pace plus bas = plus rapide. Delta positif = plus rapide avec high readiness
    deltaPct = ((lowAvg - highAvg) / lowAvg) * 100
  }

  return {
    hasData: true,
    highReadinessCount: high.length,
    lowReadinessCount: low.length,
    highReadinessAvgPace: highAvg,
    lowReadinessAvgPace: lowAvg,
    deltaPct,
  }
}

interface WeatherHrResult {
  hasData: boolean
  cold: { count: number; avgHr: number } | null  // <10C
  mild: { count: number; avgHr: number } | null  // 10-20C
  hot: { count: number; avgHr: number } | null    // >20C
}

function computeWeatherHr(
  activities: EnrichedActivity[],
  weatherData: Map<string, ActivityWeather>,
): WeatherHrResult {
  const buckets = {
    cold: [] as number[],
    mild: [] as number[],
    hot: [] as number[],
  }

  for (const act of activities) {
    if (!act.avg_heartrate_bpm || act.avg_heartrate_bpm <= 0) continue
    const weather = weatherData.get(String(act.activity_id))
    if (!weather || weather.temperature_c === null) continue

    const temp = weather.temperature_c
    if (temp < 10) buckets.cold.push(act.avg_heartrate_bpm)
    else if (temp <= 20) buckets.mild.push(act.avg_heartrate_bpm)
    else buckets.hot.push(act.avg_heartrate_bpm)
  }

  const total = buckets.cold.length + buckets.mild.length + buckets.hot.length
  if (total < 5) {
    return { hasData: false, cold: null, mild: null, hot: null }
  }

  const avg = (arr: number[]) => arr.length > 0 ? arr.reduce((a, b) => a + b, 0) / arr.length : 0

  return {
    hasData: true,
    cold: buckets.cold.length > 0 ? { count: buckets.cold.length, avgHr: avg(buckets.cold) } : null,
    mild: buckets.mild.length > 0 ? { count: buckets.mild.length, avgHr: avg(buckets.mild) } : null,
    hot: buckets.hot.length > 0 ? { count: buckets.hot.length, avgHr: avg(buckets.hot) } : null,
  }
}

type SleepLoadState = 'equilibre' | 'attention' | 'bonne_recuperation'

interface SleepLoadResult {
  hasData: boolean
  avgSleep7d: number | null
  recentActivityCount: number
  state: SleepLoadState | null
}

function computeSleepLoad(
  activities: EnrichedActivity[],
  garminDaily: GarminDailyEntry[],
): SleepLoadResult {
  if (garminDaily.length < 7) {
    return { hasData: false, avgSleep7d: null, recentActivityCount: 0, state: null }
  }

  const last7 = garminDaily.slice(-7)
  const sleepValues = last7
    .map(d => d.sleep_score)
    .filter((v): v is number => v !== null)

  if (sleepValues.length === 0) {
    return { hasData: false, avgSleep7d: null, recentActivityCount: 0, state: null }
  }

  const avgSleep = sleepValues.reduce((a, b) => a + b, 0) / sleepValues.length

  // Compter les activités des 7 derniers jours
  const sevenDaysAgo = subDays(new Date(), 7)
  const recentCount = activities.filter(a => {
    const d = parseISO(a.start_date_utc)
    return d >= sevenDaysAgo
  }).length

  // Déterminer l'état (grille 2 axes : sommeil × charge)
  let state: SleepLoadState
  if (avgSleep >= 70 && recentCount <= 2) {
    state = 'bonne_recuperation'
  } else if (avgSleep >= 70 && recentCount >= 3 && recentCount <= 6) {
    state = 'equilibre'
  } else if (avgSleep >= 60 && avgSleep < 70 && recentCount <= 5) {
    state = 'equilibre'
  } else if (avgSleep < 60 && recentCount > 4) {
    state = 'attention'
  } else if (avgSleep >= 70 && recentCount > 6) {
    state = 'attention'
  } else {
    state = 'equilibre'
  }

  return { hasData: true, avgSleep7d: avgSleep, recentActivityCount: recentCount, state }
}

interface HrvPerformanceResult {
  hasData: boolean
  narrative: string | null
  trend: 'up' | 'down' | 'neutral' | null
}

function computeHrvPerformance(
  activities: EnrichedActivity[],
  garminMap: Map<string, GarminDailyEntry>,
): HrvPerformanceResult {
  // Croiser HRV J-1 avec pace J
  const paired: { hrv: number; pace: number }[] = []

  for (const act of activities) {
    if (!act.avg_speed_m_s || act.avg_speed_m_s <= 0) continue
    const pace = speedToPace(act.avg_speed_m_s)
    if (!pace) continue

    const actDate = parseISO(act.start_date_utc)
    const prevDate = dateKey(subDays(actDate, 1))
    const garmin = garminMap.get(prevDate)
    if (!garmin || garmin.hrv_rmssd === null) continue

    paired.push({ hrv: garmin.hrv_rmssd, pace })
  }

  if (paired.length < 5) {
    return { hasData: false, narrative: null, trend: null }
  }

  // Séparer en HRV haute (>médiane) et basse
  const sorted = [...paired].sort((a, b) => a.hrv - b.hrv)
  const mid = Math.floor(sorted.length / 2)
  const lowHrv = sorted.slice(0, mid)
  const highHrv = sorted.slice(mid)

  const avgPace = (items: typeof paired) =>
    items.reduce((s, i) => s + i.pace, 0) / items.length

  const lowAvg = avgPace(lowHrv)
  const highAvg = avgPace(highHrv)

  // Pace plus bas = plus rapide
  const diff = lowAvg - highAvg // positif = plus rapide quand HRV haute
  const diffPct = (diff / lowAvg) * 100

  let narrative: string
  let trend: 'up' | 'down' | 'neutral'

  if (diffPct > 2) {
    narrative = `Quand votre HRV est élevée (veille), vous courez ~${diffPct.toFixed(0)}% plus vite le lendemain.`
    trend = 'up'
  } else if (diffPct < -2) {
    narrative = `Votre pace ne semble pas corrélé positivement avec votre HRV. Cela peut indiquer des séances intenses malgré une HRV basse.`
    trend = 'down'
  } else {
    narrative = `Votre pace est stable quelle que soit votre HRV de la veille.`
    trend = 'neutral'
  }

  return { hasData: true, narrative, trend }
}

// --- Composant principal ---

export default function CorrelationInsights({
  activities,
  garminDaily,
  weatherData,
}: CorrelationInsightsProps) {
  const garminMap = useMemo(() => buildGarminMap(garminDaily), [garminDaily])
  const hasGarmin = garminDaily.length > 0

  const recoveryPerf = useMemo(
    () => computeRecoveryPerformance(activities, garminMap),
    [activities, garminMap],
  )

  const weatherHr = useMemo(
    () => computeWeatherHr(activities, weatherData),
    [activities, weatherData],
  )

  const sleepLoad = useMemo(
    () => computeSleepLoad(activities, garminDaily),
    [activities, garminDaily],
  )

  const hrvPerf = useMemo(
    () => computeHrvPerformance(activities, garminMap),
    [activities, garminMap],
  )

  return (
    <div className="card">
      <div className="flex items-center space-x-2 mb-6">
        <Lightbulb className="h-5 w-5 text-amber-500" />
        <h3 className="text-lg font-medium text-gray-900">Insights & Corrélations</h3>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Carte 1 — Récupération → Performance */}
        <InsightCard
          title="Récupération → Performance"
          icon={<TrendingUp className="h-4 w-4 text-green-600" />}
          borderColor="border-l-green-500"
        >
          {!hasGarmin ? (
            <GarminNotConnected />
          ) : !recoveryPerf.hasData ? (
            <InsufficientData />
          ) : (
            <div className="space-y-2">
              {recoveryPerf.deltaPct !== null && recoveryPerf.deltaPct > 0 ? (
                <p className="text-lg font-semibold text-green-700">
                  +{recoveryPerf.deltaPct.toFixed(1)}% plus vite
                </p>
              ) : recoveryPerf.deltaPct !== null ? (
                <p className="text-lg font-semibold text-gray-600">
                  {recoveryPerf.deltaPct.toFixed(1)}%
                </p>
              ) : null}
              <p className="text-sm text-gray-600">
                quand Readiness ≥ 60 vs &lt; 60
              </p>
              <div className="flex gap-4 text-xs text-gray-400 mt-1">
                <span>Readiness ≥ 60 : {recoveryPerf.highReadinessCount} act.
                  {recoveryPerf.highReadinessAvgPace !== null && (
                    <> — {formatPace(recoveryPerf.highReadinessAvgPace)} /km</>
                  )}
                </span>
              </div>
              <div className="flex gap-4 text-xs text-gray-400">
                <span>Readiness &lt; 60 : {recoveryPerf.lowReadinessCount} act.
                  {recoveryPerf.lowReadinessAvgPace !== null && (
                    <> — {formatPace(recoveryPerf.lowReadinessAvgPace)} /km</>
                  )}
                </span>
              </div>
            </div>
          )}
        </InsightCard>

        {/* Carte 2 — Météo → FC */}
        <InsightCard
          title="Météo → Fréquence Cardiaque"
          icon={<Thermometer className="h-4 w-4 text-orange-500" />}
          borderColor="border-l-orange-500"
        >
          {!weatherHr.hasData ? (
            <InsufficientData message="Pas assez de données météo (min. 5 activités)" />
          ) : (
            <div className="space-y-2">
              {[
                { label: '< 10°C', data: weatherHr.cold, color: 'text-blue-600' },
                { label: '10–20°C', data: weatherHr.mild, color: 'text-amber-600' },
                { label: '> 20°C', data: weatherHr.hot, color: 'text-red-600' },
              ].map(({ label, data, color }) => (
                <div key={label} className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">{label}</span>
                  {data ? (
                    <span className={`text-sm font-semibold ${color}`}>
                      {data.avgHr.toFixed(0)} bpm
                      <span className="text-xs text-gray-400 ml-1">({data.count})</span>
                    </span>
                  ) : (
                    <span className="text-xs text-gray-300">—</span>
                  )}
                </div>
              ))}
              {weatherHr.mild && weatherHr.hot && (
                <p className="text-xs text-gray-400 mt-1">
                  Delta chaleur : +{(weatherHr.hot.avgHr - weatherHr.mild.avgHr).toFixed(0)} bpm au-dessus de 20°C
                </p>
              )}
            </div>
          )}
        </InsightCard>

        {/* Carte 3 — Sommeil → Charge */}
        <InsightCard
          title="Sommeil → Charge"
          icon={<Moon className="h-4 w-4 text-blue-500" />}
          borderColor="border-l-blue-500"
        >
          {!hasGarmin ? (
            <GarminNotConnected />
          ) : !sleepLoad.hasData ? (
            <InsufficientData message="Pas assez de données sommeil (min. 7 jours Garmin)" />
          ) : (
            <div className="space-y-2">
              {sleepLoad.state === 'equilibre' && (
                <div className="flex items-center space-x-2">
                  <span className="inline-block w-3 h-3 rounded-full bg-green-500" />
                  <span className="text-sm font-semibold text-green-700">Équilibre</span>
                </div>
              )}
              {sleepLoad.state === 'attention' && (
                <div className="flex items-center space-x-2">
                  <span className="inline-block w-3 h-3 rounded-full bg-orange-500" />
                  <span className="text-sm font-semibold text-orange-700">Attention</span>
                </div>
              )}
              {sleepLoad.state === 'bonne_recuperation' && (
                <div className="flex items-center space-x-2">
                  <span className="inline-block w-3 h-3 rounded-full bg-blue-500" />
                  <span className="text-sm font-semibold text-blue-700">Bonne récupération</span>
                </div>
              )}
              <p className="text-sm text-gray-600">
                Sleep Score moy. 7j : <span className="font-medium">{sleepLoad.avgSleep7d?.toFixed(0)}</span>
              </p>
              <p className="text-sm text-gray-600">
                Activités 7 derniers jours : <span className="font-medium">{sleepLoad.recentActivityCount}</span>
              </p>
            </div>
          )}
        </InsightCard>

        {/* Carte 4 — HRV → Performance */}
        <InsightCard
          title="HRV → Performance"
          icon={<Heart className="h-4 w-4 text-purple-500" />}
          borderColor="border-l-purple-500"
        >
          {!hasGarmin ? (
            <GarminNotConnected />
          ) : !hrvPerf.hasData ? (
            <InsufficientData />
          ) : (
            <div className="space-y-2">
              <div className="flex items-center space-x-2">
                {hrvPerf.trend === 'up' && <TrendingUp className="h-4 w-4 text-green-500" />}
                {hrvPerf.trend === 'down' && <TrendingDown className="h-4 w-4 text-red-500" />}
                {hrvPerf.trend === 'neutral' && <span className="h-4 w-4 text-gray-400">—</span>}
                <span className={`text-sm font-semibold ${
                  hrvPerf.trend === 'up' ? 'text-green-700' :
                  hrvPerf.trend === 'down' ? 'text-red-700' : 'text-gray-700'
                }`}>
                  {hrvPerf.trend === 'up' ? 'Corrélation positive' :
                   hrvPerf.trend === 'down' ? 'Corrélation inversée' : 'Stable'}
                </span>
              </div>
              <p className="text-sm text-gray-600">{hrvPerf.narrative}</p>
            </div>
          )}
        </InsightCard>
      </div>
    </div>
  )
}
