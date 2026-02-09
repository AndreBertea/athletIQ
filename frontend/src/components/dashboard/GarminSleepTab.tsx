import { useState, useMemo } from 'react'
import {
  PieChart, Pie, Cell,
  ComposedChart, Bar, Line,
  ResponsiveContainer, Tooltip as RechartsTooltip, XAxis, YAxis, Legend,
} from 'recharts'
import { Moon, Wind, Activity, Droplets, ChevronLeft, ChevronRight, Calendar } from 'lucide-react'
import { format, parseISO } from 'date-fns'
import { fr } from 'date-fns/locale'
import { useQuery } from '@tanstack/react-query'
import { garminService } from '../../services/garminService'
import type { GarminDailyEntry } from '../../services/garminService'

const SLEEP_RANGE_OPTIONS = [
  { days: 1, label: '1 nuit' },
  { days: 7, label: '7j' },
  { days: 30, label: '30j' },
  { days: 90, label: '3 mois' },
  { days: 180, label: '6 mois' },
]

function toLocaleDateStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

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
    { key: 'awake', label: 'Eveille', color: 'bg-gray-500', fill: '#6b7280', seconds: entry.awake_sleep_seconds },
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
// Vue detail d'une seule nuit (reutilisee en mode 1j et en hero multi-jour)
// ============================================================
function SleepNightDetail({ entry, showTitle }: { entry: GarminDailyEntry; showTitle?: boolean }) {
  const phases = buildPhases(entry)
  const hasPhases = phases.some(p => p.seconds > 0)
  const score = entry.sleep_score
  const sleepStart = entry.sleep_start_time
  const sleepEnd = entry.sleep_end_time
  const durationFormatted = formatMinutes(entry.sleep_duration_min)
  const hasLatestSleep = score !== null || sleepStart !== null || entry.sleep_duration_min !== null

  const donutData = [
    { name: 'Profond', value: entry.deep_sleep_seconds || 0, fill: '#4338ca' },
    { name: 'Leger', value: entry.light_sleep_seconds || 0, fill: '#60a5fa' },
    { name: 'REM', value: entry.rem_sleep_seconds || 0, fill: '#a78bfa' },
    { name: 'Eveille', value: entry.awake_sleep_seconds || 0, fill: '#6b7280' },
  ].filter(d => d.value > 0)

  if (!hasLatestSleep && !hasPhases) {
    return (
      <div className="flex items-center justify-center py-8 rounded-xl bg-gradient-to-br from-slate-900 to-indigo-950 text-indigo-400/60">
        <Moon className="h-6 w-6 mr-2" />
        <span className="text-sm">Aucune donnee de sommeil pour cette nuit</span>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* HERO : Score + Horaires + Duree */}
      {hasLatestSleep && (
        <div className="flex flex-col md:flex-row items-center gap-6 p-6 rounded-xl bg-gradient-to-br from-slate-900 to-indigo-950 text-white">
          {showTitle && (
            <div className="w-full md:hidden text-center mb-2">
              <p className="text-xs text-indigo-400/70">
                Nuit du {format(parseISO(entry.date), 'd MMMM yyyy', { locale: fr })}
              </p>
            </div>
          )}
          {/* Score circulaire */}
          {score !== null && (
            <div className="relative flex-shrink-0">
              <svg width="140" height="140" viewBox="0 0 140 140">
                <circle cx="70" cy="70" r="58" fill="none" stroke="#1e1b4b" strokeWidth="10" />
                <circle
                  cx="70" cy="70" r="58" fill="none"
                  stroke="#818cf8" strokeWidth="10" strokeLinecap="round"
                  strokeDasharray={`${(score / 100) * 364.4} 364.4`}
                  transform="rotate(-90 70 70)"
                  className="transition-all duration-1000"
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-4xl font-bold text-indigo-300">{score}</span>
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

      {/* BARRE DES PHASES */}
      {hasPhases && (
        <div>
          <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <Moon className="h-4 w-4 text-indigo-500" />
            Phases de sommeil
          </h4>
          {sleepStart && sleepEnd && (
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>{sleepStart}</span>
              <span>{sleepEnd}</span>
            </div>
          )}
          <div className="flex h-8 rounded-lg overflow-hidden shadow-inner">
            {phases.filter(p => p.seconds > 0).map(phase => (
              <div
                key={phase.key}
                className={`${phase.color} relative group cursor-pointer transition-opacity hover:opacity-80`}
                style={{ width: `${phase.pct}%` }}
              >
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-10">
                  <div className="bg-gray-900 text-white text-xs rounded px-2 py-1 whitespace-nowrap shadow-lg">
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
          <div className="flex flex-wrap gap-4 mt-3">
            {phases.filter(p => p.seconds > 0).map(phase => (
              <div key={phase.key} className="flex items-center gap-2">
                <div className={`w-3 h-3 rounded-full ${phase.color}`} />
                <span className="text-xs font-medium text-gray-700">{phase.label}</span>
                <span className="text-xs text-gray-500">{phase.formatted}</span>
                <span className="text-xs text-gray-400">({phase.pct.toFixed(0)}%)</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* DONUT + STATS */}
      {(donutData.length > 0 || entry.average_respiration !== null || entry.avg_sleep_stress !== null || entry.spo2 !== null) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {donutData.length > 0 && (
            <div className="flex flex-col items-center justify-center">
              <div className="relative">
                <PieChart width={200} height={200}>
                  <Pie
                    data={donutData}
                    cx="50%" cy="50%"
                    innerRadius={55} outerRadius={80}
                    paddingAngle={3}
                    dataKey="value"
                    strokeWidth={0}
                  >
                    {donutData.map((d) => (
                      <Cell key={d.name} fill={d.fill} />
                    ))}
                  </Pie>
                  <RechartsTooltip formatter={(value: number, name: string) => [formatSeconds(value), name]} />
                </PieChart>
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                  <div className="text-center">
                    <p className="text-lg font-bold text-gray-900">{durationFormatted}</p>
                    <p className="text-xs text-gray-500">Total</p>
                  </div>
                </div>
              </div>
            </div>
          )}
          <div className="flex flex-col gap-3">
            {entry.average_respiration !== null && (
              <div className="flex items-center gap-3 p-3 rounded-lg bg-cyan-50">
                <div className="p-2 rounded-lg bg-cyan-100">
                  <Wind className="h-5 w-5 text-cyan-600" />
                </div>
                <div>
                  <p className="text-xs text-cyan-600 font-medium">Respiration moyenne</p>
                  <p className="text-lg font-semibold text-cyan-700">{entry.average_respiration.toFixed(1)} <span className="text-sm font-normal">rpm</span></p>
                </div>
              </div>
            )}
            {entry.avg_sleep_stress !== null && (
              <div className="flex items-center gap-3 p-3 rounded-lg bg-orange-50">
                <div className="p-2 rounded-lg bg-orange-100">
                  <Activity className="h-5 w-5 text-orange-600" />
                </div>
                <div>
                  <p className="text-xs text-orange-600 font-medium">Stress sommeil</p>
                  <p className="text-lg font-semibold text-orange-700">{entry.avg_sleep_stress.toFixed(0)}</p>
                </div>
              </div>
            )}
            {entry.spo2 !== null && (
              <div className="flex items-center gap-3 p-3 rounded-lg bg-sky-50">
                <div className="p-2 rounded-lg bg-sky-100">
                  <Droplets className="h-5 w-5 text-sky-600" />
                </div>
                <div>
                  <p className="text-xs text-sky-600 font-medium">SpO2</p>
                  <p className="text-lg font-semibold text-sky-700">{entry.spo2}%</p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================
// Composant principal — fetch autonome des donnees
// ============================================================
export default function GarminSleepTab() {
  const [sleepRange, setSleepRange] = useState(7)
  const [selectedDateIdx, setSelectedDateIdx] = useState(-1) // -1 = derniere date dispo

  const isSingleDay = sleepRange === 1

  // Fetch autonome : la plage API = sleepRange (ou 30j en mode 1-nuit pour la navigation)
  const fetchDays = isSingleDay ? 30 : sleepRange
  const { data: rawData, isLoading } = useQuery({
    queryKey: ['garmin-sleep', fetchDays],
    queryFn: () => {
      const end = toLocaleDateStr(new Date())
      const start = new Date()
      start.setDate(start.getDate() - fetchDays)
      return garminService.getGarminDaily(toLocaleDateStr(start), end)
    },
    staleTime: 5 * 60_000,
  })

  const data = rawData ?? []

  // Dates disponibles (triees chronologiquement)
  const availableDates = useMemo(() => {
    if (data.length === 0) return []
    return data.map(d => d.date)
  }, [data])

  // En mode multi-jours, les donnees API correspondent deja a la plage voulue
  const filteredData = data

  // En mode 1j : entree selectionnee
  const currentDateIdx = useMemo(() => {
    if (!isSingleDay || availableDates.length === 0) return -1
    if (selectedDateIdx === -1 || selectedDateIdx >= availableDates.length) {
      return availableDates.length - 1
    }
    return selectedDateIdx
  }, [isSingleDay, selectedDateIdx, availableDates])

  const selectedEntry = useMemo(() => {
    if (isSingleDay && currentDateIdx >= 0 && currentDateIdx < data.length) {
      return data[currentDateIdx]
    }
    return null
  }, [isSingleDay, currentDateIdx, data])

  // Derniere entree pour le mode multi-jours
  const latest = filteredData.length > 0 ? filteredData[filteredData.length - 1] : null

  // Donnees pour le graphique de tendances
  const trendData = useMemo(() => {
    if (isSingleDay) return []
    return filteredData.map(entry => ({
      date: entry.date,
      dateFormatted: format(parseISO(entry.date), 'd MMM', { locale: fr }),
      sleep_score: entry.sleep_score,
      deep_min: entry.deep_sleep_seconds ? Math.round(entry.deep_sleep_seconds / 60) : 0,
      light_min: entry.light_sleep_seconds ? Math.round(entry.light_sleep_seconds / 60) : 0,
      rem_min: entry.rem_sleep_seconds ? Math.round(entry.rem_sleep_seconds / 60) : 0,
      awake_min: entry.awake_sleep_seconds ? Math.round(entry.awake_sleep_seconds / 60) : 0,
      sleep_start_time: entry.sleep_start_time,
      sleep_end_time: entry.sleep_end_time,
      sleep_duration_min: entry.sleep_duration_min,
    }))
  }, [filteredData, isSingleDay])

  // Navigation dates (mode 1j)
  const canGoPrev = currentDateIdx > 0
  const canGoNext = currentDateIdx < availableDates.length - 1

  const goPrev = () => {
    if (canGoPrev) setSelectedDateIdx(currentDateIdx - 1)
  }
  const goNext = () => {
    if (canGoNext) setSelectedDateIdx(currentDateIdx + 1)
  }

  // Quand on change de range, reset la selection de date
  const handleRangeChange = (days: number) => {
    setSleepRange(days)
    setSelectedDateIdx(-1)
  }

  // --- Chargement ---
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-gray-400">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500 mr-3" />
        <span className="text-sm">Chargement des donnees de sommeil...</span>
      </div>
    )
  }

  // --- Aucune donnee ---
  if (data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-gray-400">
        <Moon className="h-12 w-12 mb-3 text-gray-300" />
        <p className="text-sm font-medium">Aucune donnee de sommeil</p>
        <p className="text-xs text-gray-400 mt-1">Synchronisez vos donnees Garmin pour voir vos statistiques de sommeil</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* =========================================================
          FILTRES DE PERIODE (toujours en haut)
          ========================================================= */}
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <Moon className="h-4 w-4 text-indigo-500" />
          {isSingleDay ? 'Detail nuit' : 'Tendances sommeil'}
        </h4>
        <div className="flex gap-1">
          {SLEEP_RANGE_OPTIONS.map(opt => (
            <button
              key={opt.days}
              onClick={() => handleRangeChange(opt.days)}
              className={`px-3 py-1 text-xs rounded-full transition-colors ${
                sleepRange === opt.days
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* =========================================================
          MODE 1 NUIT — Navigation de date + detail complet
          ========================================================= */}
      {isSingleDay && (
        <>
          {/* Selecteur de date */}
          <div className="flex items-center justify-center gap-4">
            <button
              onClick={goPrev}
              disabled={!canGoPrev}
              className={`p-2 rounded-lg transition-colors ${
                canGoPrev
                  ? 'text-gray-700 hover:bg-gray-100'
                  : 'text-gray-300 cursor-not-allowed'
              }`}
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <div className="flex items-center gap-2 px-4 py-2 bg-indigo-50 rounded-lg">
              <Calendar className="h-4 w-4 text-indigo-500" />
              <span className="text-sm font-semibold text-indigo-700">
                {selectedEntry
                  ? format(parseISO(selectedEntry.date), 'EEEE d MMMM yyyy', { locale: fr })
                  : '--'}
              </span>
            </div>
            <button
              onClick={goNext}
              disabled={!canGoNext}
              className={`p-2 rounded-lg transition-colors ${
                canGoNext
                  ? 'text-gray-700 hover:bg-gray-100'
                  : 'text-gray-300 cursor-not-allowed'
              }`}
            >
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>

          {/* Detail de la nuit selectionnee */}
          {selectedEntry ? (
            <SleepNightDetail entry={selectedEntry} showTitle />
          ) : (
            <div className="flex items-center justify-center py-8 rounded-xl bg-gradient-to-br from-slate-900 to-indigo-950 text-indigo-400/60">
              <Moon className="h-6 w-6 mr-2" />
              <span className="text-sm">Aucune donnee pour cette date</span>
            </div>
          )}
        </>
      )}

      {/* =========================================================
          MODE MULTI-JOURS — Hero derniere nuit + Tendances
          ========================================================= */}
      {!isSingleDay && (
        <>
          {/* Detail de la derniere nuit */}
          {latest ? (
            <SleepNightDetail entry={latest} />
          ) : (
            <div className="flex items-center justify-center py-8 rounded-xl bg-gradient-to-br from-slate-900 to-indigo-950 text-indigo-400/60">
              <Moon className="h-6 w-6 mr-2" />
              <span className="text-sm">Aucune donnee de sommeil sur cette periode</span>
            </div>
          )}

          {/* Graphique de tendances */}
          {trendData.length > 1 && (
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
                <Moon className="h-4 w-4 text-indigo-500" />
                Evolution sur {SLEEP_RANGE_OPTIONS.find(o => o.days === sleepRange)?.label}
              </h4>
              <div className="h-[320px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={trendData} margin={{ top: 5, right: 10, left: 10, bottom: 0 }}>
                    <XAxis
                      dataKey="dateFormatted"
                      tick={{ fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      minTickGap={20}
                    />
                    <YAxis
                      yAxisId="left"
                      tick={{ fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      width={45}
                      tickFormatter={(v: number) => `${Math.round(v / 60)}h`}
                    />
                    <YAxis
                      yAxisId="right"
                      orientation="right"
                      domain={[0, 100]}
                      tick={{ fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      width={35}
                    />
                    <RechartsTooltip
                      content={({ active, payload, label }) => {
                        if (!active || !payload || payload.length === 0) return null
                        const d = filteredData.find(e => format(parseISO(e.date), 'd MMM', { locale: fr }) === label)
                        if (!d) return null
                        return (
                          <div className="rounded-lg border bg-white p-3 shadow-md text-sm">
                            <p className="font-semibold text-gray-900 mb-2">{format(parseISO(d.date), 'd MMMM yyyy', { locale: fr })}</p>
                            <div className="space-y-1">
                              {d.sleep_score !== null && (
                                <div className="flex justify-between gap-4">
                                  <span className="text-gray-500">Score</span>
                                  <span className="font-medium text-indigo-600">{d.sleep_score}</span>
                                </div>
                              )}
                              {d.sleep_duration_min !== null && (
                                <div className="flex justify-between gap-4">
                                  <span className="text-gray-500">Duree</span>
                                  <span className="font-medium text-sky-600">{formatMinutes(d.sleep_duration_min)}</span>
                                </div>
                              )}
                              {d.sleep_start_time && d.sleep_end_time && (
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
                              {d.light_sleep_seconds !== null && (
                                <div className="flex justify-between gap-4">
                                  <span className="text-gray-500">Leger</span>
                                  <span className="font-medium" style={{ color: '#60a5fa' }}>{formatSeconds(d.light_sleep_seconds)}</span>
                                </div>
                              )}
                              {d.rem_sleep_seconds !== null && (
                                <div className="flex justify-between gap-4">
                                  <span className="text-gray-500">REM</span>
                                  <span className="font-medium" style={{ color: '#a78bfa' }}>{formatSeconds(d.rem_sleep_seconds)}</span>
                                </div>
                              )}
                              {d.awake_sleep_seconds !== null && (
                                <div className="flex justify-between gap-4">
                                  <span className="text-gray-500">Eveille</span>
                                  <span className="font-medium text-gray-600">{formatSeconds(d.awake_sleep_seconds)}</span>
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
                    <Bar yAxisId="left" dataKey="awake_min" name="Eveille" stackId="sleep" fill="#6b7280" radius={[2, 2, 0, 0]} />
                    <Line yAxisId="right" type="monotone" dataKey="sleep_score" name="Score" stroke="#818cf8" strokeWidth={2.5} dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
