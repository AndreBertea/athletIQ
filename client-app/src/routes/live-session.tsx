import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Activity, Heart, Gauge, Clock, MapPin, Wifi, WifiOff } from 'lucide-react'
import { liveService } from '@/lib/api/live'
import type { LiveSession, LiveTrackpoint, LiveWsMessage } from '@/lib/api/live'
import LiveChart from '@/components/live/LiveChart'
import LiveMap from '@/components/live/LiveMap'
import { AppShell } from '@/components/shared/AppShell'

type ConnState = 'connecting' | 'open' | 'closed' | 'reconnecting'

export default function LiveSessionRoute() {
  return (
    <AppShell>
      <div className="px-4 pt-4 pb-6">
        <LiveSessionContent />
      </div>
    </AppShell>
  )
}

function LiveSessionContent() {
  const { id } = useParams<{ id: string }>()
  const [session, setSession] = useState<LiveSession | null>(null)
  const [points, setPoints] = useState<LiveTrackpoint[]>([])
  const [conn, setConn] = useState<ConnState>('connecting')
  const [ended, setEnded] = useState(false)
  const [now, setNow] = useState(Date.now())

  // Tick pour rafraichir la duree affichee (stop quand session terminee)
  useEffect(() => {
    if (ended) return
    const t = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(t)
  }, [ended])

  useEffect(() => {
    if (!id) return
    setPoints([])
    setSession(null)
    setEnded(false)

    const ctl = liveService.followSession(id, {
      onStatusChange: setConn,
      onMessage: (msg: LiveWsMessage) => {
        if (msg.type === 'snapshot') {
          setSession(msg.session)
          setPoints(msg.points)
          if (msg.session.status !== 'active') setEnded(true)
        } else if (msg.type === 'points') {
          setPoints((prev) => mergePoints(prev, msg.points))
        } else if (msg.type === 'ended') {
          setEnded(true)
        }
      },
    })
    return () => ctl.close()
  }, [id])

  const metrics = useMemo(() => computeMetrics(points, now, ended), [points, now, ended])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Link
            to="/live"
            className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4 mr-1" />
            Sessions
          </Link>
          <h1 className="text-xl font-bold text-foreground">
            {session?.label || 'Session live'}
          </h1>
          {ended && (
            <span className="text-xs px-2 py-1 rounded bg-white/5 text-muted-foreground">
              Terminée
            </span>
          )}
        </div>
        <ConnectionBadge state={conn} />
      </div>

      <MetricsGrid metrics={metrics} />

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="h-[60vh]" style={{ minHeight: 360 }}>
          <LiveMap points={points} />
        </div>
      </div>

      <LiveChart points={points} />

      <SplitsTable splits={metrics.splits} />
    </div>
  )
}

// ---------- UI ----------

