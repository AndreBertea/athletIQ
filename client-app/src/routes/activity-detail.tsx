import { useMemo, useRef, useState, type ReactNode, type TouchEvent as ReactTouchEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowLeftRight,
  BarChart3,
  Cloud,
  CloudSun,
  Droplets,
  Flame,
  Footprints,
  Gauge,
  Heart,
  Map as MapIcon,
  Mountain,
  MoveVertical,
  RefreshCw,
  Thermometer,
  Timer,
  Watch,
  Wind,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { AppShell } from '@/components/shared/AppShell';
import RouteMapTiler, { type RouteMapTrack } from '@/components/map/RouteMapTiler';
import MiniAreaChart from '@/components/shared/MiniAreaChart';
import {
  agonApi,
  type ActivityStreamsResponse,
  type ActivityWeather,
  type EnrichedActivity,
  type FitMetrics,
  type SegmentResponse,
} from '@/lib/api/agon';
import {
  formatDateLong,
  formatDistance,
  formatDuration,
  formatPace,
  getSportPresentation,
  speedToPace,
} from '@/lib/activity-format';
import { cn } from '@/lib/utils';
import { actionColor } from '@/lib/accent';

type TabId = 'streams' | 'segments' | 'fit' | 'weather' | 'map';

const TABS: Array<{ id: TabId; label: string; Icon: LucideIcon }> = [
  { id: 'streams', label: 'Streams', Icon: Activity },
  { id: 'segments', label: 'Segments', Icon: BarChart3 },
  { id: 'fit', label: 'FIT', Icon: Watch },
  { id: 'weather', label: 'Meteo', Icon: CloudSun },
  { id: 'map', label: 'Carte', Icon: MapIcon },
];

// 3 hauteurs du sheet, du plus petit (carte maximisée) au plus grand (déplié).
type SheetMode = 'maxi' | 'standard' | 'expanded';
const SHEET_ORDER: SheetMode[] = ['maxi', 'standard', 'expanded'];

export default function ActivityDetailRoute() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabId>('streams');
  const [sheetMode, setSheetMode] = useState<SheetMode>('standard');
  const queryClient = useQueryClient();

  // Geste vertical sur la poignée : swipe haut = mode suivant (vers déplié),
  // swipe bas = mode précédent (vers carte maximisée). Tap = standard ↔ déplié.
  const sheetTouchStartY = useRef<number | null>(null);
  const cycleSheet = (dir: 1 | -1) =>
    setSheetMode((mode) => {
      const i = SHEET_ORDER.indexOf(mode);
      const next = Math.min(SHEET_ORDER.length - 1, Math.max(0, i + dir));
      return SHEET_ORDER[next] ?? mode;
    });
  const onSheetTouchStart = (event: ReactTouchEvent) => {
    sheetTouchStartY.current = event.touches[0]?.clientY ?? null;
  };
  const onSheetTouchEnd = (event: ReactTouchEvent) => {
    const startY = sheetTouchStartY.current;
    sheetTouchStartY.current = null;
    if (startY == null) return;
    const deltaY = (event.changedTouches[0]?.clientY ?? startY) - startY;
    if (deltaY < -40) cycleSheet(1);
    else if (deltaY > 40) cycleSheet(-1);
  };

  const activityQuery = useQuery({
    queryKey: ['agon', 'activity', id],
    queryFn: () => agonApi.getEnrichedActivity(id ?? ''),
    enabled: Boolean(id),
  });

  const streamsQuery = useQuery({
    queryKey: ['agon', 'activity-streams', id],
    queryFn: () => agonApi.getEnrichedActivityStreams(id ?? ''),
    enabled: Boolean(id),
    staleTime: 10 * 60_000,
    retry: false,
  });

  const activity = activityQuery.data;
  const activityId = id ?? '';

  const fitQuery = useQuery({
    queryKey: ['agon', 'activity-fit', activityId],
    queryFn: () => agonApi.getActivityFitMetrics(activityId),
    enabled: Boolean(activityId) && activity?.has_fit_metrics === true,
    staleTime: 30 * 60_000,
    retry: false,
  });

  const weatherQuery = useQuery({
    queryKey: ['agon', 'activity-weather', activityId],
    queryFn: () => agonApi.getActivityWeather(activityId),
    enabled: Boolean(activityId) && activity?.has_weather === true,
    staleTime: 30 * 60_000,
    retry: false,
  });
  const weatherEnrich = useMutation({
    mutationFn: () => agonApi.enrichActivityWeather(activityId),
    onSuccess: (weather) => {
      queryClient.setQueryData(['agon', 'activity-weather', activityId], weather);
      void queryClient.invalidateQueries({ queryKey: ['agon', 'activity', activityId] });
      void queryClient.invalidateQueries({ queryKey: ['agon', 'weather-status'] });
    },
  });

  const segmentsQuery = useQuery({
    queryKey: ['agon', 'activity-segments', activityId],
    queryFn: () => agonApi.getActivitySegments(activityId),
    enabled: Boolean(activityId) && activeTab === 'segments',
    staleTime: 10 * 60_000,
    retry: false,
  });

  const streamData = useMemo(
    () => buildStreamData(streamsQuery.data?.streams),
    [streamsQuery.data?.streams],
  );
  const altitudeSeries = useMemo(
    () => streamData.map((point) => point.altitude),
    [streamData],
  );
  const altitudeStats = useMemo(() => {
    const vals = altitudeSeries.filter((v): v is number => Number.isFinite(v));
    if (!vals.length) return null;
    return { min: Math.round(Math.min(...vals)), max: Math.round(Math.max(...vals)) };
  }, [altitudeSeries]);
  const routeTrack = useMemo(
    () => (activity ? buildRouteTrack(activity, streamsQuery.data?.streams) : null),
    [activity, streamsQuery.data?.streams],
  );
  const sport = activity ? getSportPresentation(activity.sport_type) : null;
  const pace = activity ? speedToPace(activity.avg_speed_m_s ?? activity.avg_speed_mps ?? null) : null;
  const startTime = activity
    ? new Date(activity.start_date_utc).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
    : '';
  const weather = weatherEnrich.data ?? weatherQuery.data;

  return (
    <AppShell hideTopBar hideBottomNav disableMainPadding mainClassName="overflow-hidden">
      <div className="relative h-full overflow-hidden bg-background">
        {activityQuery.isLoading ? (
          <FullscreenState label="Chargement de l'activité..." />
        ) : !activity ? (
          <FullscreenState label="Activité introuvable" icon={AlertTriangle} />
        ) : (
          <>
            <RouteMapTiler
              tracks={routeTrack ? [routeTrack] : []}
              className="absolute inset-0 z-[1] h-full w-full"
              fallbackLabel="Pas de trace GPS disponible"
              fitPadding={88}
              loading={streamsQuery.isLoading || streamsQuery.isFetching}
              onRefresh={() => void streamsQuery.refetch()}
            />
            <div className="pointer-events-none absolute inset-0 z-[2]" style={{ background: 'var(--map-scrim)' }} />

            <button
              type="button"
              onClick={() => navigate(-1)}
              className="absolute left-4 top-[max(14px,env(safe-area-inset-top))] z-[8] inline-flex items-center gap-1.5 rounded-full border border-[var(--glass-panel-border)] bg-[var(--glass-panel)] px-3 py-2 text-[13px] font-medium text-[var(--glass-panel-fg)] shadow-lg backdrop-blur-xl"
            >
              <ArrowLeft className="h-4 w-4" />
              Retour
            </button>

            <div className="absolute left-6 top-[calc(max(14px,env(safe-area-inset-top))+50px)] z-[5]">
              <p className="font-display text-[42px] font-medium leading-none tracking-tight text-[var(--spark)] drop-shadow-[0_2px_12px_rgba(156,73,245,0.45)]">
                {formatDistance(activity.distance_m).replace(/\s?km$/i, '')}{' '}
                <span className="text-lg font-normal text-[var(--glass-panel-muted)]">km</span>
              </p>
              <p className="mt-1 font-display text-xl font-semibold tracking-tight text-[var(--spark)] drop-shadow-[0_2px_12px_rgba(156,73,245,0.45)]">
                {formatDuration(activity.moving_time_s)}
              </p>
            </div>

            <section
              className={cn(
                'absolute inset-x-0 bottom-0 z-10 flex flex-col overflow-hidden rounded-t-[28px] bg-[var(--glass-panel)] shadow-[0_-16px_48px_rgba(0,0,0,0.55)] backdrop-blur-2xl transition-[height] duration-[380ms] ease-[cubic-bezier(0.34,1.4,0.64,1)]',
                sheetMode === 'expanded'
                  ? 'h-[82%]'
                  : sheetMode === 'standard'
                    ? 'h-[34%]'
                    : 'h-[18%]',
              )}
            >
              {/* Poignée + en-tête = zone de geste : swipe haut/bas pour changer
                  de mode (maxi ↔ standard ↔ déplié). Tap = standard ↔ déplié. */}
              <div
                onTouchStart={onSheetTouchStart}
                onTouchEnd={onSheetTouchEnd}
                onClick={() => setSheetMode((m) => (m === 'standard' ? 'expanded' : 'standard'))}
                className="shrink-0 cursor-grab touch-none active:cursor-grabbing"
              >
                <div className="flex justify-center pb-1 pt-3">
                  <span className="h-1 w-9 rounded-full bg-[var(--glass-panel-border)]" />
                </div>

                <div className="flex items-start justify-between gap-3 px-6 pt-1">
                  <div className="min-w-0">
                    <h1 className="font-display truncate text-base font-bold tracking-tight text-[var(--glass-panel-fg)]">
                      {activity.name}
                    </h1>
                    <p className="mt-0.5 truncate text-[11px] text-[var(--glass-panel-muted)]">
                      {sheetMode === 'maxi'
                        ? `${formatDateLong(activity.start_date_utc)} · ${startTime}${pace ? ` · ${formatPace(pace)}` : ''}`
                        : `${formatDateLong(activity.start_date_utc)} · ${sport?.label ?? activity.sport_type}${pace ? ` · ${formatPace(pace)}` : ''}`}
                    </p>
                  </div>
                </div>
              </div>

              {/* Métriques héro masquées en mode maxi (carte maximisée). */}
              {sheetMode !== 'maxi' ? (
                <div className="grid shrink-0 grid-cols-[1fr_1px_1fr] px-7 pb-3 pt-4">
                  <ActivityHeroMetric
                    label="Rythme moyen"
                    value={pace ? formatPace(pace).replace('/km', '') : '—'}
                    unit="/KM"
                  />
                  <div className="bg-[var(--glass-panel-border)]" />
                  <ActivityHeroMetric
                    label="D+"
                    value={activity.elev_gain_m != null ? String(Math.round(activity.elev_gain_m)) : '—'}
                    unit="M"
                    align="right"
                  />
                </div>
              ) : null}

              {/* Petite altimétrie — uniquement en mode standard.
                  Dépliée, elle laisse place à la pile de graphiques ci-dessous. */}
              {sheetMode === 'standard' ? (
                <div className="shrink-0 px-5 pb-3">
                  <div className="mb-2 flex items-baseline justify-between">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--glass-panel-muted)]">
                      Profil d'altitude
                    </p>
                    {altitudeStats ? (
                      <p className="text-[10px] tabular-nums text-[var(--glass-panel-muted)]">
                        {altitudeStats.min}–{altitudeStats.max} m
                      </p>
                    ) : null}
                  </div>
                  <MiniAreaChart
                    data={altitudeSeries}
                    color="#9C49F5"
                    height={72}
                    className="bg-[var(--glass-tile)]"
                  />
                </div>
              ) : null}

              {sheetMode === 'expanded' ? (
                <div
                  className="flex-1 overflow-y-auto px-6 pb-[calc(24px+env(safe-area-inset-bottom))]"
                  onClick={(event) => event.stopPropagation()}
                >
                  {/* Pile de graphiques swipeable (altitude → allure → FC),
                      épinglée en haut du contenu déplié. */}
                  <div className="sticky top-0 z-10 -mx-6 mb-3 bg-[var(--glass-panel)] px-6 pb-3 pt-1 backdrop-blur-xl">
                    <StreamStack streamData={streamData} />
                  </div>

                  <div className="grid grid-cols-4 gap-2">
                    <SheetStat label="Temps" value={formatDuration(activity.moving_time_s)} />
                    <SheetStat label="Allure" value={pace ? formatPace(pace) : '—'} />
                    <SheetStat
                      label="FC moy."
                      value={
                        activity.avg_heartrate_bpm != null && activity.avg_heartrate_bpm > 0
                          ? `${Math.round(activity.avg_heartrate_bpm)}`
                          : '—'
                      }
                    />
                    <SheetStat
                      label="FC max"
                      value={
                        activity.max_heartrate_bpm != null && activity.max_heartrate_bpm > 0
                          ? `${Math.round(activity.max_heartrate_bpm)}`
                          : '—'
                      }
                    />
                  </div>

                  <DataCoverage activity={activity} />

                  <div className="mt-4">
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.07em] text-[var(--glass-panel-muted)]">
                      Données activité
                    </p>
                    <div className="scrollbar-hide -mx-1 mb-3 flex gap-1.5 overflow-x-auto px-1">
                      {TABS.map(({ id: tabId, label, Icon }) => {
                        const selected = activeTab === tabId;
                        return (
                          <button
                            key={tabId}
                            type="button"
                            onClick={() => setActiveTab(tabId)}
                            className={cn(
                              'inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-3 text-xs font-semibold transition',
                              selected
                                ? 'border-brand-sunset/40 bg-brand-sunset/15 text-brand-sunset'
                                : 'border-[var(--glass-panel-border)] bg-[var(--glass-tile)] text-[var(--glass-panel-muted)]',
                            )}
                          >
                            <Icon className="h-3.5 w-3.5" />
                            {label}
                          </button>
                        );
                      })}
                    </div>

                    <div className="activity-detail-panel">
                      {activeTab === 'streams' ? (
                        <StreamsPanel
                          data={streamsQuery.data}
                          isLoading={streamsQuery.isLoading}
                          isError={streamsQuery.isError}
                        />
                      ) : null}

                      {activeTab === 'segments' ? (
                        <SegmentsPanel
                          data={segmentsQuery.data}
                          isLoading={segmentsQuery.isLoading}
                          isError={segmentsQuery.isError}
                        />
                      ) : null}

                      {activeTab === 'fit' ? (
                        <FitPanel
                          data={fitQuery.data}
                          hasFit={activity.has_fit_metrics === true}
                          isLoading={fitQuery.isLoading}
                          isError={fitQuery.isError}
                          streams={streamsQuery.data}
                        />
                      ) : null}

                      {activeTab === 'weather' ? (
                        <WeatherPanel
                          data={weather}
                          hasWeather={activity.has_weather === true || Boolean(weather)}
                          isLoading={weatherQuery.isLoading}
                          isError={weatherQuery.isError}
                          isEnriching={weatherEnrich.isPending}
                          enrichError={weatherEnrich.isError}
                          onEnrich={() => weatherEnrich.mutate()}
                        />
                      ) : null}

                      {activeTab === 'map' ? (
                        <MapPanel
                          activity={activity}
                          streams={streamsQuery.data}
                          isLoading={streamsQuery.isLoading || streamsQuery.isFetching}
                          onRefresh={() => void streamsQuery.refetch()}
                        />
                      ) : null}
                    </div>
                  </div>

                  <ActivityChips activity={activity} weather={weather} fit={fitQuery.data} />
                </div>
              ) : null}
            </section>
          </>
        )}
      </div>
    </AppShell>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <div className="bg-card border-border-subtle rounded-md border p-3">
      <Icon className="text-brand-cyan mb-2 h-4 w-4" />
      <p className="text-foreground text-lg font-bold leading-none">{value}</p>
      <p className="text-muted-foreground mt-1 text-xs">{label}</p>
    </div>
  );
}

