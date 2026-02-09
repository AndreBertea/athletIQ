import { useMemo } from 'react'
import {
  ComposedChart, Bar, Line,
  ResponsiveContainer, Tooltip as RechartsTooltip, XAxis, YAxis, Legend,
} from 'recharts'
import { Moon, Wind, Activity, Droplets } from 'lucide-react'
import { format, parseISO } from 'date-fns'
import { fr } from 'date-fns/locale'
import type { GarminDailyEntry } from '../../services/garminService'
import { formatBucketLabel, getBucketKey, GRANULARITY_DESCRIPTIONS, GRANULARITY_LABELS, type TimeGranularity } from '../../utils/timeBuckets'

function formatMinutes(min: number | null): string {
  if (min === null) return '--'
  const h = Math.floor(min / 60)
  const m = Math.round(min % 60)
  return `${h}h ${m.toString().padStart(2, '0')}min`
}

function formatSeconds(s: number | null): string {
  if (s === null || s === 0) return '0min'
  const h = Math.floor(s / 3600)
  const m = Math.round((s % 3600) / 60)
  return h > 0 ? `${h}h ${m.toString().padStart(2, '0')}min` : `${m}min`
}

function hasSleepData(entry: GarminDailyEntry): boolean {
  if (entry.sleep_score !== null) return true
  if (entry.sleep_duration_min !== null) return true
  if (entry.sleep_start_time !== null || entry.sleep_end_time !== null) return true
  const totalSeconds =
    (entry.deep_sleep_seconds || 0) +
    (entry.light_sleep_seconds || 0) +
    (entry.rem_sleep_seconds || 0) +
    (entry.awake_sleep_seconds || 0)
  return totalSeconds > 0
}

/** Couleur conditionnelle du score sommeil : vert >=85, orange 70-84, rouge <70 */
function scoreColor(score: number): string {
  if (score >= 85) return '#22c55e'
  if (score >= 70) return '#f59e0b'
  return '#ef4444'
}

function scoreStrokeColor(score: number): string {
  if (score >= 85) return '#22c55e'
  if (score >= 70) return '#f59e0b'
  return '#ef4444'
}

interface PhaseInfo {
  key: string
  label: string
  color: string
  fill: string
  seconds: number
  pct: number
  formatted: string
}

function buildPhases(entry: GarminDailyEntry): PhaseInfo[] {
  const raw = [
    { key: 'deep', label: 'Profond', color: 'bg-indigo-700', fill: '#4338ca', seconds: entry.deep_sleep_seconds },
    { key: 'light', label: 'Leger', color: 'bg-blue-400', fill: '#60a5fa', seconds: entry.light_sleep_seconds },
    { key: 'rem', label: 'REM', color: 'bg-violet-400', fill: '#a78bfa', seconds: entry.rem_sleep_seconds },
    { key: 'awake', label: 'Eveille', color: 'bg-gray-400', fill: '#9ca3af', seconds: entry.awake_sleep_seconds },
  ]
  const total = raw.reduce((sum, p) => sum + (p.seconds || 0), 0)
  return raw.map(p => ({
    ...p,
    seconds: p.seconds || 0,
    pct: total > 0 ? ((p.seconds || 0) / total) * 100 : 0,
    formatted: formatSeconds(p.seconds),
  }))
}