function ConnectionBadge({ state }: { state: ConnState }) {
  const map = {
    connecting: { label: 'Connexion...', color: 'bg-yellow-100 text-yellow-700', Icon: Wifi },
    open: { label: 'En direct', color: 'bg-green-100 text-green-700', Icon: Wifi },
    closed: { label: 'Déconnecté', color: 'bg-white/5 text-muted-foreground', Icon: WifiOff },
    reconnecting: { label: 'Reconnexion...', color: 'bg-yellow-100 text-yellow-700', Icon: Wifi },
  } as const
  const { label, color, Icon } = map[state]
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded ${color}`}>
      <Icon className="h-3 w-3" />
      {label}
    </span>
  )
}

function MetricsGrid({ metrics }: { metrics: Metrics }) {
  const items = [
    { label: 'Durée', value: formatDuration(metrics.durationSec), Icon: Clock },
    { label: 'Distance', value: metrics.distanceKm.toFixed(2) + ' km', Icon: MapPin },
    { label: 'Allure', value: metrics.paceMinPerKm ? formatPace(metrics.paceMinPerKm) : '—', Icon: Activity },
    { label: 'Vitesse', value: metrics.speedKmh != null ? metrics.speedKmh.toFixed(1) + ' km/h' : '—', Icon: Gauge },
    { label: 'FC', value: metrics.hr != null ? `${metrics.hr} bpm` : '—', Icon: Heart },
  ]
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      {items.map(({ label, value, Icon }) => (
        <div key={label} className="glass rounded-lg p-4">
          <div className="flex items-center gap-2 text-xs text-muted-foreground uppercase tracking-wide">
            <Icon className="h-3.5 w-3.5" />
            {label}
          </div>
          <div className="mt-1 text-2xl font-semibold text-foreground tabular-nums">{value}</div>
        </div>
      ))}
    </div>
  )
}

function SplitsTable({ splits }: { splits: Split[] }) {
  if (splits.length === 0) return null
  return (
    <div className="glass rounded-lg">
      <div className="px-4 py-3 border-b border-[var(--border-subtle)]">
        <h2 className="text-sm font-semibold text-foreground">Splits</h2>
      </div>
      <ul className="divide-y divide-gray-100">
        {splits.map((s) => (
          <li key={s.km} className="px-4 py-2 flex items-center justify-between text-sm tabular-nums">
            <span className="text-foreground">km {s.km}</span>
            <span className="font-medium text-foreground">{formatPace(s.paceMinPerKm)}</span>
            {s.avgHr != null && <span className="text-muted-foreground">{s.avgHr} bpm</span>}
          </li>
        ))}
      </ul>
    </div>
  )
}

// ---------- Calculs ----------

interface Split {
  km: number
  paceMinPerKm: number
  avgHr: number | null
  crossTs: number
}

interface Metrics {
  durationSec: number
  distanceKm: number
  speedKmh: number | null
  paceMinPerKm: number | null
  hr: number | null
  splits: Split[]
}

function computeMetrics(points: LiveTrackpoint[], nowMs: number, ended: boolean): Metrics {
  if (points.length === 0) {
    return { durationSec: 0, distanceKm: 0, speedKmh: null, paceMinPerKm: null, hr: null, splits: [] }
  }
  const first = points[0]
  const last = points[points.length - 1]
  const startMs = first.ts * 1000
  const lastMs = last.ts * 1000
  // Duree :
  //  - session active  : entre premier point et "maintenant"
  //  - session ended   : entre premier et dernier point (figee)
  const endTs = ended ? lastMs : Math.max(nowMs, lastMs)
  const elapsed = Math.max(0, Math.floor((endTs - startMs) / 1000))

  // Distance : on prefere la valeur Garmin si dispo, sinon fallback calcul GPS
  // (Garmin renvoie souvent "$undefined" en session active -> distance = null)
  let distanceM = last.distance ?? null
  if (distanceM == null) {
    distanceM = computeGpsDistance(points)
  }
  const distanceKm = distanceM / 1000

  // Vitesse instantanee = moyenne mobile sur les 10 derniers points
  const window = points.slice(-10)
  const speedsMs = window.map((p) => p.speed).filter((s): s is number => typeof s === 'number')
  const avgSpeedMs = speedsMs.length > 0 ? speedsMs.reduce((a, b) => a + b, 0) / speedsMs.length : null
  const speedKmh = avgSpeedMs != null ? avgSpeedMs * 3.6 : null
  const paceMinPerKm = avgSpeedMs && avgSpeedMs > 0 ? 1000 / avgSpeedMs / 60 : null

  // FC instantanee = dernier ts avec hr non-null DANS LES 30 DERNIERES SECONDES
  // (sinon on affiche "—" plutot que de garder une valeur perimee de plusieurs minutes)
  let hr: number | null = null
  const hrFreshnessLimitTs = last.ts - 30
  for (let i = points.length - 1; i >= 0; i--) {
    if (points[i].ts < hrFreshnessLimitTs) break
    if (points[i].hr != null) { hr = points[i].hr; break }
  }

  // Splits par km : pour chaque franchissement de multiple de 1000m
  const splits: Split[] = []
  let nextKm = 1
  let prevTs: number | null = null
  let prevDistance = 0
  const hrSamples: number[] = []
  for (const p of points) {
    if (p.distance == null) continue
    if (p.hr != null) hrSamples.push(p.hr)
    if (prevTs === null) prevTs = p.ts
    while (p.distance >= nextKm * 1000) {
      const targetDist = nextKm * 1000
      // interp lineaire du ts au moment du franchissement
      const ratio =
        prevDistance < targetDist && p.distance > prevDistance
          ? (targetDist - prevDistance) / (p.distance - prevDistance)
          : 0
      const crossTs = prevTs + ratio * (p.ts - prevTs)
      const durSec = crossTs - (splits.length === 0 ? first.ts : splits[splits.length - 1].crossTs)
      const paceMin = durSec > 0 ? durSec / 60 : 0
      const avgHr = hrSamples.length > 0 ? Math.round(hrSamples.reduce((a, b) => a + b, 0) / hrSamples.length) : null
      splits.push({ km: nextKm, paceMinPerKm: paceMin, avgHr, crossTs })
      nextKm += 1
      hrSamples.length = 0
    }
    prevTs = p.ts
    prevDistance = p.distance
  }

  return { durationSec: elapsed, distanceKm, speedKmh, paceMinPerKm, hr, splits }
}

function mergePoints(prev: LiveTrackpoint[], incoming: LiveTrackpoint[]): LiveTrackpoint[] {
  if (incoming.length === 0) return prev
  const lastTs = prev.length > 0 ? prev[prev.length - 1].ts : -1
  const fresh = incoming.filter((p) => p.ts > lastTs).sort((a, b) => a.ts - b.ts)
  return fresh.length > 0 ? [...prev, ...fresh] : prev
}

function computeGpsDistance(points: LiveTrackpoint[]): number {
  // Somme des distances haversine entre points consecutifs.
  // Filtre les sauts GPS aberrants (> 100m en 1 sample = ~360 km/h -> bruit).
  let total = 0
  let prev: LiveTrackpoint | null = null
  for (const p of points) {
    if (p.lat == null || p.lng == null) { prev = p; continue }
    if (prev && prev.lat != null && prev.lng != null) {
      const d = haversine(prev.lat, prev.lng, p.lat, p.lng)
      if (d < 100) total += d  // skip outliers
    }
    prev = p
  }
  return total
}

function haversine(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371000  // metres
  const toRad = (deg: number) => (deg * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLng = toRad(lng2 - lng1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

function formatDuration(sec: number): string {
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

function formatPace(minPerKm: number): string {
  if (!isFinite(minPerKm) || minPerKm <= 0) return '—'
  const min = Math.floor(minPerKm)
  const sec = Math.round((minPerKm - min) * 60)
  return `${min}'${String(sec).padStart(2, '0')}"/km`
}