function FullscreenState({
  label,
  icon: Icon,
}: {
  label: string;
  icon?: LucideIcon;
}) {
  return (
    <div className="flex h-full items-center justify-center bg-background px-8 text-center">
      <div className="rounded-[18px] border border-[var(--glass-panel-border)] bg-[var(--glass-panel-strong)] px-5 py-5 text-[var(--glass-panel-muted)] shadow-2xl backdrop-blur-xl">
        {Icon ? <Icon className="mx-auto mb-3 h-7 w-7 text-[var(--glass-panel-muted)]" /> : null}
        <p className="text-sm font-semibold">{label}</p>
      </div>
    </div>
  );
}

function ActivityHeroMetric({
  label,
  value,
  unit,
  align = 'left',
}: {
  label: string;
  value: string;
  unit: string;
  align?: 'left' | 'right';
}) {
  const normalizedValue = value === '—' ? '—' : value.replace(/\s?(km|m)$/i, '');

  return (
    <div className={cn('min-w-0', align === 'right' && 'text-right')}>
      <span className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.07em] text-[var(--glass-panel-muted)]">
        {label}
      </span>
      <strong className="font-display block truncate text-[34px] font-medium leading-none tracking-tight text-[var(--spark)]">
        {normalizedValue}{' '}
        {normalizedValue !== '—' ? (
          <span className="text-sm font-normal text-[var(--glass-panel-muted)]">{unit}</span>
        ) : null}
      </strong>
    </div>
  );
}

function SheetStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[var(--glass-panel-border)] bg-[var(--glass-tile)] px-2 py-2.5">
      <p className="mb-1.5 truncate text-[9px] font-semibold uppercase tracking-[0.05em] text-[var(--glass-panel-muted)]">
        {label}
      </p>
      <p className="font-display truncate text-[13px] font-bold leading-none text-[var(--glass-panel-fg)]">
        {value}
      </p>
    </div>
  );
}

function ActivityChips({
  activity,
  weather,
  fit,
}: {
  activity: EnrichedActivity;
  weather: ActivityWeather | undefined;
  fit: FitMetrics | undefined;
}) {
  const chips = [
    activity.avg_heartrate_bpm != null && activity.avg_heartrate_bpm > 0
      ? {
          label: `${Math.round(activity.avg_heartrate_bpm)} bpm moy.`,
          Icon: Heart,
          className: 'border-danger/25 bg-danger/10 text-danger-fg',
        }
      : null,
    weather?.temperature_c != null
      ? {
          label: `${weather.temperature_c.toFixed(1)}°C`,
          Icon: Thermometer,
          className: 'border-brand-sunset/25 bg-brand-sunset/10 text-brand-sunset',
        }
      : null,
    fit?.aerobic_training_effect != null
      ? {
          label: `TE ${fit.aerobic_training_effect.toFixed(1)}`,
          Icon: Gauge,
          className: 'border-success/25 bg-success/10 text-success-fg',
        }
      : null,
  ].filter((chip): chip is { label: string; Icon: LucideIcon; className: string } => chip != null);

  if (chips.length === 0) return null;

  return (
    <div className="mt-4 flex flex-wrap gap-1.5">
      {chips.map(({ label, Icon, className }) => (
        <span
          key={label}
          className={cn('inline-flex items-center gap-1 rounded-full border px-2.5 py-1.5 text-xs font-medium', className)}
        >
          <Icon className="h-3 w-3" />
          {label}
        </span>
      ))}
    </div>
  );
}

