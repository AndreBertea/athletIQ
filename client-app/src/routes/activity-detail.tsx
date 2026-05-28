import { useMemo, useState } from 'react';
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
  MapPin,
  MoreHorizontal,
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

type TabId = 'streams' | 'segments' | 'fit' | 'weather' | 'map';

const TABS: Array<{ id: TabId; label: string; Icon: LucideIcon }> = [
  { id: 'streams', label: 'Streams', Icon: Activity },
  { id: 'segments', label: 'Segments', Icon: BarChart3 },
  { id: 'fit', label: 'FIT', Icon: Watch },
  { id: 'weather', label: 'Meteo', Icon: CloudSun },
  { id: 'map', label: 'Carte', Icon: MapIcon },
];

export default function ActivityDetailRoute() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabId>('streams');
  const [expanded, setExpanded] = useState(false);
  const queryClient = useQueryClient();

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
  const routeTrack = useMemo(
    () => (activity ? buildRouteTrack(activity, streamsQuery.data?.streams) : null),
    [activity, streamsQuery.data?.streams],
  );
  const peakElevation = useMemo(
    () => resolvePeakElevation(streamData, activity),
    [activity, streamData],
  );
  const sport = activity ? getSportPresentation(activity.sport_type) : null;
  const pace = activity ? speedToPace(activity.avg_speed_m_s ?? activity.avg_speed_mps ?? null) : null;
  const weather = weatherEnrich.data ?? weatherQuery.data;

  return (
    <AppShell hideTopBar hideBottomNav disableMainPadding mainClassName="overflow-hidden">
      <div className="relative h-full overflow-hidden bg-[#0f100c]">
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
            />
            <div className="pointer-events-none absolute inset-0 z-[2] bg-gradient-to-b from-[#0a0c08]/45 via-[#0a0c08]/5 to-[#0a0c08]/70" />

            <button
              type="button"
              onClick={() => navigate(-1)}
              className="absolute left-4 top-[max(14px,env(safe-area-inset-top))] z-[8] inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-[#0f100c]/55 px-3 py-2 text-[13px] font-medium text-[#e8dfcf] shadow-lg backdrop-blur-xl"
            >
              <ArrowLeft className="h-4 w-4" />
              Retour
            </button>

            <button
              type="button"
              aria-label="Options activité"
              className="absolute right-5 top-[calc(max(14px,env(safe-area-inset-top))+66px)] z-[6] flex h-9 w-9 items-center justify-center rounded-full text-[#d8cdbc]"
            >
              <MoreHorizontal className="h-6 w-6" />
            </button>

            <div className="absolute left-6 top-[calc(max(14px,env(safe-area-inset-top))+50px)] z-[5]">
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.09em] text-[#e8dfcf]/75">
                Altitude max
              </p>
              <p className="font-display text-[42px] font-medium leading-none tracking-tight text-[#f0e8d8]">
                {peakElevation != null ? Math.round(peakElevation) : '—'}{' '}
                <span className="text-lg font-normal text-[#f0e8d8]/70">m</span>
              </p>
              <p className="mt-2 text-[15px] font-semibold text-brand-primary">
                ▲ {activity.elev_gain_m != null ? Math.round(activity.elev_gain_m) : 0} m D+
              </p>
            </div>

            <section
              onClick={() => {
                if (!expanded) setExpanded(true);
              }}
              className={cn(
                'absolute inset-x-0 bottom-0 z-10 flex flex-col overflow-hidden rounded-t-[28px] bg-[#0d100b]/[0.97] shadow-[0_-16px_48px_rgba(0,0,0,0.55)] transition-[height] duration-[380ms] ease-[cubic-bezier(0.34,1.4,0.64,1)]',
                expanded ? 'h-[82%]' : 'h-[34%]',
              )}
            >
              <div className="flex shrink-0 justify-center pb-1 pt-3">
                <span className="h-1 w-9 rounded-full bg-[#e8dfcf]/20" />
              </div>

              <div className="flex shrink-0 items-start justify-between gap-3 px-6 pt-1">
                <div className="min-w-0">
                  <h1 className="font-display truncate text-base font-bold tracking-tight text-[#f0e8d8]">
                    {activity.name}
                  </h1>
                  <p className="mt-0.5 truncate text-[11px] text-[#e8dfcf]/55">
                    {formatDateLong(activity.start_date_utc)} · {sport?.label ?? activity.sport_type}
                    {pace ? ` · ${formatPace(pace)}` : ''}
                  </p>
                </div>
                {expanded ? (
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      setExpanded(false);
                    }}
                    className="shrink-0 rounded-full bg-[#e8dfcf]/[0.08] px-3 py-1.5 text-[11px] font-medium text-[#e8dfcf]/60"
                  >
                    Réduire ↓
                  </button>
                ) : null}
              </div>

              <div className="grid shrink-0 grid-cols-[1fr_1px_1fr] px-7 pb-3 pt-4">
                <ActivityHeroMetric label="Distance" value={formatDistance(activity.distance_m)} unit="KM" />
                <div className="bg-[#e8dfcf]/10" />
                <ActivityHeroMetric
                  label="D+"
                  value={activity.elev_gain_m != null ? String(Math.round(activity.elev_gain_m)) : '—'}
                  unit="M"
                  align="right"
                />
              </div>

              <div className="shrink-0 px-5 pb-3">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#e8dfcf]/50">
                  Profil d'altitude
                </p>
                <MiniAreaChart
                  data={streamData.map((point) => point.altitude)}
                  color="#A0432E"
                  height={72}
                  className="bg-white/[0.03]"
                />
              </div>

              {expanded ? (
                <div
                  className="flex-1 overflow-y-auto px-6 pb-[calc(24px+env(safe-area-inset-bottom))]"
                  onClick={(event) => event.stopPropagation()}
                >
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
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.07em] text-[#e8dfcf]/45">
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
                                : 'border-white/[0.08] bg-white/[0.04] text-[#e8dfcf]/50',
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
                        <MapPanel activity={activity} streams={streamsQuery.data} />
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
    <div className="flex h-full items-center justify-center bg-[#0f100c] px-8 text-center">
      <div className="rounded-[18px] border border-white/10 bg-[#191815]/80 px-5 py-5 text-[#e8dfcf]/70 shadow-2xl backdrop-blur-xl">
        {Icon ? <Icon className="mx-auto mb-3 h-7 w-7 text-[#e8dfcf]/55" /> : null}
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
      <span className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.07em] text-[#e8dfcf]/55">
        {label}
      </span>
      <strong className="font-display block truncate text-[34px] font-medium leading-none tracking-tight text-[#f0e8d8]">
        {normalizedValue}{' '}
        {normalizedValue !== '—' ? (
          <span className="text-sm font-normal text-[#f0e8d8]/60">{unit}</span>
        ) : null}
      </strong>
    </div>
  );
}

function SheetStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/[0.08] bg-[#e8dfcf]/[0.06] px-2 py-2.5">
      <p className="mb-1.5 truncate text-[9px] font-semibold uppercase tracking-[0.05em] text-[#e8dfcf]/45">
        {label}
      </p>
      <p className="font-display truncate text-[13px] font-bold leading-none text-[#f0e8d8]">
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
      <p className="mb-2.5 text-[11px] font-semibold uppercase tracking-[0.07em] text-[#e8dfcf]/45">
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
                : 'border-white/[0.08] bg-white/[0.04] text-[#a8a192]/50',
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
  const hasAltitude = streamData.some((point) => point.altitude != null);
  const hasHr = streamData.some((point) => point.heartrate != null);
  const hasPace = streamData.some((point) => point.pace != null);

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

      {hasAltitude ? (
        <StreamChart
          title="Altitude"
          data={streamData}
          dataKey="altitude"
          unit="m"
          color="var(--brand-sunset)"
        />
      ) : null}

      {hasHr ? (
        <StreamChart
          title="Frequence cardiaque"
          data={streamData}
          dataKey="heartrate"
          unit="bpm"
          color="var(--danger)"
        />
      ) : null}

      {hasPace ? (
        <StreamChart
          title="Allure"
          data={streamData}
          dataKey="pace"
          unit="min/km"
          color="var(--success)"
        />
      ) : null}

      {!hasAltitude && !hasHr && !hasPace ? (
        <EmptyBlock icon={Activity} title="Streams présents, graphiques à compléter" />
      ) : null}
    </section>
  );
}

function StreamChart({
  title,
  data,
  dataKey,
  unit,
  color,
}: {
  title: string;
  data: StreamPoint[];
  dataKey: keyof StreamPoint;
  unit: string;
  color: string;
}) {
  return (
    <section className="border-border-subtle bg-card rounded-md border p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-eyebrow">{title}</p>
        <span className="text-muted-foreground text-[11px]">{unit}</span>
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
}: {
  activity: EnrichedActivity;
  streams: ActivityStreamsResponse | undefined;
}) {
  return (
    <section className="border-border-subtle bg-card overflow-hidden rounded-md border">
      <div className="border-border-subtle border-b p-4">
        <p className="text-eyebrow">Carte</p>
        <p className="text-muted-foreground mt-1 text-xs">
          Trace GPS issue des streams ou de la polyline resume.
        </p>
      </div>
      <ActivityRouteMap activity={activity} streams={streams} />
    </section>
  );
}

function ActivityRouteMap({
  activity,
  streams,
}: {
  activity: EnrichedActivity;
  streams: ActivityStreamsResponse | undefined;
}) {
  const track = useMemo(() => buildRouteTrack(activity, streams?.streams), [activity, streams?.streams]);

  if (!track) {
    return <EmptyBlock icon={MapPin} title="Pas de trace GPS disponible" />;
  }

  return (
    <RouteMapTiler
      tracks={[track]}
      className="h-72 w-full"
      fallbackLabel="Pas de trace GPS disponible"
      fitPadding={42}
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
    .filter(([lat, lng]) => Number.isFinite(lat) && Number.isFinite(lng))
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
    color: '#A0432E',
    width: 4,
    points: routePoints.map(([lng, lat]) => ({ lat, lng })),
  };
}

function resolvePeakElevation(
  streamData: StreamPoint[],
  activity: EnrichedActivity | undefined,
): number | null {
  const altitudeValues = streamData
    .map((point) => point.altitude)
    .filter((value): value is number => value != null && Number.isFinite(value));
  if (altitudeValues.length > 0) return Math.max(...altitudeValues);
  return activity?.elev_gain_m ?? null;
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
