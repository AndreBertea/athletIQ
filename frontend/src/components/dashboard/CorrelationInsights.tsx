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
  Calendar,
  BarChart3,
  Zap,
} from 'lucide-react'
import { format, parseISO, subDays } from 'date-fns'
import type { GarminDailyEntry } from '../../services/garminService'
import type { ActivityWeather } from '../../services/dataService'
import type { EnrichedActivity } from '../../services/activityService'

interface TrainingLoadPoint {
  date: string
  chronicLoad: number
  acuteLoad: number
  trainingStressBalance: number
}

interface CorrelationInsightsProps {
  activities: EnrichedActivity[]
  garminDaily: GarminDailyEntry[]
  weatherData: Map<string, ActivityWeather>
  trainingLoadData?: TrainingLoadPoint[]
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

// --- Calculs des cartes ---

/** Score de récupération composite : training_readiness > body_battery > sleep_score */
function getRecoveryScore(garmin: GarminDailyEntry): number | null {
  if (garmin.training_readiness !== null) return garmin.training_readiness
  if (garmin.body_battery_max !== null) return garmin.body_battery_max
  if (garmin.sleep_score !== null) return garmin.sleep_score
  return null
}

type PerfMetric = 'pace' | 'hr'

interface RecoveryPerformanceResult {
  hasData: boolean
  metric: PerfMetric
  highCount: number
  lowCount: number
  highAvgValue: number | null
  lowAvgValue: number | null
  deltaPct: number | null
}

function computeRecoveryPerformance(
  activities: EnrichedActivity[],
  garminMap: Map<string, GarminDailyEntry>,
): RecoveryPerformanceResult {
  const empty: RecoveryPerformanceResult = {
    hasData: false, metric: 'pace', highCount: 0, lowCount: 0,
    highAvgValue: null, lowAvgValue: null, deltaPct: null,
  }

  // Essayer d'abord avec le pace (meilleur indicateur)
  const pacePaired: { recovery: number; value: number }[] = []
  const hrPaired: { recovery: number; value: number }[] = []

  for (const act of activities) {
    const actDate = dateKey(parseISO(act.start_date_utc))
    const garmin = garminMap.get(actDate)
    if (!garmin) continue
    const recovery = getRecoveryScore(garmin)
    if (recovery === null) continue

    const pace = speedToPace(act.avg_speed_m_s)
    if (pace) {
      pacePaired.push({ recovery, value: pace })
    }
    if (act.avg_heartrate_bpm && act.avg_heartrate_bpm > 0) {
      hrPaired.push({ recovery, value: act.avg_heartrate_bpm })
    }
  }

  // Utiliser pace si ≥ 3 paires, sinon FC si ≥ 3 paires
  const paired = pacePaired.length >= 3 ? pacePaired : hrPaired.length >= 3 ? hrPaired : null
  const metric: PerfMetric = pacePaired.length >= 3 ? 'pace' : 'hr'

  if (!paired || paired.length < 3) return empty

  const high = paired.filter(p => p.recovery >= 60)
  const low = paired.filter(p => p.recovery < 60)

  if (high.length === 0 || low.length === 0) return empty

  const avg = (items: typeof paired) =>
    items.length > 0 ? items.reduce((s, i) => s + i.value, 0) / items.length : null

  const highAvg = avg(high)
  const lowAvg = avg(low)

  let deltaPct: number | null = null
  if (highAvg !== null && lowAvg !== null && lowAvg > 0) {
    if (metric === 'pace') {
      // Pour le pace : plus bas = plus rapide, donc delta positif = amélioration
      deltaPct = ((lowAvg - highAvg) / lowAvg) * 100
    } else {
      // Pour la FC : plus bas = meilleur rendement cardiaque
      deltaPct = ((lowAvg - highAvg) / lowAvg) * 100
    }
  }

  return {
    hasData: true,
    metric,
    highCount: high.length,
    lowCount: low.length,
    highAvgValue: highAvg,
    lowAvgValue: lowAvg,
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

// --- Volume hebdo ---

interface VolumeTrendResult {
  hasData: boolean
  weeks: { label: string; distanceKm: number; count: number }[]
  currentVsPrevPct: number | null
}

function computeVolumeTrend(activities: EnrichedActivity[]): VolumeTrendResult {
  if (activities.length < 3) {
    return { hasData: false, weeks: [], currentVsPrevPct: null }
  }

  const now = new Date()
  const currentDay = now.getDay()
  const mondayOffset = currentDay === 0 ? -6 : 1 - currentDay
  const currentMonday = new Date(now)
  currentMonday.setDate(now.getDate() + mondayOffset)
  currentMonday.setHours(0, 0, 0, 0)

  const weeks: { label: string; start: Date; distanceKm: number; count: number }[] = []
  for (let i = 0; i < 4; i++) {
    const weekStart = new Date(currentMonday)
    weekStart.setDate(currentMonday.getDate() - i * 7)
    weeks.push({
      label: i === 0 ? 'Actuelle' : `S-${i}`,
      start: weekStart,
      distanceKm: 0,
      count: 0,
    })
  }

  for (const act of activities) {
    const actDate = parseISO(act.start_date_utc)
    for (let i = 0; i < weeks.length; i++) {
      const weekEnd = new Date(weeks[i].start)
      weekEnd.setDate(weeks[i].start.getDate() + 7)
      if (actDate >= weeks[i].start && actDate < weekEnd) {
        weeks[i].distanceKm += act.distance_m / 1000
        weeks[i].count++
        break
      }
    }
  }

  const hasAnyData = weeks.some(w => w.count > 0)
  if (!hasAnyData) {
    return { hasData: false, weeks: [], currentVsPrevPct: null }
  }

  let currentVsPrevPct: number | null = null
  if (weeks.length >= 2 && weeks[1].distanceKm > 0) {
    currentVsPrevPct = ((weeks[0].distanceKm - weeks[1].distanceKm) / weeks[1].distanceKm) * 100
  }

  return {
    hasData: true,
    weeks: weeks.map(w => ({ label: w.label, distanceKm: w.distanceKm, count: w.count })),
    currentVsPrevPct,
  }
}

// --- Meilleur jour de la semaine ---

interface BestDayResult {
  hasData: boolean
  days: { day: string; avgPace: number | null; count: number }[]
  bestDay: string | null
  bestPace: number | null
  globalAvgPace: number | null
}

const DAY_NAMES = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam']

function computeBestDay(activities: EnrichedActivity[]): BestDayResult {
  const dayBuckets: number[][] = Array.from({ length: 7 }, () => [])

  for (const act of activities) {
    const pace = speedToPace(act.avg_speed_m_s)
    if (!pace) continue
    const dayIdx = parseISO(act.start_date_utc).getDay()
    dayBuckets[dayIdx].push(pace)
  }

  const totalPaces = dayBuckets.flat()
  if (totalPaces.length < 5) {
    return { hasData: false, days: [], bestDay: null, bestPace: null, globalAvgPace: null }
  }

  const globalAvgPace = totalPaces.reduce((a, b) => a + b, 0) / totalPaces.length

  const days = dayBuckets.map((paces, idx) => ({
    day: DAY_NAMES[idx],
    avgPace: paces.length > 0 ? paces.reduce((a, b) => a + b, 0) / paces.length : null,
    count: paces.length,
  }))

  let bestDay: string | null = null
  let bestPace: number | null = null
  for (const d of days) {
    if (d.avgPace !== null && d.count >= 2) {
      if (bestPace === null || d.avgPace < bestPace) {
        bestPace = d.avgPace
        bestDay = d.day
      }
    }
  }

  return { hasData: true, days, bestDay, bestPace, globalAvgPace }
}

// --- Forme TSB ---

interface TsbZoneResult {
  hasData: boolean
  currentTsb: number | null
  zone: 'surcharge' | 'fatigue' | 'optimal' | 'frais' | 'tres_frais' | null
  trend7d: number | null
  acuteLoad: number | null
  chronicLoad: number | null
}

function computeTsbZone(data?: TrainingLoadPoint[]): TsbZoneResult {
  if (!data || data.length < 7) {
    return { hasData: false, currentTsb: null, zone: null, trend7d: null, acuteLoad: null, chronicLoad: null }
  }

  const latest = data[data.length - 1]
  const weekAgo = data[Math.max(0, data.length - 8)]

  const tsb = latest.trainingStressBalance
  let zone: TsbZoneResult['zone']
  if (tsb < -25) zone = 'surcharge'
  else if (tsb < -10) zone = 'fatigue'
  else if (tsb <= 10) zone = 'optimal'
  else if (tsb <= 25) zone = 'frais'
  else zone = 'tres_frais'

  return {
    hasData: true,
    currentTsb: tsb,
    zone,
    trend7d: tsb - weekAgo.trainingStressBalance,
    acuteLoad: latest.acuteLoad,
    chronicLoad: latest.chronicLoad,
  }
}

const tsbZoneConfig: Record<NonNullable<TsbZoneResult['zone']>, {
  label: string
  dotColor: string
  textColor: string
  recommendation: string
}> = {
  surcharge: {
    label: 'Surchargé',
    dotColor: 'bg-red-500',
    textColor: 'text-red-700',
    recommendation: 'Risque de blessure. Prévoyez du repos ou réduisez l\'intensité.',
  },
  fatigue: {
    label: 'Fatigué',
    dotColor: 'bg-amber-500',
    textColor: 'text-amber-700',
    recommendation: 'Fatigue accumulée. Allégez les prochaines séances.',
  },
  optimal: {
    label: 'Optimal',
    dotColor: 'bg-emerald-500',
    textColor: 'text-emerald-700',
    recommendation: 'Bon équilibre charge/récupération. Zone idéale d\'entraînement.',
  },
  frais: {
    label: 'Frais',
    dotColor: 'bg-blue-500',
    textColor: 'text-blue-700',
    recommendation: 'Bien reposé. Idéal pour une compétition ou une séance intense.',
  },
  tres_frais: {
    label: 'Très frais',
    dotColor: 'bg-indigo-500',
    textColor: 'text-indigo-700',
    recommendation: 'Très reposé. Vous pouvez augmenter le volume ou l\'intensité.',
  },
}

// --- Composant principal ---

export default function CorrelationInsights({
  activities,
  garminDaily,
  weatherData,
  trainingLoadData,
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

  const volumeTrend = useMemo(
    () => computeVolumeTrend(activities),
    [activities],
  )

  const bestDay = useMemo(
    () => computeBestDay(activities),
    [activities],
  )

  const tsbZone = useMemo(
    () => computeTsbZone(trainingLoadData),
    [trainingLoadData],
  )

  const maxWeeklyKm = useMemo(() => {
    if (!volumeTrend.hasData) return 1
    return Math.max(...volumeTrend.weeks.map(w => w.distanceKm), 1) * 1.1
  }, [volumeTrend])

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
            <InsufficientData message="Pas assez de croisements récupération/activité (min. 3)" />
          ) : (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Récupération ≥ 60 vs &lt; 60</span>
                {recoveryPerf.deltaPct !== null && (
                  <TrendBadge value={recoveryPerf.deltaPct} />
                )}
              </div>
              <div className="flex items-baseline gap-3">
                {recoveryPerf.highAvgValue !== null && (
                  <div className="text-center">
                    <p className="text-lg font-bold text-gray-900">
                      {recoveryPerf.metric === 'pace'
                        ? formatPace(recoveryPerf.highAvgValue)
                        : `${recoveryPerf.highAvgValue.toFixed(0)}`}
                    </p>
                    <p className="text-xs text-gray-400">
                      {recoveryPerf.metric === 'pace' ? '/km haute' : 'bpm haute'}
                    </p>
                  </div>
                )}
                <span className="text-xs text-gray-300">vs</span>
                {recoveryPerf.lowAvgValue !== null && (
                  <div className="text-center">
                    <p className="text-lg font-bold text-gray-400">
                      {recoveryPerf.metric === 'pace'
                        ? formatPace(recoveryPerf.lowAvgValue)
                        : `${recoveryPerf.lowAvgValue.toFixed(0)}`}
                    </p>
                    <p className="text-xs text-gray-400">
                      {recoveryPerf.metric === 'pace' ? '/km basse' : 'bpm basse'}
                    </p>
                  </div>
                )}
              </div>
              <p className="text-xs text-gray-500">
                {recoveryPerf.deltaPct !== null && recoveryPerf.deltaPct > 0
                  ? recoveryPerf.metric === 'pace'
                    ? 'Planifiez vos séances qualité les jours où votre récupération est élevée.'
                    : 'FC plus basse quand vous êtes bien récupéré — meilleur rendement cardiaque.'
                  : 'Pas de différence significative détectée.'}
              </p>
              <div className="flex gap-3 text-xs text-gray-400">
                <span>{recoveryPerf.highCount} act. haute</span>
                <span>{recoveryPerf.lowCount} act. basse</span>
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

        {/* Carte 5 — Volume hebdo (Strava-only) */}
        <InsightCard
          title="Volume hebdo"
          icon={<BarChart3 className="h-3.5 w-3.5 text-blue-500" />}
          iconBgClass="bg-blue-50"
          borderColorClass="border-l-blue-500"
        >
          {!volumeTrend.hasData ? (
            <InsufficientData message="Pas assez d'activités récentes" />
          ) : (
            <div className="space-y-2">
              {volumeTrend.currentVsPrevPct !== null && (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-500">vs semaine précédente</span>
                  <TrendBadge value={volumeTrend.currentVsPrevPct} />
                </div>
              )}
              {volumeTrend.weeks.map((w) => (
                <MiniBar
                  key={w.label}
                  label={w.label}
                  value={w.distanceKm > 0 ? w.distanceKm : null}
                  maxValue={maxWeeklyKm}
                  colorClass="bg-blue-400"
                  unit="km"
                  count={w.count}
                />
              ))}
            </div>
          )}
        </InsightCard>

        {/* Carte 6 — Meilleur jour (Strava-only) */}
        <InsightCard
          title="Meilleur jour"
          icon={<Calendar className="h-3.5 w-3.5 text-cyan-500" />}
          iconBgClass="bg-cyan-50"
          borderColorClass="border-l-cyan-500"
        >
          {!bestDay.hasData ? (
            <InsufficientData />
          ) : bestDay.bestDay !== null ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold text-gray-900">{bestDay.bestDay}</span>
                <span className="text-sm text-gray-500">{formatPace(bestDay.bestPace!)} /km</span>
                {bestDay.globalAvgPace && bestDay.bestPace && (
                  <TrendBadge
                    value={((bestDay.globalAvgPace - bestDay.bestPace) / bestDay.globalAvgPace) * 100}
                    invertColor
                  />
                )}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {bestDay.days.map(d => (
                  <div
                    key={d.day}
                    className={`text-center px-2 py-1 rounded-md text-xs ${
                      d.day === bestDay.bestDay
                        ? 'bg-cyan-50 text-cyan-700 font-semibold'
                        : d.count > 0
                        ? 'bg-gray-50 text-gray-600'
                        : 'bg-gray-50 text-gray-300'
                    }`}
                  >
                    <div>{d.day}</div>
                    {d.avgPace ? (
                      <div className="font-medium">{formatPace(d.avgPace)}</div>
                    ) : (
                      <div>—</div>
                    )}
                  </div>
                ))}
              </div>
              <p className="text-xs text-gray-500">
                Moy. globale : {bestDay.globalAvgPace ? formatPace(bestDay.globalAvgPace) : '--'} /km
              </p>
            </div>
          ) : (
            <InsufficientData message="Min. 2 activités par jour pour comparer" />
          )}
        </InsightCard>

        {/* Carte 7 — Forme TSB */}
        <InsightCard
          title="Forme (TSB)"
          icon={<Zap className="h-3.5 w-3.5 text-amber-500" />}
          iconBgClass="bg-amber-50"
          borderColorClass="border-l-amber-500"
        >
          {!tsbZone.hasData ? (
            <InsufficientData message="Pas assez de données de charge d'entraînement" />
          ) : tsbZone.zone !== null ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={`inline-block w-2.5 h-2.5 rounded-full ${tsbZoneConfig[tsbZone.zone].dotColor}`} />
                  <span className={`text-sm font-semibold ${tsbZoneConfig[tsbZone.zone].textColor}`}>
                    {tsbZoneConfig[tsbZone.zone].label}
                  </span>
                </div>
                {tsbZone.trend7d !== null && (
                  <TrendBadge value={tsbZone.trend7d} suffix="" />
                )}
              </div>
              <div className="flex items-center gap-4 text-xs text-gray-500">
                <span>TSB : <span className="font-medium text-gray-700">{tsbZone.currentTsb?.toFixed(0)}</span></span>
                <span>CTL : <span className="font-medium text-gray-700">{tsbZone.chronicLoad?.toFixed(0)}</span></span>
                <span>ATL : <span className="font-medium text-gray-700">{tsbZone.acuteLoad?.toFixed(0)}</span></span>
              </div>
              <p className="text-xs text-gray-500">
                {tsbZoneConfig[tsbZone.zone].recommendation}
              </p>
            </div>
          ) : null}
        </InsightCard>
      </div>
    </div>
  )
}
