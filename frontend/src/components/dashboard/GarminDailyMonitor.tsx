import { useState, useMemo } from 'react'
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
} from 'recharts'
import { Watch, TrendingUp, TrendingDown, Minus, Heart, Brain, Moon, Activity } from 'lucide-react'
import { format, parseISO } from 'date-fns'
import { fr } from 'date-fns/locale'
import type { GarminDailyEntry } from '../../services/garminService'

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
]

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
  if (Math.abs(diff) < 0.5) return <Minus className="h-4 w-4 text-gray-400" />
  if (diff > 0) return <TrendingUp className="h-4 w-4 text-green-500" />
  return <TrendingDown className="h-4 w-4 text-red-500" />
}

export default function GarminDailyMonitor({ data, isLoading, isConnected }: GarminDailyMonitorProps) {
  const [visibleMetrics, setVisibleMetrics] = useState<Set<string>>(
    new Set(METRICS.map(m => m.key))
  )

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

  // Mini-cartes récapitulatives
  const summaryCards = useMemo(() => {
    if (!data || data.length === 0) return null

    const hrvAvg = avg7d(data, 'hrv_rmssd')
    const hrvPrev = avg7dPrev(data, 'hrv_rmssd')
    const readinessAvg = avg7d(data, 'training_readiness')
    const sleepAvg = avg7d(data, 'sleep_score')
    const latestRhr = data[data.length - 1]?.resting_hr
    const rhrAvg = avg7d(data, 'resting_hr')

    return [
      {
        label: 'HRV moy. 7j',
        value: hrvAvg !== null ? hrvAvg.toFixed(0) : '—',
        unit: 'ms',
        icon: Heart,
        color: 'text-purple-600',
        bgColor: 'bg-purple-100',
        trend: { current: hrvAvg, previous: hrvPrev },
      },
      {
        label: 'Readiness moy. 7j',
        value: readinessAvg !== null ? readinessAvg.toFixed(0) : '—',
        unit: '',
        icon: Brain,
        color: 'text-amber-600',
        bgColor: 'bg-amber-100',
        trend: null,
      },
      {
        label: 'Sleep Score moy. 7j',
        value: sleepAvg !== null ? sleepAvg.toFixed(0) : '—',
        unit: '',
        icon: Moon,
        color: 'text-blue-600',
        bgColor: 'bg-blue-100',
        trend: null,
      },
      {
        label: 'Resting HR',
        value: latestRhr !== null && latestRhr !== undefined ? `${latestRhr}` : '—',
        unit: 'bpm',
        icon: Activity,
        color: 'text-red-600',
        bgColor: 'bg-red-100',
        subtitle: rhrAvg !== null ? `Moy. 7j : ${rhrAvg.toFixed(0)} bpm` : undefined,
        trend: null,
      },
    ]
  }, [data])

  // Données formatées pour le graphique
  const chartData = useMemo(() => {
    if (!data || data.length === 0) return []
    return data.map(entry => ({
      date: entry.date,
      dateFormatted: format(parseISO(entry.date), 'd MMM', { locale: fr }),
      hrv_rmssd: entry.hrv_rmssd,
      training_readiness: entry.training_readiness,
      sleep_score: entry.sleep_score,
      stress_score: entry.stress_score,
      body_battery_max: entry.body_battery_max,
    }))
  }, [data])

  // --- État non connecté ---
  if (!isConnected) {
    return (
      <div className="card">
        <div className="text-center py-10">
          <Watch className="h-12 w-12 mx-auto mb-3 text-gray-300" />
          <h3 className="text-lg font-medium text-gray-700 mb-1">Connectez Garmin</h3>
          <p className="text-sm text-gray-500 mb-4">
            Suivez votre HRV, sommeil, stress et récupération au quotidien.
          </p>
          <a
            href="/parametres"
            className="inline-flex items-center px-4 py-2 rounded-md text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 transition-colors"
          >
            Connecter dans les Paramètres
          </a>
        </div>
      </div>
    )
  }

  // --- État loading ---
  if (isLoading) {
    return (
      <div className="card">
        <div className="flex items-center space-x-2 mb-4">
          <Watch className="h-5 w-5 text-gray-400" />
          <h3 className="text-lg font-medium text-gray-900">Monitoring Garmin Daily</h3>
        </div>
        <div className="h-64 flex items-center justify-center text-gray-500">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500 mr-3" />
          Chargement des données Garmin...
        </div>
      </div>
    )
  }

  // --- Pas de données ---
  if (!data || data.length === 0) {
    return (
      <div className="card">
        <div className="flex items-center space-x-2 mb-4">
          <Watch className="h-5 w-5 text-gray-400" />
          <h3 className="text-lg font-medium text-gray-900">Monitoring Garmin Daily</h3>
        </div>
        <div className="h-64 flex items-center justify-center text-gray-500 bg-gray-50 rounded-lg">
          <div className="text-center">
            <Watch className="h-10 w-10 mx-auto mb-2 text-gray-300" />
            <p>Aucune donnée Garmin disponible</p>
            <p className="text-sm text-gray-400 mt-1">
              Synchronisez vos données dans les Paramètres
            </p>
          </div>
        </div>
      </div>
    )
  }

  // --- État connecté avec données ---
  return (
    <div className="card">
      <div className="flex items-center space-x-2 mb-6">
        <Watch className="h-5 w-5 text-purple-600" />
        <h3 className="text-lg font-medium text-gray-900">Monitoring Garmin Daily</h3>
        <span className="text-xs text-gray-400">{data.length} jours</span>
      </div>

      {/* Mini-cartes récapitulatives */}
      {summaryCards && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          {summaryCards.map((card) => {
            const Icon = card.icon
            return (
              <div key={card.label} className="bg-white p-4 rounded-lg border">
                <div className="flex items-center justify-between">
                  <div className={`p-2 rounded-lg ${card.bgColor}`}>
                    <Icon className={`h-4 w-4 ${card.color}`} />
                  </div>
                  {card.trend && (
                    <TrendArrow current={card.trend.current} previous={card.trend.previous} />
                  )}
                </div>
                <p className="text-sm font-medium text-gray-500 mt-3">{card.label}</p>
                <p className="text-2xl font-semibold text-gray-900">
                  {card.value}
                  {card.unit && <span className="text-sm font-normal text-gray-500 ml-1">{card.unit}</span>}
                </p>
                {card.subtitle && (
                  <p className="text-xs text-gray-400 mt-1">{card.subtitle}</p>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Toggles des métriques */}
      <div className="flex flex-wrap gap-2 mb-4">
        {METRICS.map((metric) => (
          <button
            key={metric.key}
            onClick={() => toggleMetric(metric.key)}
            className={`px-3 py-1.5 text-xs rounded-full border transition-colors ${
              visibleMetrics.has(metric.key)
                ? 'border-transparent text-white'
                : 'border-gray-300 text-gray-500 bg-white hover:bg-gray-50'
            }`}
            style={visibleMetrics.has(metric.key) ? { backgroundColor: metric.color } : undefined}
          >
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
                  <stop offset="0%" stopColor={metric.color} stopOpacity={0.2} />
                  <stop offset="100%" stopColor={metric.color} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>
            <XAxis
              dataKey="dateFormatted"
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              minTickGap={20}
            />
            <YAxis
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              width={40}
            />
            <Tooltip
              content={({ active, payload, label }) => {
                if (!active || !payload || payload.length === 0) return null
                // Trouver l'entrée originale pour afficher toutes les valeurs
                const entry = data.find(d =>
                  format(parseISO(d.date), 'd MMM', { locale: fr }) === label
                )
                if (!entry) return null

                return (
                  <div className="rounded-lg border bg-white p-3 shadow-md text-sm">
                    <p className="font-semibold text-gray-900 mb-2">
                      {format(parseISO(entry.date), 'd MMMM yyyy', { locale: fr })}
                    </p>
                    <div className="space-y-1">
                      {entry.hrv_rmssd !== null && (
                        <div className="flex justify-between gap-4">
                          <span className="text-gray-500">HRV</span>
                          <span className="font-medium" style={{ color: '#8b5cf6' }}>{entry.hrv_rmssd.toFixed(0)} ms</span>
                        </div>
                      )}
                      {entry.training_readiness !== null && (
                        <div className="flex justify-between gap-4">
                          <span className="text-gray-500">Readiness</span>
                          <span className="font-medium" style={{ color: '#f59e0b' }}>{entry.training_readiness}</span>
                        </div>
                      )}
                      {entry.sleep_score !== null && (
                        <div className="flex justify-between gap-4">
                          <span className="text-gray-500">Sommeil</span>
                          <span className="font-medium" style={{ color: '#3b82f6' }}>{entry.sleep_score}</span>
                        </div>
                      )}
                      {entry.stress_score !== null && (
                        <div className="flex justify-between gap-4">
                          <span className="text-gray-500">Stress</span>
                          <span className="font-medium" style={{ color: '#ef4444' }}>{entry.stress_score}</span>
                        </div>
                      )}
                      {entry.body_battery_max !== null && (
                        <div className="flex justify-between gap-4">
                          <span className="text-gray-500">Body Battery</span>
                          <span className="font-medium" style={{ color: '#10b981' }}>{entry.body_battery_max}</span>
                        </div>
                      )}
                      {entry.resting_hr !== null && (
                        <div className="flex justify-between gap-4">
                          <span className="text-gray-500">Resting HR</span>
                          <span className="font-medium text-gray-700">{entry.resting_hr} bpm</span>
                        </div>
                      )}
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
    </div>
  )
}
