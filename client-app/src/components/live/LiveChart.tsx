import { useMemo, useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Clock, MapPin } from 'lucide-react'
import type { LiveTrackpoint } from '@/lib/api/live'

type AxisMode = 'time' | 'distance'

interface Props {
  points: LiveTrackpoint[]
}

interface ChartPoint {
  /** Position sur l'axe X : secondes depuis le debut OU metres cumules */
  x: number
  hr: number | null
  /** Allure en min/km, null si vitesse nulle ou inconnue */
  pace: number | null
  /** Distance cumulee en metres (toujours dispo, calcul haversine fallback) */
  distM: number
}

export default function LiveChart({ points }: Props) {
  const [mode, setMode] = useState<AxisMode>('time')

  const data = useMemo(() => buildChartData(points), [points])

  if (data.length === 0) {
    return null
  }

  const xKey: keyof ChartPoint = mode === 'time' ? 'x' : 'distM'
  const xFormatter = mode === 'time' ? formatSeconds : formatKilometers
  const xLabel = mode === 'time' ? 'Temps' : 'Distance'

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <h2 className="text-sm font-semibold text-gray-900">
          FC &amp; Allure
        </h2>
        <div className="inline-flex rounded-md border border-gray-200 overflow-hidden text-xs">
          <button
            type="button"
            onClick={() => setMode('time')}
            className={`inline-flex items-center gap-1 px-3 py-1 ${
              mode === 'time'
                ? 'bg-primary-600 text-white'
                : 'text-gray-600 hover:bg-gray-50'
            }`}
          >
            <Clock className="h-3.5 w-3.5" />
            Temps
          </button>
          <button
            type="button"
            onClick={() => setMode('distance')}
            className={`inline-flex items-center gap-1 px-3 py-1 border-l border-gray-200 ${
              mode === 'distance'
                ? 'bg-primary-600 text-white'
                : 'text-gray-600 hover:bg-gray-50'
            }`}
          >
            <MapPin className="h-3.5 w-3.5" />
            Distance
          </button>
        </div>
      </div>

      <div className="h-72 w-full px-2 py-3">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 10, right: 16, bottom: 18, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey={xKey as string}
              type="number"
              domain={['dataMin', 'dataMax']}
              tickFormatter={xFormatter}
              tick={{ fontSize: 11, fill: '#6b7280' }}
              label={{
                value: xLabel,
                position: 'insideBottom',
                offset: -8,
                fill: '#6b7280',
                fontSize: 11,
              }}
            />
            <YAxis
              yAxisId="hr"
              orientation="left"
              domain={['dataMin - 5', 'dataMax + 5']}
              tick={{ fontSize: 11, fill: '#dc2626' }}
              tickFormatter={(v) => `${Math.round(v)}`}
              label={{
                value: 'FC (bpm)',
                angle: -90,
                position: 'insideLeft',
                fill: '#dc2626',
                fontSize: 11,
              }}
            />
            <YAxis
              yAxisId="pace"
              orientation="right"
              reversed
              domain={['dataMin - 0.2', 'dataMax + 0.2']}
              tick={{ fontSize: 11, fill: '#2563eb' }}
              tickFormatter={formatPaceShort}
              label={{
                value: 'Allure (min/km)',
                angle: 90,
                position: 'insideRight',
                fill: '#2563eb',
                fontSize: 11,
              }}
            />
            <Tooltip
              labelFormatter={(label) => `${xLabel} : ${xFormatter(label as number)}`}
              formatter={(value, name) => {
                if (value == null) return ['—', name as string]
                if (name === 'FC') return [`${Math.round(value as number)} bpm`, name]
                if (name === 'Allure') return [formatPaceShort(value as number) + '/km', name]
                return [String(value), name as string]
              }}
              contentStyle={{ fontSize: 12, borderRadius: 8 }}
            />
            <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
            <Line
              yAxisId="hr"
              type="monotone"
              dataKey="hr"
              name="FC"
              stroke="#dc2626"
              strokeWidth={2}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              yAxisId="pace"
              type="monotone"
              dataKey="pace"
              name="Allure"
              stroke="#2563eb"
              strokeWidth={2}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

// ---------- Helpers ----------

function buildChartData(points: LiveTrackpoint[]): ChartPoint[] {
  if (points.length === 0) return []
  const first = points[0]
  if (!first) return []
  const startTs = first.ts
  const result: ChartPoint[] = []
  let cumulativeDist = 0
  let prev: LiveTrackpoint | null = null

  for (const p of points) {
    if (prev && p.lat != null && p.lng != null && prev.lat != null && prev.lng != null) {
      const d = haversine(prev.lat, prev.lng, p.lat, p.lng)
      if (d < 100) cumulativeDist += d  // skip outliers GPS
    }
    // Prefere la distance Garmin si presente
    const distM = p.distance != null ? p.distance : cumulativeDist

    const pace =
      p.speed != null && p.speed > 0.3  // > ~1 km/h sinon allure pas significative
        ? 1000 / p.speed / 60
        : null

    result.push({
      x: p.ts - startTs,
      hr: p.hr,
      pace: pace != null && pace < 30 ? pace : null,  // cap a 30 min/km
      distM,
    })
    prev = p
  }
  return result
}

function haversine(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371000
  const toRad = (deg: number) => (deg * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLng = toRad(lng2 - lng1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

function formatSeconds(sec: number): string {
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = Math.floor(sec % 60)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

function formatKilometers(m: number): string {
  const km = m / 1000
  return km < 10 ? km.toFixed(2) + ' km' : km.toFixed(1) + ' km'
}

function formatPaceShort(minPerKm: number): string {
  if (!isFinite(minPerKm) || minPerKm <= 0) return '—'
  const min = Math.floor(minPerKm)
  const sec = Math.round((minPerKm - min) * 60)
  return `${min}'${String(sec).padStart(2, '0')}"`
}
