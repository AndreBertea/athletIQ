import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft } from 'lucide-react';
import LiveSharedMap from '@/components/live/LiveSharedMap';
import type { AthleteTrack } from '@/components/live/LiveSharedMap';
import { AppShell } from '@/components/shared/AppShell';
import { trackColorForIndex } from '@/components/shared/avatar-colors';
import { liveService } from '@/lib/api/live';
import type { LiveSession, LiveSessionStatus, LiveTrackpoint, LiveWsMessage } from '@/lib/api/live';
import {
  LIVE_MULTI_SELECTION_EVENT,
  readLiveMultiSessionIds,
} from '@/lib/live-multi-selection';
import { cn } from '@/lib/utils';

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

type SelectedId = 'all' | string;

export default function SharedLiveRoute() {
  return (
    <AppShell hideTopBar hideBottomNav disableMainPadding mainClassName="overflow-hidden">
      <SharedLiveContent />
    </AppShell>
  );
}

function SharedLiveContent() {
  const [selectedSessionIds, setSelectedSessionIds] = useState(readLiveMultiSessionIds);
  const [states, setStates] = useState<Record<string, AthleteState>>({});
  const [selectedId, setSelectedId] = useState<SelectedId>('all');
  const [expanded, setExpanded] = useState(false);
  const [now, setNow] = useState(() => Date.now());

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

  const hasActive = useMemo(
    () => Object.values(states).some((state) => state.status === 'active'),
    [states],
  );

  useEffect(() => {
    if (!hasActive) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [hasActive]);

  const wsControllersRef = useRef<Map<string, { close: () => void }>>(new Map());

  useEffect(() => {
    const entries = selectedEntries;
    const currentIds = new Set(entries.map((entry) => entry.session.id));

    for (const [sessionId, controller] of Array.from(wsControllersRef.current.entries())) {
      if (!currentIds.has(sessionId)) {
        controller.close();
        wsControllersRef.current.delete(sessionId);
        setStates((prev) => {
          const next = { ...prev };
          delete next[sessionId];
          return next;
        });
      }
    }

    setStates((prev) => {
      const next = { ...prev };
      entries.forEach((entry, index) => {
        const sessionId = entry.session.id;
        const color = trackColorForIndex(index);
        const current = next[sessionId];
        next[sessionId] = current
          ? { ...current, color, status: entry.session.status }
          : {
              sessionId,
              athleteId: entry.session.user_id,
              fullName: entry.fullName,
              email: entry.email,
              color,
              status: entry.session.status,
              points: [],
              connected: false,
            };
      });
      return next;
    });

    entries.forEach((entry) => {
      const sessionId = entry.session.id;
      if (wsControllersRef.current.has(sessionId)) return;
      const controller = liveService.followSession(sessionId, {
        onStatusChange: (status) => {
          setStates((prev) => {
            const state = prev[sessionId];
            if (!state) return prev;
            return { ...prev, [sessionId]: { ...state, connected: status === 'open' } };
          });
        },
        onMessage: (msg: LiveWsMessage) => {
          if (msg.type === 'snapshot') {
            setStates((prev) => {
              const state = prev[sessionId];
              if (!state) return prev;
              return {
                ...prev,
                [sessionId]: { ...state, points: msg.points, status: msg.session.status },
              };
            });
          } else if (msg.type === 'points') {
            setStates((prev) => {
              const state = prev[sessionId];
              if (!state) return prev;
              return {
                ...prev,
                [sessionId]: { ...state, points: mergePoints(state.points, msg.points) },
              };
            });
          } else if (msg.type === 'ended') {
            setStates((prev) => {
              const state = prev[sessionId];
              if (!state) return prev;
              return { ...prev, [sessionId]: { ...state, status: msg.status } };
            });
          }
        },
      });
      wsControllersRef.current.set(sessionId, controller);
    });
  }, [selectedEntries]);

  useEffect(() => {
    const controllers = wsControllersRef.current;
    return () => {
      for (const controller of controllers.values()) controller.close();
      controllers.clear();
    };
  }, []);

  const stateValues = useMemo(() => Object.values(states), [states]);
  const visibleSelectedId: SelectedId =
    selectedId !== 'all' && !states[selectedId] ? 'all' : selectedId;
  const tracks: AthleteTrack[] = useMemo(
    () =>
      stateValues.map((state) => ({
        id: state.sessionId,
        color: state.color,
        points: state.points,
      })),
    [stateValues],
  );

  const selectedAthlete = visibleSelectedId === 'all' ? null : states[visibleSelectedId] ?? null;
  const focusedId = selectedAthlete?.sessionId ?? null;
  const activeCount = stateValues.filter((state) => state.status === 'active').length;
  const empty =
    selectedSessionIds.length === 0 ||
    (!sessionsQuery.isLoading && selectedSessionIds.length > 0 && stateValues.length === 0);

  return (
    <div className="relative h-full overflow-hidden bg-background">
      <LiveSharedMap tracks={tracks} focusedId={focusedId} />
      <div className="pointer-events-none absolute inset-0 z-[2]" style={{ background: 'var(--map-scrim)' }} />

      <Link
        to="/live"
        className="absolute left-4 top-[max(14px,env(safe-area-inset-top))] z-[8] inline-flex items-center gap-1.5 rounded-full border border-[var(--glass-panel-border)] bg-[var(--glass-panel)] px-3 py-2 text-[13px] font-medium text-[var(--glass-panel-fg)] shadow-lg backdrop-blur-xl"
      >
        <ArrowLeft className="h-4 w-4" />
        Retour
      </Link>

      <div className="absolute right-4 top-[max(14px,env(safe-area-inset-top))] z-[8] inline-flex items-center gap-1.5 rounded-full border border-success/35 bg-success/20 px-3 py-2 text-xs font-semibold text-success-soft backdrop-blur-xl">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-success-soft" />
        {activeCount} actif{activeCount > 1 ? 's' : ''}
      </div>

      <div className="absolute left-6 top-[calc(max(14px,env(safe-area-inset-top))+50px)] z-[5]">
        <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.09em] text-[var(--glass-panel-muted)]">
          Multi-athlètes
        </p>
        <h1 className="font-display text-[22px] font-bold leading-tight tracking-tight text-[var(--glass-panel-fg)]">
          Carte partagée
        </h1>
      </div>

      <section
        onClick={() => {
          if (!expanded) setExpanded(true);
        }}
        className={cn(
          'absolute inset-x-0 bottom-0 z-10 flex flex-col overflow-hidden rounded-t-[28px] bg-[var(--glass-panel-strong)] shadow-[0_-16px_48px_rgba(0,0,0,0.55)] transition-[height] duration-[380ms] ease-[cubic-bezier(0.34,1.4,0.64,1)]',
          expanded ? 'h-[82%]' : 'h-[36%]',
        )}
      >
        <div className="flex shrink-0 justify-center pb-1.5 pt-3">
          <span className="h-1 w-9 rounded-full bg-[var(--glass-panel-border)]" />
        </div>

        {empty ? (
          <EmptySheet loading={sessionsQuery.isLoading} />
        ) : (
          <>
            <AthleteChips
              states={stateValues}
              selectedId={visibleSelectedId}
              onSelect={setSelectedId}
            />

            {selectedAthlete ? (
              <SelectedAthleteSummary state={selectedAthlete} now={now} />
            ) : (
              <AllAthletesSummary states={stateValues} now={now} />
            )}

            <div
              className="flex-1 overflow-y-auto px-4 pb-[calc(16px+env(safe-area-inset-bottom))]"
              onClick={(event) => event.stopPropagation()}
            >
              {expanded ? (
                <button
                  type="button"
                  onClick={() => setExpanded(false)}
                  className="mb-2 ml-auto block rounded-full bg-[var(--glass-tile)] px-3 py-1.5 text-[11px] font-medium text-[var(--glass-panel-muted)]"
                >
                  Réduire ↓
                </button>
              ) : null}

              {stateValues.map((state) => (
                <AthleteRow
                  key={state.sessionId}
                  state={state}
                  selected={visibleSelectedId === state.sessionId}
                  dimmed={visibleSelectedId !== 'all' && visibleSelectedId !== state.sessionId}
                  now={now}
                  onSelect={() => setSelectedId(visibleSelectedId === state.sessionId ? 'all' : state.sessionId)}
                />
              ))}
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function AthleteChips({
  states,
  selectedId,
  onSelect,
}: {
  states: AthleteState[];
  selectedId: SelectedId;
  onSelect: (id: SelectedId) => void;
}) {
  return (
    <div className="scrollbar-hide flex shrink-0 gap-1.5 overflow-x-auto px-5 pb-3">
      <Chip label="Tous" color="#A0432E" active={selectedId === 'all'} onClick={() => onSelect('all')} />
      {states.map((state) => (
        <Chip
          key={state.sessionId}
          label={firstName(state.fullName)}
          color={state.color}
          active={selectedId === state.sessionId}
          onClick={() => onSelect(state.sessionId)}
          withDot
        />
      ))}
    </div>
  );
}

function Chip({
  label,
  color,
  active,
  onClick,
  withDot = false,
}: {
  label: string;
  color: string;
  active: boolean;
  onClick: () => void;
  withDot?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      className="flex h-[30px] shrink-0 items-center gap-1.5 rounded-full border px-3 text-xs font-semibold transition"
      style={{
        borderColor: active ? `${color}66` : 'var(--glass-panel-border)',
        background: active ? `${color}1A` : 'var(--glass-tile)',
        color: active ? color : 'var(--glass-panel-muted)',
      }}
    >
      {withDot ? <span className="h-[7px] w-[7px] rounded-full" style={{ background: color }} /> : null}
      {label}
    </button>
  );
}

function SelectedAthleteSummary({ state, now }: { state: AthleteState; now: number }) {
  const metrics = useMemo(
    () => computeQuickMetrics(state.points, now, state.status === 'active'),
    [state.points, now, state.status],
  );

  return (
    <div className="shrink-0 px-5 pb-3">
      <div className="mb-2 grid grid-cols-[1fr_1px_1fr]">
        <HeroValue label="Distance" value={`${metrics.distanceKm.toFixed(2)} km`} color={state.color} />
        <div className="bg-[var(--glass-panel-border)]" />
        <HeroValue label="D+" value={`${Math.round(metrics.elevationGainM)} m`} color={state.color} align="right" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <SmallValue label="Allure" value={metrics.paceMinPerKm ? formatPace(metrics.paceMinPerKm) : '—'} />
        <SmallValue label="FC" value={metrics.hr != null ? `${metrics.hr} bpm` : '—'} />
      </div>
    </div>
  );
}

function AllAthletesSummary({ states, now }: { states: AthleteState[]; now: number }) {
  const metrics = states.map((state) => computeQuickMetrics(state.points, now, state.status === 'active'));
  const distanceValues = metrics.map((metric) => metric.distanceKm).filter((value) => value > 0);
  const hrValues = metrics.map((metric) => metric.hr).filter((value): value is number => value != null);
  const avgDistance =
    distanceValues.length > 0
      ? distanceValues.reduce((sum, value) => sum + value, 0) / distanceValues.length
      : 0;
  const avgHr =
    hrValues.length > 0
      ? Math.round(hrValues.reduce((sum, value) => sum + value, 0) / hrValues.length)
      : null;

  return (
    <div className="grid shrink-0 grid-cols-3 px-5 pb-3 pt-1 text-center">
      <AllValue label="Actifs" value={String(states.filter((state) => state.status === 'active').length)} />
      <AllValue label="km moy." value={avgDistance > 0 ? avgDistance.toFixed(1) : '0.0'} />
      <AllValue label="FC moy." value={avgHr != null ? `${avgHr} bpm` : '—'} />
    </div>
  );
}

function AthleteRow({
  state,
  selected,
  dimmed,
  now,
  onSelect,
}: {
  state: AthleteState;
  selected: boolean;
  dimmed: boolean;
  now: number;
  onSelect: () => void;
}) {
  const metrics = useMemo(
    () => computeQuickMetrics(state.points, now, state.status === 'active'),
    [state.points, now, state.status],
  );

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'mb-1 grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-[10px] border px-3 py-2.5 text-left transition',
        selected ? 'bg-[var(--active-overlay)]' : 'bg-[var(--glass-tile)]',
        dimmed && 'opacity-45',
      )}
      style={{ borderColor: selected ? `${state.color}66` : 'var(--glass-panel-border)' }}
    >
      <div className="flex min-w-0 items-center gap-2">
        <span
          className={cn('h-2 w-2 shrink-0 rounded-full', state.status === 'active' && 'animate-pulse')}
          style={{ background: state.color }}
        />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-[var(--glass-panel-fg)]">{state.fullName}</p>
          <p className="truncate text-[11px] text-[var(--glass-panel-muted)]">
            {state.connected ? 'En direct' : state.status === 'active' ? 'Reconnexion...' : 'Terminée'}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2 text-xs">
        <span className="font-bold tabular-nums" style={{ color: state.color }}>
          {metrics.distanceKm.toFixed(2)} km
        </span>
        <span className="tabular-nums text-[var(--glass-panel-muted)]">
          {metrics.paceMinPerKm ? formatPaceShort(metrics.paceMinPerKm) : '—'}/km
        </span>
        <span className="tabular-nums text-danger-fg">
          {metrics.hr != null ? `${metrics.hr} bpm` : '—'}
        </span>
      </div>
    </button>
  );
}

function EmptySheet({ loading }: { loading: boolean }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-8 text-center">
      <h2 className="font-display text-lg font-bold text-[var(--glass-panel-fg)]">
        {loading ? 'Chargement des sessions...' : 'Aucune session multi-athlètes'}
      </h2>
      <p className="mt-2 text-sm leading-relaxed text-[var(--glass-panel-muted)]">
        Ajoute des sessions depuis la page Live avec le bouton multi-athlètes.
      </p>
      <Link
        to="/live"
        className="mt-4 rounded-full bg-brand-primary px-4 py-2 text-xs font-bold text-white shadow-[var(--glow-primary)]"
      >
        Retourner à Live
      </Link>
    </div>
  );
}

