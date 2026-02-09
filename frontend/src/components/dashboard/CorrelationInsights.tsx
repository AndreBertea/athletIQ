import { useMemo } from 'react'
import {
  Lightbulb,
  TrendingUp,
  TrendingDown,
  Minus,
  Thermometer,
  Moon,
  Heart,
  Activity,
  Link as LinkIcon,
} from 'lucide-react'
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

function speedToPace(speedMs: number): number | null {
  if (!speedMs || speedMs <= 0) return null
  return (1000 / speedMs) / 60
}

function formatPace(paceMinKm: number): string {
  const mins = Math.floor(paceMinKm)
  const secs = Math.round((paceMinKm - mins) * 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

// --- Sous-composants ---

interface InsightCardProps {
  title: string
  icon: React.ReactNode
  iconBgClass: string
  borderColorClass: string
  children: React.ReactNode
}

function InsightCard({ title, icon, iconBgClass, borderColorClass, children }: InsightCardProps) {
  return (
    <div className={`bg-white rounded-lg border-l-4 ${borderColorClass} border border-gray-200/60 p-4 transition-all duration-200 hover:shadow-sm`}>
      <div className="flex items-center gap-2.5 mb-3">
        <div className={`p-1.5 rounded-md ${iconBgClass}`}>
          {icon}
        </div>
        <h4 className="text-sm font-semibold text-gray-900">{title}</h4>
      </div>
      {children}
    </div>
  )
}

function InsufficientData({ message }: { message?: string }) {
  return (
    <p className="text-xs text-gray-400 italic">
      {message || 'Pas assez de données (min. 5 activités)'}
    </p>
  )
}

function GarminNotConnected() {
  return (
    <div className="flex items-center gap-2 text-xs text-gray-400">
      <LinkIcon className="h-3 w-3 flex-shrink-0" />
      <span>
        <a href="/parametres" className="text-amber-600 hover:text-amber-700 font-medium">
          Connectez Garmin
        </a>
        {' '}pour activer cet insight
      </span>
    </div>
  )
}

interface TrendBadgeProps {
  value: number
  suffix?: string
  invertColor?: boolean
}

function TrendBadge({ value, suffix = '%', invertColor = false }: TrendBadgeProps) {
  const isPositive = invertColor ? value < 0 : value > 0
  const isNegative = invertColor ? value > 0 : value < 0

  return (
    <div className={`inline-flex items-center gap-1 text-xs font-semibold px-1.5 py-0.5 rounded-full ${
      isPositive
        ? 'bg-emerald-50 text-emerald-700'
        : isNegative
        ? 'bg-red-50 text-red-600'
        : 'bg-gray-100 text-gray-500'
    }`}>
      {isPositive ? (
        <TrendingUp className="h-3 w-3" />
      ) : isNegative ? (
        <TrendingDown className="h-3 w-3" />
      ) : (
        <Minus className="h-3 w-3" />
      )}
      {value > 0 ? '+' : ''}{value.toFixed(1)}{suffix}
    </div>
  )
}

// --- Mini barre de comparaison inline ---

interface MiniBarProps {
  label: string
  value: number | null
  maxValue: number
  colorClass: string
  unit: string
  count?: number
}

function MiniBar({ label, value, maxValue, colorClass, unit, count }: MiniBarProps) {
  const width = value && maxValue > 0 ? Math.min((value / maxValue) * 100, 100) : 0

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-500 w-14 flex-shrink-0">{label}</span>
      <div className="flex-1 flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${colorClass}`}
            style={{ width: `${width}%` }}
          />
        </div>
        {value !== null ? (
          <span className="text-xs font-medium text-gray-700 w-16 text-right">
            {value.toFixed(0)} {unit}
            {count !== undefined && (
              <span className="text-gray-400 font-normal"> ({count})</span>
            )}
          </span>
        ) : (
          <span className="text-xs text-gray-300 w-16 text-right">--</span>
        )}
      </div>
    </div>
  )
}

// --- Calculs des 4 cartes (logique inchangée) ---

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
  cold: { count: number; avgHr: number } | null
  mild: { count: number; avgHr: number } | null
  hot: { count: number; avgHr: number } | null
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

  const sevenDaysAgo = subDays(new Date(), 7)
  const recentCount = activities.filter(a => {
    const d = parseISO(a.start_date_utc)
    return d >= sevenDaysAgo
  }).length

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
  recommendation: string | null
  trend: 'up' | 'down' | 'neutral' | null
  diffPct: number | null
}

