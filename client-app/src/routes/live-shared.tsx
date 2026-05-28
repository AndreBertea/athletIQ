import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  Activity as ActivityIcon,
  Heart,
  Gauge,
  Clock,
  MapPin,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { liveService } from '@/lib/api/live';
import type {
  LiveSession,
  LiveSessionStatus,
  LiveTrackpoint,
  LiveWsMessage,
} from '@/lib/api/live';
import LiveSharedMap from '@/components/live/LiveSharedMap';
import type { AthleteTrack } from '@/components/live/LiveSharedMap';
import LiveChart from '@/components/live/LiveChart';
import Avatar, { trackColorForIndex } from '@/components/shared/Avatar';
import { AppShell } from '@/components/shared/AppShell';
import {
  LIVE_MULTI_SELECTION_EVENT,
  readLiveMultiSessionIds,
} from '@/lib/live-multi-selection';

interface AthleteState {
  sessionId: string;
  athleteId: string;
  fullName: string;
  email: string;
  color: string;
  status: LiveSessionStatus;
  points: LiveTrackpoint[];
  connected: boolean;
}

interface MultiSessionEntry {
  session: LiveSession;
  fullName: string;
  email: string;
}

export default function SharedLiveRoute() {
  return (
    <AppShell>
      <div className="px-4 pb-6 pt-4">
        <SharedLiveContent />
      </div>
    </AppShell>
  );
}