function HeroValue({
  label,
  value,
  color,
  align = 'left',
}: {
  label: string;
  value: string;
  color: string;
  align?: 'left' | 'right';
}) {
  return (
    <div className={cn('px-2', align === 'right' && 'text-right')}>
      <span className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.07em] text-[var(--glass-panel-muted)]">
        {label}
      </span>
      <strong className="font-display block text-[28px] font-medium leading-none tracking-tight" style={{ color }}>
        {value}
      </strong>
    </div>
  );
}

function SmallValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[var(--glass-panel-border)] bg-[var(--glass-tile)] px-3 py-2 text-center">
      <span className="mb-1 block text-[9px] font-semibold uppercase tracking-[0.07em] text-[var(--glass-panel-muted)]">
        {label}
      </span>
      <strong className="font-display text-lg font-semibold leading-none text-[var(--glass-panel-fg)]">
        {value}
      </strong>
    </div>
  );
}

function AllValue({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="font-display text-[26px] font-semibold leading-none text-[var(--glass-panel-fg)]">{value}</p>
      <p className="mt-1.5 text-[10px] font-semibold uppercase tracking-[0.05em] text-[var(--glass-panel-muted)]">
        {label}
      </p>
    </div>
  );
}

interface QuickMetrics {
  durationSec: number;
  distanceKm: number;
  speedKmh: number | null;
  paceMinPerKm: number | null;
  hr: number | null;
  elevationGainM: number;
}

