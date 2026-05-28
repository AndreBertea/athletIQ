import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Wifi, WifiOff } from 'lucide-react';
import LiveMap from '@/components/live/LiveMap';
import { AppShell } from '@/components/shared/AppShell';
import MiniAreaChart from '@/components/shared/MiniAreaChart';
import { liveService } from '@/lib/api/live';
import type { LiveSession, LiveTrackpoint, LiveWsMessage } from '@/lib/api/live';
import { cn } from '@/lib/utils';

type ConnState = 'connecting' | 'open' | 'closed' | 'reconnecting';

export default function LiveSessionRoute() {
  const { id } = useParams<{ id: string }>();

  return (
    <AppShell hideTopBar hideBottomNav disableMainPadding mainClassName="overflow-hidden">
      <LiveSessionContent key={id ?? 'missing-session'} sessionId={id ?? ''} />
    </AppShell>
  );
}

function LiveSessionContent({ sessionId }: { sessionId: string }) {
  const [session, setSession] = useState<LiveSession | null>(null);
  const [points, setPoints] = useState<LiveTrackpoint[]>([]);
  const [conn, setConn] = useState<ConnState>('connecting');
  const [ended, setEnded] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (ended) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [ended]);

  useEffect(() => {
    if (!sessionId) return;

    const controller = liveService.followSession(sessionId, {
      onStatusChange: setConn,
      onMessage: (msg: LiveWsMessage) => {
        if (msg.type === 'snapshot') {
          setSession(msg.session);
          setPoints(msg.points);
          if (msg.session.status !== 'active') setEnded(true);
        } else if (msg.type === 'points') {
          setPoints((prev) => mergePoints(prev, msg.points));
        } else if (msg.type === 'ended') {
          setEnded(true);
        }
      },
    });
    return () => controller.close();
  }, [sessionId]);

  const metrics = useMemo(() => computeMetrics(points, now, ended), [points, now, ended]);
  const hrSeries = useMemo(
    () => points.slice(-42).map((point) => point.hr ?? null),
    [points],
  );
  const status = ended || (session != null && session.status !== 'active') ? 'closed' : conn;

  return (
    <div className="relative h-full overflow-hidden bg-[#0f100c]">
      <LiveMap points={points} />
      <div className="pointer-events-none absolute inset-0 z-[2] bg-gradient-to-b from-[#0a0c08]/50 via-[#0a0c08]/5 to-[#0a0c08]/70" />

      <Link
        to="/live"
        className="absolute left-4 top-[max(14px,env(safe-area-inset-top))] z-[8] inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-[#0f100c]/55 px-3 py-2 text-[13px] font-medium text-[#e8dfcf] shadow-lg backdrop-blur-xl"
      >
        <ArrowLeft className="h-4 w-4" />
        Retour
      </Link>

      <ConnectionBadge state={status} />

      <div className="absolute left-6 top-[calc(max(14px,env(safe-area-inset-top))+50px)] z-[5] max-w-[270px]">
        <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.09em] text-[#e8dfcf]/60">
          Session live
        </p>
        <h1 className="font-display text-[22px] font-bold leading-tight tracking-tight text-[#f0e8d8]">
          {session?.label || 'Session live'}
        </h1>
      </div>

      <section
        onClick={() => {
          if (!expanded) setExpanded(true);
        }}
        className={cn(
          'absolute inset-x-0 bottom-0 z-10 flex flex-col overflow-hidden rounded-t-[28px] bg-[#0d100b]/[0.97] shadow-[0_-16px_48px_rgba(0,0,0,0.55)] transition-[height] duration-[380ms] ease-[cubic-bezier(0.34,1.4,0.64,1)]',
          expanded ? 'h-[80%]' : 'h-[34%]',
        )}
      >
        <div className="flex shrink-0 justify-center pb-1 pt-3">
          <span className="h-1 w-9 rounded-full bg-[#e8dfcf]/20" />
        </div>

        <div className="grid shrink-0 grid-cols-[1fr_1px_1fr] px-7 pb-2.5 pt-3.5">
          <HeroMetric label="Durée" value={formatDuration(metrics.durationSec)} />
          <div className="bg-[#e8dfcf]/10" />
          <HeroMetric label="Distance" value={`${metrics.distanceKm.toFixed(2)} km`} align="right" />
        </div>

        <div className="shrink-0 px-5 pb-2">
          <div className="mb-1.5 flex items-center justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-[0.07em] text-[#e8dfcf]/45">
              FC en temps réel
            </p>
            {metrics.hr != null ? (
              <span className="font-display text-sm font-bold text-danger-fg">
                {metrics.hr} bpm
              </span>
            ) : null}
          </div>
          <MiniAreaChart
            data={hrSeries}
            color="#FCA5A5"
            height={56}
            className="bg-white/[0.03]"
          />
        </div>

        {expanded ? (
          <div
            className="flex-1 overflow-y-auto px-6 pb-[calc(24px+env(safe-area-inset-bottom))] pt-2"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => setExpanded(false)}
              className="mb-3 ml-auto block rounded-full bg-[#e8dfcf]/[0.07] px-3 py-1.5 text-[11px] font-medium text-[#e8dfcf]/55"
            >
              Réduire ↓
            </button>

            <div className="grid grid-cols-3 gap-2">
              <SheetMetric label="Allure" value={metrics.paceMinPerKm ? formatPace(metrics.paceMinPerKm) : '—'} />
              <SheetMetric label="Vitesse" value={metrics.speedKmh != null ? `${metrics.speedKmh.toFixed(1)} km/h` : '—'} />
              <SheetMetric label="FC" value={metrics.hr != null ? `${metrics.hr} bpm` : '—'} />
            </div>

            {metrics.splits.length > 0 ? (
              <div className="mt-4">
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.07em] text-[#e8dfcf]/45">
                  Splits
                </p>
                <div className="flex flex-col gap-1">
                  {metrics.splits.map((split) => (
                    <div
                      key={split.km}
                      className="grid grid-cols-[1fr_auto_auto] items-center gap-3 rounded-md bg-[#e8dfcf]/[0.04] px-3 py-2 text-[13px]"
                    >
                      <span className="text-[#e8dfcf]/70">km {split.km}</span>
                      <span className="font-semibold tabular-nums text-[#f0e8d8]">
                        {formatPace(split.paceMinPerKm)}
                      </span>
                      {split.avgHr != null ? (
                        <span className="text-xs tabular-nums text-danger-fg">
                          {split.avgHr} bpm
                        </span>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="mt-4 rounded-[10px] border border-white/[0.07] bg-white/[0.04] px-3 py-4 text-center text-xs text-[#e8dfcf]/55">
                Les splits apparaîtront après le premier kilomètre.
              </div>
            )}
          </div>
        ) : null}
      </section>
    </div>
  );
}

function ConnectionBadge({ state }: { state: ConnState }) {
  const active = state === 'open';
  const reconnecting = state === 'connecting' || state === 'reconnecting';
  const Icon = active || reconnecting ? Wifi : WifiOff;
  const label = active ? 'En direct' : reconnecting ? 'Connexion...' : 'Terminée';

  return (
    <div
      className={cn(
        'absolute right-4 top-[max(14px,env(safe-area-inset-top))] z-[8] inline-flex items-center gap-1.5 rounded-full border px-3 py-2 text-xs font-semibold backdrop-blur-xl',
        active
          ? 'border-success/35 bg-success/20 text-success-soft'
          : 'border-white/10 bg-[#191815]/60 text-[#a8a192]/70',
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      <span>{label}</span>
      {active ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-success-soft" /> : null}
    </div>
  );
}

function HeroMetric({
  label,
  value,
  align = 'left',
}: {
  label: string;
  value: string;
  align?: 'left' | 'right';
}) {
  return (
    <div className={cn('min-w-0', align === 'right' && 'text-right')}>
      <span className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.07em] text-[#e8dfcf]/50">
        {label}
      </span>
      <strong className="font-display block truncate text-[30px] font-medium leading-none tracking-tight text-[#f0e8d8]">
        {value}
      </strong>
    </div>
  );
}

function SheetMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/[0.08] bg-[#e8dfcf]/[0.06] px-2 py-2.5 text-center">
      <p className="mb-1.5 text-[9px] font-semibold uppercase tracking-[0.05em] text-[#e8dfcf]/45">
        {label}
      </p>
      <p className="font-display text-[15px] font-bold leading-none text-[#f0e8d8]">
        {value}
      </p>
    </div>
  );
}

interface Split {
  km: number;
  paceMinPerKm: number;
  avgHr: number | null;
  crossTs: number;
}

interface Metrics {
  durationSec: number;
  distanceKm: number;
  speedKmh: number | null;
  paceMinPerKm: number | null;
  hr: number | null;
  splits: Split[];
}

function computeMetrics(points: LiveTrackpoint[], nowMs: number, ended: boolean): Metrics {
  if (points.length === 0) return emptyMetrics();

  const first = points[0];
  const last = points[points.length - 1];
  if (!first || !last) return emptyMetrics();

  const startMs = first.ts * 1000;
  const lastMs = last.ts * 1000;
  const endTs = ended ? lastMs : Math.max(nowMs, lastMs);
  const elapsed = Math.max(0, Math.floor((endTs - startMs) / 1000));

  let distanceM = last.distance ?? null;
  if (distanceM == null) distanceM = computeGpsDistance(points);
  const distanceKm = distanceM / 1000;

  const windowPoints = points.slice(-10);
  const speedsMs = windowPoints
    .map((point) => point.speed)
    .filter((speed): speed is number => typeof speed === 'number');
  const avgSpeedMs =
    speedsMs.length > 0 ? speedsMs.reduce((sum, speed) => sum + speed, 0) / speedsMs.length : null;
  const speedKmh = avgSpeedMs != null ? avgSpeedMs * 3.6 : null;
  const paceMinPerKm = avgSpeedMs != null && avgSpeedMs > 0.3 ? 1000 / avgSpeedMs / 60 : null;

  let hr: number | null = null;
  const hrFreshnessLimitTs = last.ts - 30;
  for (let index = points.length - 1; index >= 0; index -= 1) {
    const point = points[index];
    if (!point || point.ts < hrFreshnessLimitTs) break;
    if (point.hr != null) {
      hr = point.hr;
      break;
    }
  }

  return { durationSec: elapsed, distanceKm, speedKmh, paceMinPerKm, hr, splits: computeSplits(points, first) };
}

function computeSplits(points: LiveTrackpoint[], first: LiveTrackpoint): Split[] {
  const splits: Split[] = [];
  let nextKm = 1;
  let prevTs: number | null = null;
  let prevDistance = 0;
  const hrSamples: number[] = [];

  for (const point of points) {
    if (point.distance == null) continue;
    if (point.hr != null) hrSamples.push(point.hr);
    if (prevTs === null) prevTs = point.ts;

    while (point.distance >= nextKm * 1000) {
      const targetDist = nextKm * 1000;
      const ratio =
        prevDistance < targetDist && point.distance > prevDistance
          ? (targetDist - prevDistance) / (point.distance - prevDistance)
          : 0;
      const crossTs = prevTs + ratio * (point.ts - prevTs);
      const previousCrossTs = splits[splits.length - 1]?.crossTs ?? first.ts;
      const durSec = crossTs - previousCrossTs;
      const paceMin = durSec > 0 ? durSec / 60 : 0;
      const avgHr =
        hrSamples.length > 0
          ? Math.round(hrSamples.reduce((sum, sample) => sum + sample, 0) / hrSamples.length)
          : null;
      splits.push({ km: nextKm, paceMinPerKm: paceMin, avgHr, crossTs });
      nextKm += 1;
      hrSamples.length = 0;
    }

    prevTs = point.ts;
    prevDistance = point.distance;
  }

  return splits;
}

function mergePoints(prev: LiveTrackpoint[], incoming: LiveTrackpoint[]): LiveTrackpoint[] {
  if (incoming.length === 0) return prev;
  const lastTs = prev[prev.length - 1]?.ts ?? -1;
  const fresh = incoming.filter((point) => point.ts > lastTs).sort((a, b) => a.ts - b.ts);
  return fresh.length > 0 ? [...prev, ...fresh] : prev;
}

function computeGpsDistance(points: LiveTrackpoint[]): number {
  let total = 0;
  let prev: LiveTrackpoint | null = null;
  for (const point of points) {
    if (point.lat == null || point.lng == null) {
      prev = point;
      continue;
    }
    if (prev?.lat != null && prev.lng != null) {
      const distance = haversine(prev.lat, prev.lng, point.lat, point.lng);
      if (distance < 100) total += distance;
    }
    prev = point;
  }
  return total;
}

function emptyMetrics(): Metrics {
  return {
    durationSec: 0,
    distanceKm: 0,
    speedKmh: null,
    paceMinPerKm: null,
    hr: null,
    splits: [],
  };
}

function haversine(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const radius = 6371000;
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * radius * Math.asin(Math.sqrt(a));
}

function formatDuration(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function formatPace(minPerKm: number): string {
  if (!Number.isFinite(minPerKm) || minPerKm <= 0) return '—';
  const totalSec = Math.round(minPerKm * 60);
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min}'${String(sec).padStart(2, '0')}"/km`;
}