function SharedLiveContent() {
  const [selectedSessionIds, setSelectedSessionIds] = useState(readLiveMultiSessionIds);

  useEffect(() => {
    const syncSelection = () => setSelectedSessionIds(readLiveMultiSessionIds());
    window.addEventListener('storage', syncSelection);
    window.addEventListener(LIVE_MULTI_SELECTION_EVENT, syncSelection);
    return () => {
      window.removeEventListener('storage', syncSelection);
      window.removeEventListener(LIVE_MULTI_SELECTION_EVENT, syncSelection);
    };
  }, []);

  const sessionsQuery = useQuery({
    queryKey: ['live', 'multi-selected-sessions'],
    queryFn: () => liveService.listSessions(),
    refetchInterval: 10_000,
    enabled: selectedSessionIds.length > 0,
  });

  const selectedEntries = useMemo<MultiSessionEntry[]>(() => {
    const sessions = sessionsQuery.data ?? [];
    return selectedSessionIds
      .map((id) => sessions.find((session) => session.id === id))
      .filter((session): session is LiveSession => Boolean(session))
      .map((session) => ({
        session,
        fullName: session.label || `Session du ${formatSessionDate(session.created_at)}`,
        email: session.source === 'livetrack' ? 'Garmin LiveTrack' : 'Connect IQ',
      }));
  }, [selectedSessionIds, sessionsQuery.data]);

  const [states, setStates] = useState<Record<string, AthleteState>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  // Tick uniquement quand au moins une session est encore active
  const hasActive = useMemo(
    () => Object.values(states).some((s) => s.status === 'active'),
    [states],
  );
  useEffect(() => {
    if (!hasActive) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [hasActive]);

  // Map<sessionId, controller WS>
  const wsControllersRef = useRef<Map<string, { close: () => void }>>(new Map());

  // Sync states + WS subscriptions quand la selection multi change.
  useEffect(() => {
    const entries = selectedEntries;
    const currentIds = new Set(entries.map((e) => e.session.id));

    // 1. Close les WS pour sessions disparues
    for (const [sid, ctl] of Array.from(wsControllersRef.current.entries())) {
      if (!currentIds.has(sid)) {
        ctl.close();
        wsControllersRef.current.delete(sid);
        setStates((prev) => {
          const next = { ...prev };
          delete next[sid];
          return next;
        });
      }
    }

    // 2. Init states + open WS pour nouveaux
    setStates((prev) => {
      const next = { ...prev };
      entries.forEach((entry, idx) => {
        const sid = entry.session.id;
        if (!next[sid]) {
          next[sid] = {
            sessionId: sid,
            athleteId: entry.session.user_id,
            fullName: entry.fullName,
            email: entry.email,
            color: trackColorForIndex(idx),
            status: entry.session.status,
            points: [],
            connected: false,
          };
        } else {
          // Refresh couleur (au cas ou l'index change) + status REST
          next[sid] = {
            ...next[sid],
            color: trackColorForIndex(idx),
            status: entry.session.status,
          };
        }
      });
      return next;
    });

    // Open WS pour ceux qui n'en ont pas
    entries.forEach((entry) => {
      const sid = entry.session.id;
      if (wsControllersRef.current.has(sid)) return;
      const ctl = liveService.followSession(sid, {
        onStatusChange: (status) => {
          setStates((prev) => {
            const s = prev[sid];
            if (!s) return prev;
            return { ...prev, [sid]: { ...s, connected: status === 'open' } };
          });
        },
        onMessage: (msg: LiveWsMessage) => {
          if (msg.type === 'snapshot') {
            setStates((prev) => {
              const s = prev[sid];
              if (!s) return prev;
              return {
                ...prev,
                [sid]: { ...s, points: msg.points, status: msg.session.status },
              };
            });
          } else if (msg.type === 'points') {
            setStates((prev) => {
              const s = prev[sid];
              if (!s) return prev;
              const merged = mergePoints(s.points, msg.points);
              return { ...prev, [sid]: { ...s, points: merged } };
            });
          } else if (msg.type === 'ended') {
            setStates((prev) => {
              const s = prev[sid];
              if (!s) return prev;
              return { ...prev, [sid]: { ...s, status: msg.status } };
            });
          }
        },
      });
      wsControllersRef.current.set(sid, ctl);
    });
  }, [selectedEntries]);

  // Cleanup global au unmount
  useEffect(() => {
    const controllers = wsControllersRef.current;
    return () => {
      for (const ctl of controllers.values()) ctl.close();
      controllers.clear();
    };
  }, []);

  const stateValues = useMemo(() => Object.values(states), [states]);

  const tracks: AthleteTrack[] = useMemo(
    () =>
      stateValues.map((s) => ({
        id: s.sessionId,
        color: s.color,
        points: s.points,
      })),
    [stateValues],
  );

  const selected =
    (selectedId ? states[selectedId] : null) ??
    stateValues.find((state) => state.status === 'active') ??
    stateValues[0] ??
    null;
  const effectiveSelectedId = selected?.sessionId ?? null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link
          to="/live"
          className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="mr-1 h-4 w-4" />
          Live
        </Link>
        <h1 className="text-xl font-bold text-foreground">Suivi multi-athlètes</h1>
        <span className="rounded bg-blue-50 px-2 py-1 text-xs text-blue-700">
          {stateValues.length} session(s)
        </span>
      </div>

      {selectedSessionIds.length === 0 ? (
        <EmptyState />
      ) : sessionsQuery.isLoading ? (
        <div className="text-sm text-muted-foreground">Chargement...</div>
      ) : stateValues.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="space-y-4">
          {/* Row 1 : sidebar athletes + carte */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[260px_1fr]">
            <aside className="max-h-[60vh] space-y-2 overflow-auto pr-1">
              {stateValues.map((s) => (
                <AthleteRow
                  key={s.sessionId}
                  state={s}
                  isSelected={s.sessionId === effectiveSelectedId}
                  onSelect={() => setSelectedId(s.sessionId)}
                />
              ))}
            </aside>

            <div className="overflow-hidden rounded-lg bg-white shadow">
              <div className="h-[60vh]" style={{ minHeight: 360 }}>
                <LiveSharedMap tracks={tracks} focusedId={effectiveSelectedId} />
              </div>
            </div>
          </div>

          {/* Row 2 : panel détails de l'athlete sélectionné */}
          {selected ? (
            <div className="glass rounded-lg">
              <SelectedHeader state={selected} now={now} />
              <div className="border-t border-[var(--border-subtle)] px-4 py-3">
                {selected.points.length === 0 ? (
                  <div className="py-8 text-center text-sm text-muted-foreground">
                    En attente du premier point GPS pour {selected.fullName}...
                  </div>
                ) : (
                  <LiveChart points={selected.points} />
                )}
              </div>
            </div>
          ) : (
            <div className="rounded-lg bg-white p-6 text-center text-sm text-muted-foreground shadow">
              Sélectionne un athlète à gauche pour voir ses streams.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------- Sub-components ----------

function EmptyState() {
  return (
    <div className="rounded-lg bg-white p-8 text-center shadow">
      <h2 className="mb-2 text-base font-semibold text-foreground">
        Aucune session dans la vue multi-athlètes
      </h2>
      <p className="mb-4 text-sm text-muted-foreground">
        Ajoute des sessions depuis la page Live avec le bouton multi-athlètes.
        <br />
        <Link to="/live" className="text-[var(--brand-cyan)] underline">
          Retourner à Live
        </Link>
      </p>
    </div>
  );
}

function AthleteRow({
  state,
  isSelected,
  onSelect,
}: {
  state: AthleteState;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const active = state.status === 'active';
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors ${
        isSelected
          ? 'border-primary-500 bg-primary-50 ring-1 ring-primary-200'
          : 'border-[var(--border-subtle)] bg-white hover:bg-white/5'
      }`}
    >
      <Avatar name={state.fullName} color={state.color} size={36} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-foreground">
          {state.fullName}
        </div>
        <div className="flex items-center gap-1 truncate text-xs text-muted-foreground">
          {active ? (
            <Wifi
              className={`h-3 w-3 ${
                state.connected ? 'text-green-600' : 'text-muted-foreground'
              }`}
            />
          ) : (
            <WifiOff className="h-3 w-3 text-muted-foreground" />
          )}
          {active ? (state.connected ? 'En direct' : 'Reconnexion...') : 'Terminée'}
          <span>·</span>
          <span>{state.points.length} pts</span>
        </div>
      </div>
      <span className="h-8 w-1.5 rounded-full" style={{ backgroundColor: state.color }} />
    </button>
  );
}

function SelectedHeader({ state, now }: { state: AthleteState; now: number }) {
  const m = useMemo(
    () => computeQuickMetrics(state.points, now, state.status === 'active'),
    [state.points, now, state.status],
  );
  return (
    <div className="grid grid-cols-1 items-center gap-4 p-4 md:grid-cols-[auto_1fr]">
      <div className="flex min-w-0 items-center gap-3">
        <Avatar name={state.fullName} color={state.color} size={44} />
        <div className="min-w-0">
          <div className="flex items-center gap-2 truncate font-semibold text-foreground">
            {state.fullName}
            {state.status !== 'active' && (
              <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                {state.status}
              </span>
            )}
          </div>
          <div className="truncate text-xs text-muted-foreground">{state.email}</div>
        </div>
      </div>

      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-5">
        <MetricCell label="Durée" value={formatDuration(m.durationSec)} Icon={Clock} />
        <MetricCell
          label="Distance"
          value={m.distanceKm.toFixed(2) + ' km'}
          Icon={MapPin}
        />
        <MetricCell
          label="Allure"
          value={m.paceMinPerKm ? formatPace(m.paceMinPerKm) : '—'}
          Icon={ActivityIcon}
        />
        <MetricCell
          label="Vitesse"
          value={m.speedKmh != null ? m.speedKmh.toFixed(1) + ' km/h' : '—'}
          Icon={Gauge}
        />
        <MetricCell label="FC" value={m.hr != null ? `${m.hr} bpm` : '—'} Icon={Heart} />
      </ul>
    </div>
  );
}

function MetricCell({
  label,
  value,
  Icon,
}: {
  label: string;
  value: string;
  Icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <li className="flex flex-col rounded bg-white/5 px-3 py-2">
      <span className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-muted-foreground">
        <Icon className="h-3 w-3" />
        {label}
      </span>
      <span className="mt-0.5 text-sm font-semibold tabular-nums text-foreground">
        {value}
      </span>
    </li>
  );
}

// ---------- Helpers ----------

interface QuickMetrics {
  durationSec: number;
  distanceKm: number;
  speedKmh: number | null;
  paceMinPerKm: number | null;
  hr: number | null;
}

function computeQuickMetrics(
  points: LiveTrackpoint[],
  nowMs: number,
  isActive: boolean,
): QuickMetrics {
  if (points.length === 0) {
    return emptyQuickMetrics();
  }
  const first = points[0];
  const last = points[points.length - 1];
  if (!first || !last) return emptyQuickMetrics();
  // Durée : si session active, on suit le temps réel ; sinon on fige sur le dernier point.
  const endMs = isActive ? Math.max(nowMs, last.ts * 1000) : last.ts * 1000;
  const elapsed = Math.max(0, Math.floor((endMs - first.ts * 1000) / 1000));

  // Distance haversine en fallback si pas de distance Garmin
  let distanceM = last.distance ?? null;
  if (distanceM == null) {
    distanceM = 0;
    let prev: LiveTrackpoint | null = null;
    for (const p of points) {
      if (
        prev &&
        p.lat != null &&
        p.lng != null &&
        prev.lat != null &&
        prev.lng != null
      ) {
        const d = haversine(prev.lat, prev.lng, p.lat, p.lng);
        if (d < 100) distanceM += d;
      }
      prev = p;
    }
  }

  const window = points.slice(-10);
  const speedsMs = window
    .map((p) => p.speed)
    .filter((s): s is number => typeof s === 'number');
  const avg =
    speedsMs.length > 0 ? speedsMs.reduce((a, b) => a + b, 0) / speedsMs.length : null;
  const speedKmh = avg != null ? avg * 3.6 : null;
  const paceMinPerKm = avg && avg > 0.3 ? 1000 / avg / 60 : null;

  let hr: number | null = null;
  const cutoff = last.ts - 30;
  for (let i = points.length - 1; i >= 0; i--) {
    const point = points[i];
    if (!point || point.ts < cutoff) break;
    if (point.hr != null) {
      hr = point.hr;
      break;
    }
  }

  return {
    durationSec: elapsed,
    distanceKm: distanceM / 1000,
    speedKmh,
    paceMinPerKm,
    hr,
  };
}

function mergePoints(
  prev: LiveTrackpoint[],
  incoming: LiveTrackpoint[],
): LiveTrackpoint[] {
  if (incoming.length === 0) return prev;
  const lastTs = prev[prev.length - 1]?.ts ?? -1;
  const fresh = incoming.filter((p) => p.ts > lastTs).sort((a, b) => a.ts - b.ts);
  return fresh.length > 0 ? [...prev, ...fresh] : prev;
}

function emptyQuickMetrics(): QuickMetrics {
  return {
    durationSec: 0,
    distanceKm: 0,
    speedKmh: null,
    paceMinPerKm: null,
    hr: null,
  };
}

function haversine(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function formatSessionDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR');
}

function formatDuration(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function formatPace(minPerKm: number): string {
  if (!isFinite(minPerKm) || minPerKm <= 0) return '—';
  const min = Math.floor(minPerKm);
  const sec = Math.round((minPerKm - min) * 60);
  return `${min}'${String(sec).padStart(2, '0')}"/km`;
}
