import { useState, useMemo } from 'react'
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Watch, TrendingUp, TrendingDown, Minus, Heart, Brain, Moon, Activity, Weight, Droplets } from 'lucide-react'
import { format, parseISO } from 'date-fns'
import { fr } from 'date-fns/locale'
import type { GarminDailyEntry } from '../../services/garminService'
import GarminSleepTab from './GarminSleepTab'

interface GarminDailyMonitorProps {
  data: GarminDailyEntry[]
  isLoading: boolean
  isConnected: boolean
}

interface MetricConfig {
  key: string
  label: string
  color: string
}

const METRICS: MetricConfig[] = [
  { key: 'hrv_rmssd', label: 'HRV', color: '#8b5cf6' },
  { key: 'training_readiness', label: 'Readiness', color: '#f59e0b' },
  { key: 'sleep_score', label: 'Sommeil', color: '#3b82f6' },
  { key: 'stress_score', label: 'Stress', color: '#ef4444' },
  { key: 'body_battery_max', label: 'Body Battery', color: '#10b981' },
  { key: 'resting_hr', label: 'FC repos', color: '#f43f5e' },
]

const DEFAULT_VISIBLE = new Set(['hrv_rmssd', 'training_readiness', 'sleep_score'])

function avg7d(data: GarminDailyEntry[], key: keyof GarminDailyEntry): number | null {
  const last7 = data.slice(-7)
  const values = last7.map(d => d[key]).filter((v): v is number => v !== null && typeof v === 'number')
  if (values.length === 0) return null
  return values.reduce((a, b) => a + b, 0) / values.length
}

function avg7dPrev(data: GarminDailyEntry[], key: keyof GarminDailyEntry): number | null {
  if (data.length < 8) return null
  const prev7 = data.slice(-14, -7)
  const values = prev7.map(d => d[key]).filter((v): v is number => v !== null && typeof v === 'number')
  if (values.length === 0) return null
  return values.reduce((a, b) => a + b, 0) / values.length
}

function TrendArrow({ current, previous }: { current: number | null; previous: number | null }) {
  if (current === null || previous === null) return null
  const diff = current - previous
  if (Math.abs(diff) < 0.5) return <Minus className="h-3.5 w-3.5 text-gray-400" />
  if (diff > 0) return <TrendingUp className="h-3.5 w-3.5 text-green-500" />
  return <TrendingDown className="h-3.5 w-3.5 text-red-500" />
}