function computeHrvPerformance(
  activities: EnrichedActivity[],
  garminMap: Map<string, GarminDailyEntry>,
): HrvPerformanceResult {
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
    return { hasData: false, narrative: null, recommendation: null, trend: null, diffPct: null }
  }

  const sorted = [...paired].sort((a, b) => a.hrv - b.hrv)
  const mid = Math.floor(sorted.length / 2)
  const lowHrv = sorted.slice(0, mid)
  const highHrv = sorted.slice(mid)

  const avgPace = (items: typeof paired) =>
    items.reduce((s, i) => s + i.pace, 0) / items.length

  const lowAvg = avgPace(lowHrv)
  const highAvg = avgPace(highHrv)

  const diff = lowAvg - highAvg
  const diffPct = (diff / lowAvg) * 100

  let narrative: string
  let recommendation: string
  let trend: 'up' | 'down' | 'neutral'

  if (diffPct > 2) {
    narrative = `Quand votre HRV est élevée, vous courez ~${diffPct.toFixed(0)}% plus vite le lendemain.`
    recommendation = 'Planifiez vos séances intenses après une bonne nuit de sommeil.'
    trend = 'up'
  } else if (diffPct < -2) {
    narrative = `Votre pace n'est pas corrélé positivement avec votre HRV.`
    recommendation = 'Cela peut indiquer des séances intenses malgré une HRV basse — écoutez votre corps.'
    trend = 'down'
  } else {
    narrative = `Votre pace est stable quelle que soit votre HRV.`
    recommendation = 'Bonne régularité — votre corps gère bien les variations de récupération.'
    trend = 'neutral'
  }

  return { hasData: true, narrative, recommendation, trend, diffPct }
}

// --- Helpers pour narration des états ---