function computeQuickMetrics(
  points: LiveTrackpoint[],
  nowMs: number,
  isActive: boolean,
): QuickMetrics {
  if (points.length === 0) return emptyQuickMetrics();
  const first = points[0];
  const last = points[points.length - 1];
  if (!first || !last) return emptyQuickMetrics();

  const endMs = isActive ? Math.max(nowMs, last.ts * 1000) : last.ts * 1000;
  const elapsed = Math.max(0, Math.floor((endMs - first.ts * 1000) / 1000));

  let distanceM = last.distance ?? null;
  if (distanceM == null) distanceM = computeGpsDistance(points);

  const windowPoints = points.slice(-10);
  const speedsMs = windowPoints
    .map((point) => point.speed)
    .filter((speed): speed is number => typeof speed === 'number');
  const avgSpeedMs =
    speedsMs.length > 0 ? speedsMs.reduce((sum, speed) => sum + speed, 0) / speedsMs.length : null;

  let hr: number | null = null;
  const cutoff = last.ts - 30;
  for (let index = points.length - 1; index >= 0; index -= 1) {
    const point = points[index];
    if (!point || point.ts < cutoff) break;
    if (point.hr != null) {
      hr = point.hr;
      break;
    }
  }

  return {
    durationSec: elapsed,
    distanceKm: distanceM / 1000,
    speedKmh: avgSpeedMs != null ? avgSpeedMs * 3.6 : null,
    paceMinPerKm: avgSpeedMs != null && avgSpeedMs > 0.3 ? 1000 / avgSpeedMs / 60 : null,
    hr,
    elevationGainM: computeElevationGain(points),
  };
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

function computeElevationGain(points: LiveTrackpoint[]): number {
  let gain = 0;
  let prev: number | null = null;
  for (const point of points) {
    if (point.altitude == null) continue;
    if (prev != null) {
      const delta = point.altitude - prev;
      if (delta > 0 && delta < 15) gain += delta;
    }
    prev = point.altitude;
  }
  return gain;
}

function emptyQuickMetrics(): QuickMetrics {
  return {
    durationSec: 0,
    distanceKm: 0,
    speedKmh: null,
    paceMinPerKm: null,
    hr: null,
    elevationGainM: 0,
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

function formatSessionDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR');
}

function firstName(name: string): string {
  return name.trim().split(/\s+/)[0] ?? name;
}

function formatPace(minPerKm: number): string {
  if (!Number.isFinite(minPerKm) || minPerKm <= 0) return '—';
  const totalSec = Math.round(minPerKm * 60);
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min}'${String(sec).padStart(2, '0')}"`;
}

function formatPaceShort(minPerKm: number): string {
  return formatPace(minPerKm);
}