export default function GarminDailyMonitor({ data, isLoading, isConnected }: GarminDailyMonitorProps) {
  const [activeTab, setActiveTab] = useState<'monitoring' | 'sleep'>('monitoring')
  const [visibleMetrics, setVisibleMetrics] = useState<Set<string>>(new Set(DEFAULT_VISIBLE))

  const orderedData = useMemo(() => {
    if (!data || data.length === 0) return []
    return [...data].sort((a, b) => a.date.localeCompare(b.date))
  }, [data])

  const toggleMetric = (key: string) => {
    setVisibleMetrics(prev => {
      const next = new Set(prev)
      if (next.has(key)) {
        if (next.size > 1) next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  // Mini-cartes recapitulatives
  const summaryCards = useMemo(() => {
    if (orderedData.length === 0) return null

    const hrvAvg = avg7d(orderedData, 'hrv_rmssd')
    const hrvPrev = avg7dPrev(orderedData, 'hrv_rmssd')
    const readinessAvg = avg7d(orderedData, 'training_readiness')
    const readinessPrev = avg7dPrev(orderedData, 'training_readiness')
    const sleepAvg = avg7d(orderedData, 'sleep_score')
    const sleepPrev = avg7dPrev(orderedData, 'sleep_score')
    const latestRhr = orderedData[orderedData.length - 1]?.resting_hr
    const rhrAvg = avg7d(orderedData, 'resting_hr')
    const rhrPrev = avg7dPrev(orderedData, 'resting_hr')
    const latestVo2 = orderedData[orderedData.length - 1]?.vo2max_estimated
    const latestWeight = orderedData[orderedData.length - 1]?.weight_kg

    const cards: Array<{
      label: string
      value: string
      unit: string
      icon: typeof Heart
      color: string
      bgColor: string
      trend: { current: number | null; previous: number | null }
      subtitle?: string
    }> = [
      {
        label: 'HRV moy. 7j',
        value: hrvAvg !== null ? hrvAvg.toFixed(0) : '--',
        unit: 'ms',
        icon: Heart,
        color: 'text-violet-600',
        bgColor: 'bg-violet-100',
        trend: { current: hrvAvg, previous: hrvPrev },
      },
      {
        label: 'Readiness moy. 7j',
        value: readinessAvg !== null ? readinessAvg.toFixed(0) : '--',
        unit: '',
        icon: Brain,
        color: 'text-amber-600',
        bgColor: 'bg-amber-100',
        trend: { current: readinessAvg, previous: readinessPrev },
      },
      {
        label: 'Sleep Score moy. 7j',
        value: sleepAvg !== null ? sleepAvg.toFixed(0) : '--',
        unit: '',
        icon: Moon,
        color: 'text-indigo-600',
        bgColor: 'bg-indigo-100',
        trend: { current: sleepAvg, previous: sleepPrev },
      },
      {
        label: 'Resting HR',
        value: latestRhr !== null && latestRhr !== undefined ? `${latestRhr}` : '--',
        unit: 'bpm',
        icon: Activity,
        color: 'text-rose-600',
        bgColor: 'bg-rose-100',
        subtitle: rhrAvg !== null ? `Moy. 7j : ${rhrAvg.toFixed(0)} bpm` : undefined,
        trend: { current: rhrAvg, previous: rhrPrev },
      },
    ]

    if (latestVo2 != null) {
      cards.push({
        label: 'VO2max',
        value: latestVo2.toFixed(0),
        unit: 'ml/kg/min',
        icon: Activity,
        color: 'text-emerald-600',
        bgColor: 'bg-emerald-100',
        trend: { current: null, previous: null },
      })
    }

    if (latestWeight != null) {
      cards.push({
        label: 'Poids',
        value: latestWeight.toFixed(1),
        unit: 'kg',
        icon: Weight,
        color: 'text-gray-600',
        bgColor: 'bg-gray-200',
        trend: { current: null, previous: null },
      })
    }

    return cards
  }, [orderedData])

  // Badges secondaires (derniere entree)
  const latestBadges = useMemo(() => {
    if (orderedData.length === 0) return null
    const latest = orderedData[orderedData.length - 1]

    const trainingStatusColors: Record<string, string> = {
      Productive: 'bg-green-100 text-green-700',
      Maintaining: 'bg-blue-100 text-blue-700',
      Detraining: 'bg-red-100 text-red-700',
      Overreaching: 'bg-orange-100 text-orange-700',
      Recovery: 'bg-teal-100 text-teal-700',
      Unproductive: 'bg-yellow-100 text-yellow-700',
    }

    return {
      trainingStatus: latest.training_status,
      trainingStatusColor: latest.training_status
        ? trainingStatusColors[latest.training_status] || 'bg-gray-100 text-gray-700'
        : null,
      spo2: latest.spo2,
      bodyBatteryMin: latest.body_battery_min,
      bodyBatteryMax: latest.body_battery_max,
    }
  }, [orderedData])

  // Donnees formatees pour le graphique
  const chartData = useMemo(() => {
    if (orderedData.length === 0) return []
    return orderedData.map(entry => ({
      date: entry.date,
      dateFormatted: format(parseISO(entry.date), 'd MMM', { locale: fr }),
      hrv_rmssd: entry.hrv_rmssd,
      training_readiness: entry.training_readiness,
      sleep_score: entry.sleep_score,
      stress_score: entry.stress_score,
      body_battery_max: entry.body_battery_max,
      resting_hr: entry.resting_hr,
    }))
  }, [orderedData])

  // --- Etat non connecte ---
  if (!isConnected) {
    return (
      <div className="bg-white rounded-xl border border-gray-200/60 p-6">
        <div className="flex flex-col items-center justify-center py-12 text-gray-400">
          <Watch className="h-10 w-10 mb-3 text-gray-300" />
          <p className="text-sm font-medium text-gray-500">Connectez Garmin</p>
          <p className="text-xs text-gray-400 mt-1">
            Suivez votre HRV, sommeil, stress et recuperation au quotidien.
          </p>
          <a
            href="/parametres"
            className="mt-4 inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium text-white bg-violet-600 hover:bg-violet-700 transition-colors"
          >
            Connecter dans les Parametres
          </a>
        </div>
      </div>
    )
  }

  // --- Etat loading ---
  if (isLoading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200/60 p-6">
        <div className="flex items-center gap-2 mb-5">
          <div className="p-2.5 rounded-lg bg-violet-100">
            <Watch className="h-5 w-5 text-violet-600" />
          </div>
          <h3 className="text-base font-semibold text-gray-900">Monitoring Garmin Daily</h3>
        </div>
        <div className="flex items-center justify-center py-12 text-gray-400">
          <div className="h-6 w-6 border-2 border-gray-200 border-t-orange-500 rounded-full animate-spin" />
          <span className="ml-3 text-sm">Chargement...</span>
        </div>
      </div>
    )
  }

  // --- Pas de donnees ---
  if (orderedData.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-200/60 p-6">
        <div className="flex items-center gap-2 mb-5">
          <div className="p-2.5 rounded-lg bg-violet-100">
            <Watch className="h-5 w-5 text-violet-600" />
          </div>
          <h3 className="text-base font-semibold text-gray-900">Monitoring Garmin Daily</h3>
        </div>
        <div className="flex flex-col items-center justify-center py-12 text-gray-400">
          <Watch className="h-10 w-10 mb-3 text-gray-300" />
          <p className="text-sm font-medium text-gray-500">Aucune donnee Garmin disponible</p>
          <p className="text-xs text-gray-400 mt-1">Synchronisez vos donnees dans les Parametres</p>
        </div>
      </div>
    )
  }

  // --- Etat connecte avec donnees ---
  return (
    <div className="bg-white rounded-xl border border-gray-200/60 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <div className="p-2.5 rounded-lg bg-violet-100">
            <Watch className="h-5 w-5 text-violet-600" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-gray-900">Monitoring Garmin Daily</h3>
            <p className="text-xs text-gray-400">{orderedData.length} jours de donnees</p>
          </div>
        </div>
      </div>

      {/* Onglets */}
      <div className="flex border-b border-gray-200 mb-6">
        <button
          onClick={() => setActiveTab('monitoring')}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'monitoring'
              ? 'border-violet-600 text-violet-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          <Watch className="inline h-4 w-4 mr-1.5 -mt-0.5" />
          Monitoring
        </button>
        <button
          onClick={() => setActiveTab('sleep')}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'sleep'
              ? 'border-violet-600 text-violet-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          <Moon className="inline h-4 w-4 mr-1.5 -mt-0.5" />
          Sommeil
        </button>
      </div>

      {activeTab === 'monitoring' ? (
        <>
          {/* Mini-cartes recapitulatives */}
          {summaryCards && (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-6">
              {summaryCards.map((card) => {
                const Icon = card.icon
                return (
                  <div key={card.label} className="bg-gray-50 rounded-lg p-4 border border-gray-100">
                    <div className="flex items-center justify-between">
                      <div className={`p-2.5 rounded-lg ${card.bgColor}`}>
                        <Icon className={`h-5 w-5 ${card.color}`} />
                      </div>
                      <TrendArrow current={card.trend.current} previous={card.trend.previous} />
                    </div>
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mt-3">{card.label}</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {card.value}
                      {card.unit && <span className="text-sm font-normal text-gray-400 ml-1">{card.unit}</span>}
                    </p>
                    {card.subtitle && (
                      <p className="text-xs text-gray-400 mt-1">{card.subtitle}</p>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* Badges secondaires */}
          {latestBadges && (
            <div className="flex flex-wrap items-center gap-2 mb-5">
              {latestBadges.trainingStatus && latestBadges.trainingStatusColor && (
                <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${latestBadges.trainingStatusColor}`}>
                  {latestBadges.trainingStatus}
                </span>
              )}
              {latestBadges.spo2 != null && (
                <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-sky-100 text-sky-700">
                  <Droplets className="h-3 w-3" />
                  SpO2 {latestBadges.spo2}%
                </span>
              )}
              {latestBadges.bodyBatteryMax != null && latestBadges.bodyBatteryMin != null && (
                <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">
                  BB {latestBadges.bodyBatteryMin} → {latestBadges.bodyBatteryMax}
                </span>
              )}
            </div>
          )}

          {/* Toggles des metriques — toggle segmente unifie */}
          <div className="inline-flex items-center bg-gray-100 rounded-lg p-1 gap-0.5 mb-5 flex-wrap">
            {METRICS.map((metric) => (
              <button
                key={metric.key}
                onClick={() => toggleMetric(metric.key)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200 ${
                  visibleMetrics.has(metric.key)
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                <span
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ backgroundColor: metric.color }}
                />
                {metric.label}
              </button>
            ))}
          </div>

          {/* Graphique multi-lignes */}
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 0 }}>
                <defs>
                  {METRICS.filter(m => visibleMetrics.has(m.key)).map((metric) => (
                    <linearGradient key={metric.key} id={`gradient-${metric.key}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={metric.color} stopOpacity={0.15} />
                      <stop offset="100%" stopColor={metric.color} stopOpacity={0} />
                    </linearGradient>
                  ))}
                </defs>
                <XAxis
                  dataKey="dateFormatted"
                  tick={{ fontSize: 11, fill: '#9ca3af' }}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={20}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: '#9ca3af' }}
                  tickLine={false}
                  axisLine={false}
                  width={40}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload || payload.length === 0) return null
                    const entry = orderedData.find(d =>
                      format(parseISO(d.date), 'd MMM', { locale: fr }) === label
                    )
                    if (!entry) return null

                    return (
                      <div className="rounded-lg border border-gray-200/60 bg-white p-3 shadow-lg text-sm">
                        <p className="font-semibold text-gray-900 mb-2">
                          {format(parseISO(entry.date), 'd MMMM yyyy', { locale: fr })}
                        </p>
                        <div className="space-y-1">
                          {METRICS.filter(m => visibleMetrics.has(m.key)).map(metric => {
                            const val = entry[metric.key as keyof GarminDailyEntry]
                            if (val === null) return null
                            const unit = metric.key === 'hrv_rmssd' ? ' ms'
                              : metric.key === 'resting_hr' ? ' bpm'
                              : ''
                            return (
                              <div key={metric.key} className="flex justify-between gap-4">
                                <span className="text-gray-500 flex items-center gap-1.5">
                                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: metric.color }} />
                                  {metric.label}
                                </span>
                                <span className="font-medium" style={{ color: metric.color }}>
                                  {typeof val === 'number' ? val.toFixed(0) : val}{unit}
                                </span>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )
                  }}
                />
                {METRICS.filter(m => visibleMetrics.has(m.key)).map((metric) => (
                  <Area
                    key={metric.key}
                    type="monotone"
                    dataKey={metric.key}
                    stroke={metric.color}
                    strokeWidth={2}
                    fill={`url(#gradient-${metric.key})`}
                    connectNulls
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </>
      ) : (
        <GarminSleepTab />
      )}
    </div>
  )
}