function DataCoverage({ activity }: { activity: EnrichedActivity }) {
  const items = [
    { label: 'Streams', active: activity.has_streams === true, Icon: Activity },
    { label: 'FIT', active: activity.has_fit_metrics === true, Icon: Watch },
    { label: 'Météo', active: activity.has_weather === true, Icon: CloudSun },
    { label: 'Trace', active: hasMapCandidate(activity), Icon: MapIcon },
  ];

  return (
    <section className="mt-4">
      <p className="mb-2.5 text-[11px] font-semibold uppercase tracking-[0.07em] text-[var(--glass-panel-muted)]">
        Données disponibles
      </p>
      <div className="grid grid-cols-4 gap-1.5">
        {items.map(({ label, active, Icon }) => (
          <div
            key={label}
            className={cn(
              'rounded-lg border px-1 py-2 text-center',
              active
                ? 'border-success/25 bg-success/10 text-success-fg'
                : 'border-[var(--glass-panel-border)] bg-[var(--glass-tile)] text-[var(--glass-panel-muted)]',
            )}
          >
            <Icon className="mx-auto mb-1 h-3.5 w-3.5" />
            <p className="text-[9px] font-semibold">{label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

type StackCard = {
  key: string;
  title: string;
  unit: string;
  color: string;
  dataKey: keyof StreamPoint;
};

/**
 * Pile de graphiques empilés et swipeables : altitude (défaut) → allure → FC.
 * Swipe horizontal ou tap sur les dots pour défiler. L'indicateur (dots) est
 * affiché à côté du titre du graphique courant. Remplace les graphiques
 * séparés du panneau Streams.
 */
function StreamStack({ streamData }: { streamData: StreamPoint[] }) {
  const cards = useMemo<StackCard[]>(() => {
    const out: StackCard[] = [];
    if (streamData.some((point) => point.altitude != null))
      out.push({ key: 'altitude', title: "Profil d'altitude", unit: 'm', color: '#9C49F5', dataKey: 'altitude' });
    if (streamData.some((point) => point.pace != null))
      out.push({ key: 'pace', title: 'Allure', unit: 'min/km', color: 'var(--success)', dataKey: 'pace' });
    if (streamData.some((point) => point.heartrate != null))
      out.push({ key: 'heartrate', title: 'Fréquence cardiaque', unit: 'bpm', color: 'var(--danger)', dataKey: 'heartrate' });
    return out;
  }, [streamData]);

  const [index, setIndex] = useState(0);
  const touchX = useRef<number | null>(null);

  if (cards.length === 0) return null;

  const safeIndex = Math.min(index, cards.length - 1);
  const active = cards[safeIndex]!;
  const go = (next: number) => setIndex(((next % cards.length) + cards.length) % cards.length);

  const onTouchStart = (event: ReactTouchEvent) => {
    touchX.current = event.touches[0]?.clientX ?? null;
  };
  const onTouchEnd = (event: ReactTouchEvent) => {
    const start = touchX.current;
    touchX.current = null;
    if (start == null) return;
    const deltaX = (event.changedTouches[0]?.clientX ?? start) - start;
    if (deltaX < -40) go(safeIndex + 1);
    else if (deltaX > 40) go(safeIndex - 1);
  };

  const dots = (
    <span className="flex items-center gap-1" role="tablist" aria-label="Graphiques">
      {cards.map((card, i) => (
        <button
          key={card.key}
          type="button"
          role="tab"
          aria-selected={i === safeIndex}
          aria-label={card.title}
          onClick={() => go(i)}
          className={cn(
            'h-1.5 rounded-full transition-all',
            i === safeIndex ? 'w-4 bg-brand-primary' : 'w-1.5 bg-[var(--active-overlay)]',
          )}
        />
      ))}
    </span>
  );

  return (
    <div className="relative select-none" onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>
      {/* Couches empilées derrière (effet pile) */}
      {cards.length > 1 ? (
        <div
          aria-hidden="true"
          className="border-border-subtle bg-card absolute inset-x-2 -bottom-1.5 top-2 rounded-md border opacity-60"
        />
      ) : null}
      {cards.length > 2 ? (
        <div
          aria-hidden="true"
          className="border-border-subtle bg-card absolute inset-x-4 -bottom-3 top-3.5 rounded-md border opacity-40"
        />
      ) : null}

      <div className="relative z-10">
        <StreamChart
          title={active.title}
          data={streamData}
          dataKey={active.dataKey}
          unit={active.unit}
          color={active.color}
          indicator={dots}
        />
      </div>
    </div>
  );
}

function StreamsPanel({
  data,
  isLoading,
  isError,
}: {
  data: ActivityStreamsResponse | undefined;
  isLoading: boolean;
  isError: boolean;
}) {
  const streamData = useMemo(() => buildStreamData(data?.streams), [data?.streams]);
  const pointCount = streamData.length;

  if (isLoading) return <LoadingBlock label="Chargement des streams..." />;
  if (isError || !data?.streams) {
    return <EmptyBlock icon={Activity} title="Streams indisponibles" />;
  }
  if (pointCount === 0) {
    return <EmptyBlock icon={Activity} title="Aucun stream exploitable" />;
  }

  return (
    <section className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <MetricCard icon={Activity} label="Points" value={String(pointCount)} />
        <MetricCard icon={Gauge} label="Distance axe" value={`${streamData[pointCount - 1]?.km.toFixed(1) ?? '—'} km`} />
      </div>
      <p className="text-muted-foreground text-[11px]">
        Altitude, allure et FC sont regroupés dans la pile de graphiques en haut.
      </p>
    </section>
  );
}

function StreamChart({
  title,
  data,
  dataKey,
  unit,
  color,
  indicator,
}: {
  title: string;
  data: StreamPoint[];
  dataKey: keyof StreamPoint;
  unit: string;
  color: string;
  indicator?: ReactNode;
}) {
  const values = data
    .map((point) => point[dataKey])
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  const stats = values.length
    ? {
        min: Math.min(...values),
        max: Math.max(...values),
        avg: values.reduce((sum, value) => sum + value, 0) / values.length,
      }
    : null;
  const fmt = (value: number) =>
    unit === 'min/km' ? formatPace(value) : Math.round(value).toLocaleString('fr-FR');

  return (
    <section className="border-border-subtle bg-card rounded-md border p-4">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <div className="flex items-center gap-2">
          <p className="text-eyebrow">{title}</p>
          {indicator}
        </div>
        {stats ? (
          <span className="text-muted-foreground text-[10px] tabular-nums">
            min {fmt(stats.min)} · moy {fmt(stats.avg)} · max {fmt(stats.max)} {unit}
          </span>
        ) : (
          <span className="text-muted-foreground text-[11px]">{unit}</span>
        )}
      </div>
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1} initialDimension={{ width: 1, height: 1 }}>
          <AreaChart data={data}>
            <XAxis
              dataKey="km"
              type="number"
              domain={['dataMin', 'dataMax']}
              hide
            />
            <YAxis hide domain={['dataMin', 'dataMax']} />
            <Tooltip
              contentStyle={{
                background: 'var(--surface-2)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 8,
                color: 'var(--foreground)',
              }}
              labelFormatter={(value) => `${Number(value).toFixed(1)} km`}
              formatter={(value) => [`${Number(value).toFixed(1)} ${unit}`, title]}
            />
            <Area
              type="monotone"
              dataKey={dataKey as string}
              stroke={color}
              fill={color}
              fillOpacity={0.16}
              strokeWidth={2}
              connectNulls
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function SegmentsPanel({
  data,
  isLoading,
  isError,
}: {
  data: SegmentResponse | undefined;
  isLoading: boolean;
  isError: boolean;
}) {
  if (isLoading) return <LoadingBlock label="Chargement des segments..." />;
  if (isError || !data) return <EmptyBlock icon={BarChart3} title="Segments indisponibles" />;
  if (data.segment_count === 0) return <EmptyBlock icon={BarChart3} title="Aucun segment trouve" />;

  const totalDistance = data.segments.reduce(
    (sum, item) => sum + (item.segment.distance_m || 0),
    0,
  );
  const lastFeatures = data.segments[data.segments.length - 1]?.features;

  return (
    <section className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <MetricCard icon={BarChart3} label="Segments" value={String(data.segment_count)} />
        <MetricCard icon={Activity} label="Distance" value={formatDistance(totalDistance)} />
        <MetricCard
          icon={Heart}
          label="Cardiac drift"
          value={
            lastFeatures?.cardiac_drift != null
              ? `${(lastFeatures.cardiac_drift * 100).toFixed(1)}%`
              : '—'
          }
        />
        <MetricCard
          icon={Gauge}
          label="Efficacite"
          value={
            lastFeatures?.efficiency_factor != null
              ? lastFeatures.efficiency_factor.toFixed(3)
              : '—'
          }
        />
      </div>

      <div className="border-border-subtle bg-card overflow-hidden rounded-md border">
        {data.segments.map((item, index) => (
          <div
            key={item.segment.id}
            className={cn(
              'px-4 py-3',
              index !== data.segments.length - 1 && 'border-border-subtle border-b',
            )}
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <p className="text-foreground text-sm font-semibold">
                Segment {item.segment.segment_index + 1}
              </p>
              <span className="text-brand-cyan text-xs font-semibold">
                {formatDistance(item.segment.distance_m)}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2 text-[11px]">
              <MiniValue label="Temps" value={formatDuration(item.segment.elapsed_time_s)} />
              <MiniValue label="Allure" value={formatPace(item.segment.pace_min_per_km)} />
              <MiniValue
                label="Pente"
                value={
                  item.segment.avg_grade_percent != null
                    ? `${item.segment.avg_grade_percent.toFixed(1)}%`
                    : '—'
                }
              />
              <MiniValue
                label="D+"
                value={
                  item.segment.elevation_gain_m != null
                    ? `${Math.round(item.segment.elevation_gain_m)} m`
                    : '—'
                }
              />
              <MiniValue
                label="FC"
                value={
                  item.segment.avg_hr != null
                    ? `${Math.round(item.segment.avg_hr)}`
                    : '—'
                }
              />
              <MiniValue
                label="EF"
                value={
                  item.features?.efficiency_factor != null
                    ? item.features.efficiency_factor.toFixed(3)
                    : '—'
                }
              />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function FitPanel({
  data,
  hasFit,
  isLoading,
  isError,
  streams,
}: {
  data: FitMetrics | undefined;
  hasFit: boolean;
  isLoading: boolean;
  isError: boolean;
  streams: ActivityStreamsResponse | undefined;
}) {
  if (!hasFit) return <EmptyBlock icon={Watch} title="Pas de donnees FIT pour cette activite" />;
  if (isLoading) return <LoadingBlock label="Chargement des metriques FIT..." />;
  if (isError || !data) return <EmptyBlock icon={Watch} title="Donnees FIT indisponibles" />;

  const groups = buildFitGroups(data);
  const dynamics = buildDynamicsStreamCards(streams?.streams);

  if (groups.length === 0 && dynamics.length === 0) {
    return <EmptyBlock icon={Watch} title="Aucune metrique FIT exploitable" />;
  }

  return (
    <section className="space-y-4">
      {groups.map((group) => (
        <div key={group.title} className="space-y-2">
          <p className="text-eyebrow">{group.title}</p>
          <div className="grid grid-cols-2 gap-2">
            {group.items.map((item) => (
              <MetricCard
                key={`${group.title}-${item.label}`}
                icon={item.Icon}
                label={item.label}
                value={item.value}
              />
            ))}
          </div>
        </div>
      ))}

      {dynamics.length > 0 ? (
        <div className="space-y-2">
          <p className="text-eyebrow">Running dynamics streams</p>
          <div className="grid grid-cols-2 gap-2">
            {dynamics.map((item) => (
              <MetricCard
                key={item.label}
                icon={item.Icon}
                label={item.label}
                value={item.value}
              />
            ))}
          </div>
        </div>
      ) : null}

      <div className="text-muted-foreground text-xs">
        {data.record_count != null ? `Enregistrements FIT : ${data.record_count}` : null}
        {data.record_count != null && data.fit_downloaded_at ? ' · ' : null}
        {data.fit_downloaded_at
          ? `Import : ${new Date(data.fit_downloaded_at).toLocaleDateString('fr-FR')}`
          : null}
      </div>
    </section>
  );
}

function WeatherPanel({
  data,
  hasWeather,
  isLoading,
  isError,
  isEnriching,
  enrichError,
  onEnrich,
}: {
  data: ActivityWeather | undefined;
  hasWeather: boolean;
  isLoading: boolean;
  isError: boolean;
  isEnriching: boolean;
  enrichError: boolean;
  onEnrich: () => void;
}) {
  if (!hasWeather) {
    return (
      <WeatherEmptyState
        title="Pas de meteo pour cette activite"
        isEnriching={isEnriching}
        enrichError={enrichError}
        onEnrich={onEnrich}
      />
    );
  }
  if (isLoading) return <LoadingBlock label="Chargement de la meteo..." />;
  if (isError || !data) {
    return (
      <WeatherEmptyState
        title="Meteo indisponible"
        isEnriching={isEnriching}
        enrichError={enrichError}
        onEnrich={onEnrich}
      />
    );
  }

  const metrics = buildWeatherMetrics(data);
  const description = weatherDescription(data.weather_code);
  const timeline = buildWeatherTimeline(data);

  if (metrics.length === 0) {
    return (
      <WeatherEmptyState
        title="Aucune metrique meteo exploitable"
        isEnriching={isEnriching}
        enrichError={enrichError}
        onEnrich={onEnrich}
      />
    );
  }

  return (
    <section className="border-border-subtle bg-card rounded-md border p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <p className="text-eyebrow">Meteo activite</p>
          {description ? (
            <p className="text-foreground mt-1 text-lg font-bold">{description}</p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onEnrich}
          disabled={isEnriching}
          className="inline-flex h-9 items-center gap-1.5 rounded-full border border-border-subtle px-3 text-xs font-semibold text-brand-cyan disabled:opacity-50"
        >
          <RefreshCw className={cn('h-3.5 w-3.5', isEnriching && 'animate-spin')} />
          Recalculer
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {metrics.map((metric) => (
          <MetricCard
            key={metric.label}
            icon={metric.Icon}
            label={metric.label}
            value={metric.value}
          />
        ))}
      </div>

      {timeline.length > 0 ? (
        <div className="border-border-subtle mt-4 border-t pt-4">
          <WeatherTimelineChart data={timeline} />
          <div className="max-h-48 overflow-y-auto rounded-md border border-border-subtle">
            {timeline.map((point, index) => (
              <div
                key={`${point.elapsed_min}-${point.timestamp ?? index}`}
                className={cn(
                  'flex items-center justify-between px-3 py-2 text-xs',
                  index < timeline.length - 1 && 'border-border-subtle border-b',
                )}
              >
                <span className="text-muted-foreground">+{formatElapsedMinutes(point.elapsed_min)}</span>
                <span className="text-foreground font-semibold">
                  {point.temperature_c != null ? `${point.temperature_c.toFixed(1)}°C` : '—'}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <p className="text-muted-foreground mt-4 border-t border-border-subtle pt-3 text-xs">
          La timeline 10 min sera disponible apres le prochain import meteo.
        </p>
      )}
    </section>
  );
}

function WeatherEmptyState({
  title,
  isEnriching,
  enrichError,
  onEnrich,
}: {
  title: string;
  isEnriching: boolean;
  enrichError: boolean;
  onEnrich: () => void;
}) {
  return (
    <section className="border-border-subtle bg-card rounded-md border p-4 text-center">
      <CloudSun className="text-muted-foreground mx-auto mb-3 h-8 w-8" />
      <p className="text-foreground text-sm font-semibold">{title}</p>
      <p className="text-muted-foreground mx-auto mt-1 max-w-xs text-xs leading-relaxed">
        La meteo 10 min n'est plus lancee pendant l'import global. Tu peux la calculer pour cette activite seulement.
      </p>
      <button
        type="button"
        onClick={onEnrich}
        disabled={isEnriching}
        className="bg-brand-primary mt-4 inline-flex h-9 items-center justify-center gap-2 rounded-md px-3 text-xs font-semibold text-white disabled:opacity-50"
      >
        <RefreshCw className={cn('h-3.5 w-3.5', isEnriching && 'animate-spin')} />
        {isEnriching ? 'Calcul en cours...' : 'Calculer la meteo'}
      </button>
      {enrichError ? (
        <p className="text-danger mt-2 text-[11px]">
          Calcul impossible pour cette activite.
        </p>
      ) : null}
    </section>
  );
}

function WeatherTimelineChart({ data }: { data: WeatherTimelinePoint[] }) {
  const hasApparent = data.some((point) => point.apparent_temperature_c != null);
  const hasWind = data.some((point) => point.wind_speed_kmh != null);

  return (
    <div className="mb-3 rounded-md border border-border-subtle bg-surface-2 p-3">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <div>
          <p className="text-eyebrow">Graphique meteo</p>
          <p className="text-muted-foreground mt-1 text-[11px]">
            Temperature toutes les 10 min depuis le depart
          </p>
        </div>
        <span className="text-muted-foreground text-[11px]">{data.length} points</span>
      </div>

      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1} initialDimension={{ width: 1, height: 1 }}>
          <AreaChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
            <XAxis
              dataKey="elapsed_min"
              type="number"
              domain={['dataMin', 'dataMax']}
              tickFormatter={(value) => formatElapsedMinutes(Number(value))}
              tick={{ fill: 'var(--muted-foreground)', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              yAxisId="temp"
              domain={['dataMin - 1', 'dataMax + 1']}
              tickFormatter={(value) => `${Number(value).toFixed(0)}°`}
              tick={{ fill: 'var(--muted-foreground)', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              width={28}
            />
            {hasWind ? (
              <YAxis yAxisId="wind" orientation="right" hide domain={['dataMin', 'dataMax']} />
            ) : null}
            <Tooltip
              contentStyle={{
                background: 'var(--surface-2)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 8,
                color: 'var(--foreground)',
              }}
              labelFormatter={(value) => `+${formatElapsedMinutes(Number(value))}`}
              formatter={(value, name) => {
                const numeric = Number(value);
                if (!Number.isFinite(numeric)) return ['—', String(name)];
                if (name === 'Vent') return [`${numeric.toFixed(1)} km/h`, name];
                return [`${numeric.toFixed(1)}°C`, name];
              }}
            />
            <Area
              yAxisId="temp"
              type="monotone"
              dataKey="temperature_c"
              name="Temp."
              stroke="var(--brand-sunset)"
              fill="var(--brand-sunset)"
              fillOpacity={0.18}
              strokeWidth={2}
              connectNulls
            />
            {hasApparent ? (
              <Area
                yAxisId="temp"
                type="monotone"
                dataKey="apparent_temperature_c"
                name="Ressenti"
                stroke="var(--brand-cyan)"
                fill="var(--brand-cyan)"
                fillOpacity={0.08}
                strokeWidth={1.8}
                connectNulls
              />
            ) : null}
            {hasWind ? (
              <Area
                yAxisId="wind"
                type="monotone"
                dataKey="wind_speed_kmh"
                name="Vent"
                stroke="var(--success)"
                fill="var(--success)"
                fillOpacity={0.06}
                strokeWidth={1.5}
                connectNulls
              />
            ) : null}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function MapPanel({
  activity,
  streams,
  isLoading = false,
  onRefresh,
}: {
  activity: EnrichedActivity;
  streams: ActivityStreamsResponse | undefined;
  isLoading?: boolean;
  onRefresh?: () => void;
}) {
  return (
    <section className="border-border-subtle bg-card overflow-hidden rounded-md border">
      <div className="border-border-subtle border-b p-4">
        <p className="text-eyebrow">Carte</p>
        <p className="text-muted-foreground mt-1 text-xs">
          Trace GPS issue des streams ou de la polyline resume.
        </p>
      </div>
      <ActivityRouteMap
        activity={activity}
        streams={streams}
        isLoading={isLoading}
        onRefresh={onRefresh}
      />
    </section>
  );
}

function ActivityRouteMap({
  activity,
  streams,
  isLoading = false,
  onRefresh,
}: {
  activity: EnrichedActivity;
  streams: ActivityStreamsResponse | undefined;
  isLoading?: boolean;
  onRefresh?: () => void;
}) {
  const track = useMemo(() => buildRouteTrack(activity, streams?.streams), [activity, streams?.streams]);

  // On délègue à RouteMapTiler la gestion des états vide / chargement /
  // erreur (spinner pendant le fetch, bouton Réactualiser sinon).
  return (
    <RouteMapTiler
      tracks={track ? [track] : []}
      className="h-72 w-full"
      fallbackLabel="Pas de trace GPS disponible"
      fitPadding={42}
      loading={isLoading}
      onRefresh={onRefresh}
    />
  );
}

function LoadingBlock({ label }: { label: string }) {
  return (
    <div className="border-border-subtle bg-card rounded-md border p-4 text-sm text-muted-foreground">
      {label}
    </div>
  );
}

function EmptyBlock({
  icon: Icon,
  title,
}: {
  icon: LucideIcon;
  title: string;
}) {
  return (
    <div className="border-border-subtle bg-card rounded-md border p-6 text-center">
      <Icon className="text-muted-foreground mx-auto mb-3 h-7 w-7" />
      <p className="text-muted-foreground text-sm">{title}</p>
    </div>
  );
}

function MiniValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-surface-2 rounded-md px-2 py-2">
      <p className="text-muted-foreground text-[10px] uppercase leading-none">{label}</p>
      <p className="text-foreground mt-1 text-xs font-semibold">{value}</p>
    </div>
  );
}

interface StreamPoint {
  km: number;
  altitude?: number | null;
  heartrate?: number | null;
  pace?: number | null;
}

function buildStreamData(streams?: ActivityStreamsResponse['streams']): StreamPoint[] {
  const distance = streamArray<number>(streams?.distance);
  const altitude = streamArray<number>(streams?.altitude);
  const heartrate = streamArray<number>(streams?.heartrate);
  const velocity = streamArray<number>(streams?.velocity_smooth);
  const count = Math.max(distance.length, altitude.length, heartrate.length, velocity.length);
  if (count === 0) return [];

  const step = Math.max(1, Math.floor(count / 120));
  const points: StreamPoint[] = [];

  for (let index = 0; index < count; index += step) {
    const km = distance[index] != null ? Number(distance[index]) / 1000 : index / count;
    const altitudeValue = altitude[index] != null ? Number(altitude[index]) : null;
    const hrValue = heartrate[index] != null ? Number(heartrate[index]) : null;
    const pace = speedToPace(velocity[index] != null ? Number(velocity[index]) : null);

    if (Number.isFinite(km)) {
      points.push({
        km,
        altitude: Number.isFinite(altitudeValue) ? altitudeValue : null,
        heartrate: Number.isFinite(hrValue) ? hrValue : null,
        pace,
      });
    }
  }

  return points;
}

function streamArray<T = number>(stream: unknown): T[] {
  if (Array.isArray(stream)) return stream as T[];
  if (stream && typeof stream === 'object' && Array.isArray((stream as { data?: T[] }).data)) {
    return (stream as { data: T[] }).data;
  }
  return [];
}

function buildRoutePoints(
  activity: EnrichedActivity,
  streams?: ActivityStreamsResponse['streams'],
): [number, number][] {
  const latlng = streamArray<[number, number]>(streams?.latlng)
    // Les streams GPS réels contiennent des trous : certains éléments sont
    // `null`. On valide la paire AVANT de la déstructurer, sinon
    // `const [lat, lng] = null` jette "object null is not iterable".
    .filter(
      (pair): pair is [number, number] =>
        Array.isArray(pair) &&
        Number.isFinite(pair[0]) &&
        Number.isFinite(pair[1]),
    )
    .map(([lat, lng]) => [lng, lat] as [number, number]);
  if (latlng.length > 1) return latlng;

  const encoded = activity.polyline || activity.summary_polyline;
  if (encoded) return decodePolyline(encoded);

  if (activity.start_latlng && activity.end_latlng) {
    return [
      [activity.start_latlng[1], activity.start_latlng[0]],
      [activity.end_latlng[1], activity.end_latlng[0]],
    ];
  }

  return [];
}

function buildRouteTrack(
  activity: EnrichedActivity,
  streams?: ActivityStreamsResponse['streams'],
): RouteMapTrack | null {
  const routePoints = buildRoutePoints(activity, streams);
  if (routePoints.length === 0) return null;
  return {
    id: String(activity.activity_id ?? activity.id ?? 'activity'),
    // Trace = couleur d'action (orange foncé braise), comme les CTA.
    color: actionColor(),
    width: 4,
    points: routePoints.map(([lng, lat]) => ({ lat, lng })),
  };
}


function decodePolyline(encoded: string): [number, number][] {
  let index = 0;
  let lat = 0;
  let lng = 0;
  const points: [number, number][] = [];

  while (index < encoded.length) {
    const latResult = decodePolylineValue(encoded, index);
    lat += latResult.value;
    index = latResult.nextIndex;

    const lngResult = decodePolylineValue(encoded, index);
    lng += lngResult.value;
    index = lngResult.nextIndex;

    points.push([lng / 1e5, lat / 1e5]);
  }

  return points;
}

function decodePolylineValue(encoded: string, startIndex: number): { value: number; nextIndex: number } {
  let result = 0;
  let shift = 0;
  let index = startIndex;

  while (index < encoded.length) {
    const byte = encoded.charCodeAt(index) - 63;
    index += 1;
    result |= (byte & 0x1f) << shift;
    shift += 5;
    if (byte < 0x20) break;
  }

  return {
    value: result & 1 ? ~(result >> 1) : result >> 1,
    nextIndex: index,
  };
}

function hasMapCandidate(activity: EnrichedActivity): boolean {
  return Boolean(activity.polyline || activity.summary_polyline || (activity.start_latlng && activity.end_latlng));
}

function buildFitGroups(data: FitMetrics): Array<{
  title: string;
  items: Array<{ label: string; value: string; Icon: LucideIcon }>;
}> {
  return [
    {
      title: 'Running dynamics',
      items: compactMetrics([
        metric('GCT', data.ground_contact_time_avg, ' ms', Footprints, 0),
        metric('Oscillation', data.vertical_oscillation_avg, ' mm', MoveVertical, 1),
        metric('Equilibre G/D', data.stance_time_balance_avg, '%', ArrowLeftRight, 1),
        metric('Longueur foulee', data.step_length_avg != null ? data.step_length_avg / 10 : null, ' cm', Footprints, 1),
        metric('Ratio vertical', data.vertical_ratio_avg, '%', MoveVertical, 1),
      ]),
    },
    {
      title: 'Puissance et charge',
      items: compactMetrics([
        metric('Puissance moy.', data.power_avg, ' W', Zap, 0),
        metric('Puissance max', data.power_max, ' W', Zap, 0),
        metric('Puissance norm.', data.normalized_power, ' W', Zap, 0),
        metric('TE aerobie', data.aerobic_training_effect, '', Gauge, 1),
        metric('TE anaerobie', data.anaerobic_training_effect, '', Gauge, 1),
      ]),
    },
    {
      title: 'Cardio et cadence',
      items: compactMetrics([
        metric('FC moy.', data.heart_rate_avg, ' bpm', Heart, 0),
        metric('FC max', data.heart_rate_max, ' bpm', Heart, 0),
        metric('Cadence moy.', data.cadence_avg, ' spm', Footprints, 0),
        metric('Cadence max', data.cadence_max, ' spm', Footprints, 0),
      ]),
    },
    {
      title: 'Totaux',
      items: compactMetrics([
        metric('Distance', data.total_distance != null ? data.total_distance / 1000 : null, ' km', Activity, 2),
        metric('Temps actif', data.total_timer_time, ' s', Timer, 0, formatDuration),
        metric('Calories', data.total_calories, ' kcal', Flame, 0),
        metric('D+', data.total_ascent, ' m', Mountain, 0),
        metric('D-', data.total_descent, ' m', Mountain, 0),
      ]),
    },
  ].filter((group) => group.items.length > 0);
}

function compactMetrics(
  values: Array<{ label: string; value: string; Icon: LucideIcon } | null>,
): Array<{ label: string; value: string; Icon: LucideIcon }> {
  return values.filter((item): item is { label: string; value: string; Icon: LucideIcon } => item != null);
}

function metric(
  label: string,
  value: number | null | undefined,
  suffix: string,
  Icon: LucideIcon,
  digits = 0,
  formatter?: (value: number) => string,
): { label: string; value: string; Icon: LucideIcon } | null {
  if (value == null || !Number.isFinite(value)) return null;
  return {
    label,
    value: formatter ? formatter(value) : `${value.toFixed(digits)}${suffix}`,
    Icon,
  };
}

function buildDynamicsStreamCards(streams?: ActivityStreamsResponse['streams']): Array<{
  label: string;
  value: string;
  Icon: LucideIcon;
}> {
  const cards: Array<{ label: string; value: string; Icon: LucideIcon }> = [];
  const gct = average(streamArray<number>(streams?.stance_time));
  const verticalOscillation = average(streamArray<number>(streams?.vertical_oscillation));
  const stepLength = average(streamArray<number>(streams?.step_length));
  const verticalRatio = average(streamArray<number>(streams?.vertical_ratio));

  if (gct != null) cards.push({ label: 'GCT stream', value: `${gct.toFixed(0)} ms`, Icon: Footprints });
  if (verticalOscillation != null) cards.push({ label: 'Oscillation stream', value: `${verticalOscillation.toFixed(1)} mm`, Icon: MoveVertical });
  if (stepLength != null) cards.push({ label: 'Foulee stream', value: `${(stepLength / 10).toFixed(1)} cm`, Icon: Footprints });
  if (verticalRatio != null) cards.push({ label: 'Ratio stream', value: `${verticalRatio.toFixed(1)}%`, Icon: MoveVertical });

  return cards;
}

function average(values: number[]): number | null {
  const valid = values.filter((value) => Number.isFinite(value));
  if (valid.length === 0) return null;
  return valid.reduce((sum, value) => sum + value, 0) / valid.length;
}

function buildWeatherMetrics(weather: ActivityWeather): Array<{
  label: string;
  value: string;
  Icon: LucideIcon;
}> {
  const snapshot = weather.hourly_snapshot ?? {};
  const apparentTemperature = numericSnapshot(snapshot, 'apparent_temperature');
  const dewPoint = numericSnapshot(snapshot, 'dew_point_2m');
  const windGusts = numericSnapshot(snapshot, 'wind_gusts_10m');

  return compactMetrics([
    metric('Temperature', weather.temperature_c, '°C', Thermometer, 1),
    metric('Ressenti', apparentTemperature, '°C', Thermometer, 1),
    metric('Humidite', weather.humidity_pct, '%', Droplets, 0),
    metric('Point rosee', dewPoint, '°C', Droplets, 1),
    weather.wind_speed_kmh != null
      ? {
          label: 'Vent',
          value: `${weather.wind_speed_kmh.toFixed(0)} km/h${weather.wind_direction_deg != null ? ` ${windDirectionLabel(weather.wind_direction_deg)}` : ''}`,
          Icon: Wind,
        }
      : null,
    metric('Rafales', windGusts, ' km/h', Wind, 0),
    metric('Pression', weather.pressure_hpa, ' hPa', Gauge, 0),
    metric('Pluie', weather.precipitation_mm, ' mm', Cloud, 1),
    metric('Nuages', weather.cloud_cover_pct, '%', Cloud, 0),
  ]);
}

interface WeatherTimelinePoint {
  elapsed_min: number;
  timestamp?: string;
  temperature_c: number | null;
  apparent_temperature_c: number | null;
  humidity_pct: number | null;
  wind_speed_kmh: number | null;
  precipitation_mm: number | null;
}

function buildWeatherTimeline(weather: ActivityWeather): WeatherTimelinePoint[] {
  const snapshot = weather.hourly_snapshot ?? {};
  const rawTimeline = snapshot.timeline_10min;
  if (!Array.isArray(rawTimeline)) return [];

  return rawTimeline
    .map((raw): WeatherTimelinePoint | null => {
      if (!raw || typeof raw !== 'object') return null;
      const item = raw as Record<string, unknown>;
      const elapsed = Number(item.elapsed_min);
      if (!Number.isFinite(elapsed)) return null;
      const point: WeatherTimelinePoint = {
        elapsed_min: elapsed,
        temperature_c: optionalTimelineNumber(item.temperature_c),
        apparent_temperature_c: optionalTimelineNumber(item.apparent_temperature_c),
        humidity_pct: optionalTimelineNumber(item.humidity_pct),
        wind_speed_kmh: optionalTimelineNumber(item.wind_speed_kmh),
        precipitation_mm: optionalTimelineNumber(item.precipitation_mm),
      };
      if (typeof item.timestamp === 'string') {
        point.timestamp = item.timestamp;
      }
      return point;
    })
    .filter((item): item is WeatherTimelinePoint => item != null);
}

function optionalTimelineNumber(value: unknown): number | null {
  if (value == null) return null;
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function formatElapsedMinutes(minutes: number): string {
  if (minutes < 60) return `${Math.round(minutes)} min`;
  const hours = Math.floor(minutes / 60);
  const remainder = Math.round(minutes % 60);
  return remainder > 0 ? `${hours}h${String(remainder).padStart(2, '0')}` : `${hours}h`;
}

function numericSnapshot(snapshot: Record<string, unknown>, key: string): number | null {
  const value = snapshot[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function weatherDescription(code: number | null): string | null {
  if (code === null) return null;
  if (code === 0) return 'Ciel clair';
  if (code <= 3) return 'Nuageux';
  if (code >= 45 && code <= 48) return 'Brouillard';
  if (code >= 51 && code <= 57) return 'Bruine';
  if (code >= 61 && code <= 67) return 'Pluie';
  if (code >= 71 && code <= 77) return 'Neige';
  if (code >= 80 && code <= 82) return 'Averses';
  if (code >= 95 && code <= 99) return 'Orage';
  return null;
}

function windDirectionLabel(deg: number): string {
  const dirs = ['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO'];
  return dirs[Math.round(deg / 45) % 8] ?? 'N';
}