// ============================================================
// Vue detail d'une seule nuit
// ============================================================
function SleepNightDetail({ entry, showTitle }: { entry: GarminDailyEntry; showTitle?: boolean }) {
  const phases = buildPhases(entry)
  const hasPhases = phases.some(p => p.seconds > 0)
  const score = entry.sleep_score
  const sleepStart = entry.sleep_start_time
  const sleepEnd = entry.sleep_end_time
  const durationFormatted = formatMinutes(entry.sleep_duration_min)
  const hasLatestSleep = score !== null || sleepStart !== null || entry.sleep_duration_min !== null

  if (!hasLatestSleep && !hasPhases) {
    return (
      <div className="flex flex-col items-center justify-center py-12 rounded-2xl bg-gradient-to-br from-slate-900 to-indigo-950 text-indigo-400/60">
        <Moon className="h-10 w-10 mb-3" />
        <p className="text-sm font-medium">Aucune donnee de sommeil pour cette nuit</p>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* HERO : Score + Horaires + Duree */}
      {hasLatestSleep && (
        <div className="flex flex-col md:flex-row items-center gap-6 p-6 rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900 to-indigo-950 text-white transition-all duration-300">
          {showTitle && (
            <div className="w-full md:hidden text-center mb-2">
              <p className="text-xs text-indigo-400/70">
                Nuit du {format(parseISO(entry.date), 'd MMMM yyyy', { locale: fr })}
              </p>
            </div>
          )}
          {/* Score circulaire avec couleur conditionnelle */}
          {score !== null && (
            <div className="relative flex-shrink-0">
              <svg width="140" height="140" viewBox="0 0 140 140">
                <circle cx="70" cy="70" r="58" fill="none" stroke="#1e1b4b" strokeWidth="10" />
                <circle
                  cx="70" cy="70" r="58" fill="none"
                  stroke={scoreStrokeColor(score)} strokeWidth="10" strokeLinecap="round"
                  strokeDasharray={`${(score / 100) * 364.4} 364.4`}
                  transform="rotate(-90 70 70)"
                  className="transition-all duration-1000"
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-4xl font-bold" style={{ color: scoreColor(score) }}>{score}</span>
                <span className="text-xs text-indigo-400/70">/ 100</span>
              </div>
            </div>
          )}
          {/* Horaires et duree */}
          <div className="flex-1 grid grid-cols-2 gap-4">
            {sleepStart !== null && (
              <div className="text-center md:text-left">
                <p className="text-xs text-purple-400 uppercase tracking-wider mb-1">Coucher</p>
                <p className="text-2xl font-semibold text-purple-300">{sleepStart}</p>
              </div>
            )}
            {sleepEnd !== null && (
              <div className="text-center md:text-left">
                <p className="text-xs text-amber-400 uppercase tracking-wider mb-1">Reveil</p>
                <p className="text-2xl font-semibold text-amber-300">{sleepEnd}</p>
              </div>
            )}
            {entry.sleep_duration_min !== null && (
              <div className="col-span-2 text-center md:text-left">
                <p className="text-xs text-sky-400 uppercase tracking-wider mb-1">Duree totale</p>
                <p className="text-2xl font-semibold text-sky-300">{durationFormatted}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* PHASES DE SOMMEIL — Barre + Mini-cartes */}
      {hasPhases && (
        <div>
          <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <Moon className="h-4 w-4 text-indigo-500" />
            Phases de sommeil
          </h4>
          {/* Barre horizontale des phases */}
          {sleepStart && sleepEnd && (
            <div className="flex justify-between text-xs text-gray-400 mb-1">
              <span>{sleepStart}</span>
              <span>{sleepEnd}</span>
            </div>
          )}
          <div className="flex h-7 rounded-lg overflow-hidden">
            {phases.filter(p => p.seconds > 0).map(phase => (
              <div
                key={phase.key}
                className={`${phase.color} relative group cursor-pointer transition-opacity hover:opacity-80`}
                style={{ width: `${phase.pct}%` }}
              >
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-10">
                  <div className="bg-gray-900 text-white text-xs rounded-lg px-3 py-2 whitespace-nowrap shadow-lg">
                    {phase.label}: {phase.formatted} ({phase.pct.toFixed(0)}%)
                  </div>
                </div>
                {phase.pct > 15 && (
                  <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-white/90">
                    {phase.formatted}
                  </span>
                )}
              </div>
            ))}
          </div>
          {/* Mini-cartes des phases */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
            {phases.filter(p => p.seconds > 0).map(phase => (
              <div key={phase.key} className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                <div className="flex items-center gap-2 mb-1">
                  <div className={`w-2.5 h-2.5 rounded-full ${phase.color}`} />
                  <span className="text-xs font-medium text-gray-500">{phase.label}</span>
                </div>
                <p className="text-lg font-semibold text-gray-900">{phase.formatted}</p>
                <p className="text-xs text-gray-400">{phase.pct.toFixed(0)}%</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* STATS SECONDAIRES — card-metric */}
      {(entry.average_respiration !== null || entry.avg_sleep_stress !== null || entry.spo2 !== null) && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {entry.average_respiration !== null && (
            <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-lg bg-cyan-100">
                  <Wind className="h-5 w-5 text-cyan-600" />
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Respiration</p>
                  <p className="text-lg font-bold text-gray-900">
                    {entry.average_respiration.toFixed(1)}
                    <span className="text-sm font-normal text-gray-400 ml-1">rpm</span>
                  </p>
                </div>
              </div>
            </div>
          )}
          {entry.avg_sleep_stress !== null && (
            <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-lg bg-orange-100">
                  <Activity className="h-5 w-5 text-orange-600" />
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Stress sommeil</p>
                  <p className="text-lg font-bold text-gray-900">{entry.avg_sleep_stress.toFixed(0)}</p>
                </div>
              </div>
            </div>
          )}
          {entry.spo2 !== null && (
            <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-lg bg-sky-100">
                  <Droplets className="h-5 w-5 text-sky-600" />
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">SpO2</p>
                  <p className="text-lg font-bold text-gray-900">
                    {entry.spo2}
                    <span className="text-sm font-normal text-gray-400 ml-1">%</span>
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================
// Composant principal — piloté par la topbar
// ============================================================
interface GarminSleepTabProps {
  data: GarminDailyEntry[]
  granularity: TimeGranularity
  periodLabel?: string
}

interface SleepTrendPoint {
  dateKey: string
  dateLabel: string
  sleep_score: number | null
  deep_min: number
  light_min: number
  rem_min: number
  awake_min: number
  deep_sleep_seconds: number | null
  light_sleep_seconds: number | null
  rem_sleep_seconds: number | null
  awake_sleep_seconds: number | null
  sleep_duration_min: number | null
  sleep_start_time?: string | null
  sleep_end_time?: string | null
}

function aggregateSleepTrend(data: GarminDailyEntry[], granularity: TimeGranularity): SleepTrendPoint[] {
  if (!data || data.length === 0) return []

  if (granularity === 'day') {
    return data.map(entry => ({
      dateKey: entry.date,
      dateLabel: formatBucketLabel(entry.date, granularity),
      sleep_score: entry.sleep_score,
      deep_min: entry.deep_sleep_seconds ? Math.round(entry.deep_sleep_seconds / 60) : 0,
      light_min: entry.light_sleep_seconds ? Math.round(entry.light_sleep_seconds / 60) : 0,
      rem_min: entry.rem_sleep_seconds ? Math.round(entry.rem_sleep_seconds / 60) : 0,
      awake_min: entry.awake_sleep_seconds ? Math.round(entry.awake_sleep_seconds / 60) : 0,
      deep_sleep_seconds: entry.deep_sleep_seconds,
      light_sleep_seconds: entry.light_sleep_seconds,
      rem_sleep_seconds: entry.rem_sleep_seconds,
      awake_sleep_seconds: entry.awake_sleep_seconds,
      sleep_duration_min: entry.sleep_duration_min,
      sleep_start_time: entry.sleep_start_time,
      sleep_end_time: entry.sleep_end_time,
    }))
  }

  const buckets = new Map<string, {
    counts: Record<string, number>
    sums: Record<string, number>
  }>()

  for (const entry of data) {
    if (!hasSleepData(entry)) continue
    const key = getBucketKey(entry.date, granularity)
    const bucket = buckets.get(key) ?? { counts: {}, sums: {} }

    const numericFields: Array<[string, number | null]> = [
      ['sleep_score', entry.sleep_score],
      ['sleep_duration_min', entry.sleep_duration_min],
      ['deep_sleep_seconds', entry.deep_sleep_seconds],
      ['light_sleep_seconds', entry.light_sleep_seconds],
      ['rem_sleep_seconds', entry.rem_sleep_seconds],
      ['awake_sleep_seconds', entry.awake_sleep_seconds],
    ]

    for (const [field, value] of numericFields) {
      if (typeof value === 'number') {
        bucket.sums[field] = (bucket.sums[field] ?? 0) + value
        bucket.counts[field] = (bucket.counts[field] ?? 0) + 1
      }
    }

    buckets.set(key, bucket)
  }

  return Array.from(buckets.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, bucket]) => {
      const avgScore = bucket.counts.sleep_score ? bucket.sums.sleep_score / bucket.counts.sleep_score : null
      const avgDuration = bucket.counts.sleep_duration_min ? bucket.sums.sleep_duration_min / bucket.counts.sleep_duration_min : null
      const avgDeep = bucket.counts.deep_sleep_seconds ? bucket.sums.deep_sleep_seconds / bucket.counts.deep_sleep_seconds : null
      const avgLight = bucket.counts.light_sleep_seconds ? bucket.sums.light_sleep_seconds / bucket.counts.light_sleep_seconds : null
      const avgRem = bucket.counts.rem_sleep_seconds ? bucket.sums.rem_sleep_seconds / bucket.counts.rem_sleep_seconds : null
      const avgAwake = bucket.counts.awake_sleep_seconds ? bucket.sums.awake_sleep_seconds / bucket.counts.awake_sleep_seconds : null

      return {
        dateKey: key,
        dateLabel: formatBucketLabel(key, granularity),
        sleep_score: avgScore,
        sleep_duration_min: avgDuration,
        deep_sleep_seconds: avgDeep,
        light_sleep_seconds: avgLight,
        rem_sleep_seconds: avgRem,
        awake_sleep_seconds: avgAwake,
        deep_min: avgDeep ? Math.round(avgDeep / 60) : 0,
        light_min: avgLight ? Math.round(avgLight / 60) : 0,
        rem_min: avgRem ? Math.round(avgRem / 60) : 0,
        awake_min: avgAwake ? Math.round(avgAwake / 60) : 0,
      }
    })
}

export default function GarminSleepTab({ data, granularity, periodLabel }: GarminSleepTabProps) {
  const sortedData = useMemo(() => {
    if (!data || data.length === 0) return []
    return [...data].sort((a, b) => a.date.localeCompare(b.date))
  }, [data])

  const granularityLabel = GRANULARITY_LABELS[granularity]
  const granularityDescription = GRANULARITY_DESCRIPTIONS[granularity]
  const isAggregated = granularity !== 'day'

  const latest = useMemo(() => {
    if (sortedData.length === 0) return null
    const latestWithSleep = [...sortedData].reverse().find(hasSleepData)
    return latestWithSleep ?? sortedData[sortedData.length - 1]
  }, [sortedData])

  const summaryKpis = useMemo(() => {
    if (sortedData.length === 0) return null
    const withSleep = sortedData.filter(hasSleepData)
    if (withSleep.length === 0) return null

    const scores = withSleep.map(d => d.sleep_score).filter((v): v is number => v !== null)
    const durations = withSleep.map(d => d.sleep_duration_min).filter((v): v is number => v !== null)

    return {
      avgScore: scores.length > 0 ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null,
      avgDuration: durations.length > 0 ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length) : null,
      nightsCount: withSleep.length,
    }
  }, [sortedData])

  const trendData = useMemo(
    () => aggregateSleepTrend(sortedData, granularity),
    [sortedData, granularity],
  )

  if (sortedData.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-gray-400">
        <Moon className="h-10 w-10 mb-3 text-gray-300" />
        <p className="text-sm font-medium text-gray-500">Aucune donnee de sommeil</p>
        <p className="text-xs text-gray-400 mt-1">Synchronisez vos donnees Garmin pour voir vos statistiques de sommeil</p>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <Moon className="h-4 w-4 text-indigo-500" />
          Tendances sommeil
        </h4>
        <p className="text-xs text-gray-400">
          Periode {periodLabel ?? `${sortedData.length}j`} • Temporalite {granularityLabel}
        </p>
      </div>

      {/* KPIs resume de la periode */}
      {summaryKpis && (
        <div className="grid grid-cols-3 gap-3">
          {summaryKpis.avgScore !== null && (
            <div className="bg-gray-50 rounded-lg p-3 border border-gray-100 text-center">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Score moy.</p>
              <p className="text-xl font-bold text-gray-900">{summaryKpis.avgScore}</p>
            </div>
          )}
          {summaryKpis.avgDuration !== null && (
            <div className="bg-gray-50 rounded-lg p-3 border border-gray-100 text-center">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Duree moy.</p>
              <p className="text-xl font-bold text-gray-900">{formatMinutes(summaryKpis.avgDuration)}</p>
            </div>
          )}
          <div className="bg-gray-50 rounded-lg p-3 border border-gray-100 text-center">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Nuits</p>
            <p className="text-xl font-bold text-gray-900">{summaryKpis.nightsCount}</p>
          </div>
        </div>
      )}

      {/* Detail de la derniere nuit */}
      {latest ? (
        <SleepNightDetail entry={latest} />
      ) : (
        <div className="flex flex-col items-center justify-center py-12 rounded-2xl bg-gradient-to-br from-slate-900 to-indigo-950 text-indigo-400/60">
          <Moon className="h-10 w-10 mb-3" />
          <p className="text-sm font-medium">Aucune donnee de sommeil sur cette periode</p>
        </div>
      )}

      {/* Graphique de tendances */}
      {trendData.length > 1 && (
        <div>
          <h4 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Moon className="h-4 w-4 text-indigo-500" />
            Evolution {isAggregated ? `(moyennes ${granularityDescription})` : ''}
          </h4>
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={trendData} margin={{ top: 5, right: 10, left: 10, bottom: 0 }}>
                <XAxis
                  dataKey="dateLabel"
                  tick={{ fontSize: 11, fill: '#9ca3af' }}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={20}
                />
                <YAxis
                  yAxisId="left"
                  tick={{ fontSize: 11, fill: '#9ca3af' }}
                  tickLine={false}
                  axisLine={false}
                  width={45}
                  tickFormatter={(v: number) => `${Math.round(v / 60)}h`}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  domain={[0, 100]}
                  tick={{ fontSize: 11, fill: '#9ca3af' }}
                  tickLine={false}
                  axisLine={false}
                  width={35}
                />
                <RechartsTooltip
                  content={({ active, payload }) => {
                    if (!active || !payload || payload.length === 0) return null
                    const d = payload[0]?.payload as SleepTrendPoint
                    if (!d?.dateKey) return null
                    const title = isAggregated
                      ? d.dateLabel
                      : format(parseISO(d.dateKey), 'd MMMM yyyy', { locale: fr })

                    return (
                      <div className="rounded-lg border border-gray-200/60 bg-white p-3 shadow-lg text-sm">
                        <p className="font-semibold text-gray-900 mb-2">{title}</p>
                        <div className="space-y-1">
                          {d.sleep_score !== null && (
                            <div className="flex justify-between gap-4">
                              <span className="text-gray-500">{isAggregated ? 'Score moy.' : 'Score'}</span>
                              <span className="font-medium text-indigo-600">{Math.round(d.sleep_score)}</span>
                            </div>
                          )}
                          {d.sleep_duration_min !== null && (
                            <div className="flex justify-between gap-4">
                              <span className="text-gray-500">{isAggregated ? 'Duree moy.' : 'Duree'}</span>
                              <span className="font-medium text-sky-600">{formatMinutes(d.sleep_duration_min)}</span>
                            </div>
                          )}
                          {!isAggregated && d.sleep_start_time && d.sleep_end_time && (
                            <div className="flex justify-between gap-4">
                              <span className="text-gray-500">Horaires</span>
                              <span className="font-medium text-purple-600">{d.sleep_start_time} - {d.sleep_end_time}</span>
                            </div>
                          )}
                          {d.deep_sleep_seconds !== null && (
                            <div className="flex justify-between gap-4">
                              <span className="text-gray-500">Profond</span>
                              <span className="font-medium" style={{ color: '#4338ca' }}>{formatSeconds(d.deep_sleep_seconds)}</span>
                            </div>
                          )}
                          {d.rem_sleep_seconds !== null && (
                            <div className="flex justify-between gap-4">
                              <span className="text-gray-500">REM</span>
                              <span className="font-medium" style={{ color: '#a78bfa' }}>{formatSeconds(d.rem_sleep_seconds)}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    )
                  }}
                />
                <Legend
                  verticalAlign="bottom"
                  iconType="square"
                  wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                />
                <Bar yAxisId="left" dataKey="deep_min" name="Profond" stackId="sleep" fill="#4338ca" radius={[0, 0, 0, 0]} />
                <Bar yAxisId="left" dataKey="light_min" name="Leger" stackId="sleep" fill="#60a5fa" />
                <Bar yAxisId="left" dataKey="rem_min" name="REM" stackId="sleep" fill="#a78bfa" />
                <Bar yAxisId="left" dataKey="awake_min" name="Eveille" stackId="sleep" fill="#9ca3af" radius={[2, 2, 0, 0]} />
                <Line yAxisId="right" type="monotone" dataKey="sleep_score" name="Score" stroke="#818cf8" strokeWidth={2.5} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  )
}