const sleepLoadConfig: Record<SleepLoadState, {
  label: string
  dotColor: string
  textColor: string
  recommendation: string
}> = {
  equilibre: {
    label: 'Équilibre',
    dotColor: 'bg-emerald-500',
    textColor: 'text-emerald-700',
    recommendation: 'Bon ratio sommeil/charge. Continuez sur ce rythme.',
  },
  attention: {
    label: 'Attention',
    dotColor: 'bg-amber-500',
    textColor: 'text-amber-700',
    recommendation: 'Charge élevée ou sommeil insuffisant. Prévoyez du repos.',
  },
  bonne_recuperation: {
    label: 'Bonne récupération',
    dotColor: 'bg-blue-500',
    textColor: 'text-blue-700',
    recommendation: 'Vous êtes bien reposé. Idéal pour une séance qualité.',
  },
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

  // Max HR across buckets for MiniBar scaling
  const maxHr = useMemo(() => {
    const values = [weatherHr.cold?.avgHr, weatherHr.mild?.avgHr, weatherHr.hot?.avgHr]
      .filter((v): v is number => v !== null && v !== undefined)
    return values.length > 0 ? Math.max(...values) * 1.1 : 200
  }, [weatherHr])

  return (
    <div className="bg-white rounded-xl border border-gray-200/60 p-6">
      {/* Section header */}
      <div className="flex items-center gap-2 mb-5">
        <div className="p-2 rounded-lg bg-amber-100">
          <Lightbulb className="h-5 w-5 text-amber-600" />
        </div>
        <div>
          <h3 className="text-base font-semibold text-gray-900">Insights</h3>
          <p className="text-xs text-gray-400">Corrélations entre vos données</p>
        </div>
      </div>

      <div className="space-y-3">
        {/* Carte 1 — Récupération -> Performance */}
        <InsightCard
          title="Récupération → Performance"
          icon={<Activity className="h-3.5 w-3.5 text-emerald-600" />}
          iconBgClass="bg-emerald-50"
          borderColorClass="border-l-emerald-500"
        >
          {!hasGarmin ? (
            <GarminNotConnected />
          ) : !recoveryPerf.hasData ? (
            <InsufficientData />
          ) : (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Readiness ≥ 60 vs &lt; 60</span>
                {recoveryPerf.deltaPct !== null && (
                  <TrendBadge value={recoveryPerf.deltaPct} />
                )}
              </div>
              <div className="flex items-baseline gap-3">
                {recoveryPerf.highReadinessAvgPace !== null && (
                  <div className="text-center">
                    <p className="text-lg font-bold text-gray-900">
                      {formatPace(recoveryPerf.highReadinessAvgPace)}
                    </p>
                    <p className="text-xs text-gray-400">/km haute</p>
                  </div>
                )}
                <span className="text-xs text-gray-300">vs</span>
                {recoveryPerf.lowReadinessAvgPace !== null && (
                  <div className="text-center">
                    <p className="text-lg font-bold text-gray-400">
                      {formatPace(recoveryPerf.lowReadinessAvgPace)}
                    </p>
                    <p className="text-xs text-gray-400">/km basse</p>
                  </div>
                )}
              </div>
              <p className="text-xs text-gray-500">
                {recoveryPerf.deltaPct !== null && recoveryPerf.deltaPct > 0
                  ? 'Planifiez vos séances qualité les jours où votre readiness est élevée.'
                  : 'Pas de différence significative détectée.'}
              </p>
              <div className="flex gap-3 text-xs text-gray-400">
                <span>{recoveryPerf.highReadinessCount} act. haute</span>
                <span>{recoveryPerf.lowReadinessCount} act. basse</span>
              </div>
            </div>
          )}
        </InsightCard>

        {/* Carte 2 — Météo -> FC */}
        <InsightCard
          title="Météo → FC"
          icon={<Thermometer className="h-3.5 w-3.5 text-orange-500" />}
          iconBgClass="bg-orange-50"
          borderColorClass="border-l-orange-500"
        >
          {!weatherHr.hasData ? (
            <InsufficientData message="Pas assez de données météo (min. 5 activités)" />
          ) : (
            <div className="space-y-2">
              <MiniBar
                label="< 10°C"
                value={weatherHr.cold?.avgHr ?? null}
                maxValue={maxHr}
                colorClass="bg-blue-400"
                unit="bpm"
                count={weatherHr.cold?.count}
              />
              <MiniBar
                label="10–20°C"
                value={weatherHr.mild?.avgHr ?? null}
                maxValue={maxHr}
                colorClass="bg-amber-400"
                unit="bpm"
                count={weatherHr.mild?.count}
              />
              <MiniBar
                label="> 20°C"
                value={weatherHr.hot?.avgHr ?? null}
                maxValue={maxHr}
                colorClass="bg-red-400"
                unit="bpm"
                count={weatherHr.hot?.count}
              />
              {weatherHr.mild && weatherHr.hot && (
                <p className="text-xs text-gray-500 pt-1">
                  Hydratez-vous davantage par temps chaud
                  <span className="text-gray-400"> — delta : +{(weatherHr.hot.avgHr - weatherHr.mild.avgHr).toFixed(0)} bpm au-dessus de 20°C</span>
                </p>
              )}
            </div>
          )}
        </InsightCard>

        {/* Carte 3 — Sommeil -> Charge */}
        <InsightCard
          title="Sommeil → Charge"
          icon={<Moon className="h-3.5 w-3.5 text-indigo-500" />}
          iconBgClass="bg-indigo-50"
          borderColorClass="border-l-indigo-500"
        >
          {!hasGarmin ? (
            <GarminNotConnected />
          ) : !sleepLoad.hasData ? (
            <InsufficientData message="Pas assez de données sommeil (min. 7 jours)" />
          ) : sleepLoad.state !== null ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={`inline-block w-2.5 h-2.5 rounded-full ${sleepLoadConfig[sleepLoad.state].dotColor}`} />
                  <span className={`text-sm font-semibold ${sleepLoadConfig[sleepLoad.state].textColor}`}>
                    {sleepLoadConfig[sleepLoad.state].label}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-4 text-xs text-gray-500">
                <span>
                  Sleep score moy. : <span className="font-medium text-gray-700">{sleepLoad.avgSleep7d?.toFixed(0)}</span>
                </span>
                <span>
                  Activités 7j : <span className="font-medium text-gray-700">{sleepLoad.recentActivityCount}</span>
                </span>
              </div>
              <p className="text-xs text-gray-500">
                {sleepLoadConfig[sleepLoad.state].recommendation}
              </p>
            </div>
          ) : null}
        </InsightCard>

        {/* Carte 4 — HRV -> Performance */}
        <InsightCard
          title="HRV → Performance"
          icon={<Heart className="h-3.5 w-3.5 text-violet-500" />}
          iconBgClass="bg-violet-50"
          borderColorClass="border-l-violet-500"
        >
          {!hasGarmin ? (
            <GarminNotConnected />
          ) : !hrvPerf.hasData ? (
            <InsufficientData />
          ) : (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  {hrvPerf.trend === 'up' && <TrendingUp className="h-3.5 w-3.5 text-emerald-500" />}
                  {hrvPerf.trend === 'down' && <TrendingDown className="h-3.5 w-3.5 text-red-500" />}
                  {hrvPerf.trend === 'neutral' && <Minus className="h-3.5 w-3.5 text-gray-400" />}
                  <span className={`text-sm font-semibold ${
                    hrvPerf.trend === 'up' ? 'text-emerald-700' :
                    hrvPerf.trend === 'down' ? 'text-red-600' : 'text-gray-600'
                  }`}>
                    {hrvPerf.trend === 'up' ? 'Corrélation positive' :
                     hrvPerf.trend === 'down' ? 'Corrélation inversée' : 'Stable'}
                  </span>
                </div>
                {hrvPerf.diffPct !== null && (
                  <TrendBadge value={hrvPerf.diffPct} />
                )}
              </div>
              <p className="text-xs text-gray-600">{hrvPerf.narrative}</p>
              <p className="text-xs text-gray-500 italic">{hrvPerf.recommendation}</p>
            </div>
          )}
        </InsightCard>
      </div>
    </div>
  )
}
