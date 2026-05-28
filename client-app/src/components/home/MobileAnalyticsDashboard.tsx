import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQueries, useQuery } from '@tanstack/react-query';
import {
  Activity,
  BarChart3,
  Brain,
  Calendar,
  ChevronDown,
  Flame,
  Gauge,
  Heart,
  LineChart as LineChartIcon,
  Moon,
  Scale,
  Thermometer,
  Timer,
  TrendingUp,
  Watch,
  Zap,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  activityDisplayId,
  agonApi,
  type ActivityWeather,
  type EnrichedActivity,
  type EnrichedActivityStats,
  type GarminDailyEntry,
  type TrainingLoadEntry,
} from '@/lib/api/agon';
import { cn } from '@/lib/utils';

type PeriodDays = 7 | 30 | 90 | 180 | 365;
type TimeGranularity = 'day' | 'week' | 'month';
type DashboardTab = 'performance' | 'garmin' | 'sleep' | 'load' | 'insights';
type MetricKey = 'distance' | 'duration' | 'pace' | 'elevation';
type GarminMetricKey =
  | 'hrv_rmssd'
  | 'training_readiness'
  | 'sleep_score'
  | 'stress_score'
  | 'body_battery_max'
  | 'resting_hr';
type LoadModel = 'banister' | 'edwards' | 'comparison';
type IconType = typeof Activity;
type AnalyticsFilterKey = 'period' | 'granularity';

interface StatsSummary {
  totalActivities: number;
  totalDistanceKm: number;
  totalTimeHours: number;
  sportTypes: number;
}

interface PerformancePoint {
  bucketKey: string;
  label: string;
  distance: number;
  duration: number;
  pace: number;
  elevation: number;
  count: number;
}

interface GarminPoint {
  bucketKey: string;
  label: string;
  hrv_rmssd: number | null;
  training_readiness: number | null;
  sleep_score: number | null;
  stress_score: number | null;
  body_battery_max: number | null;
  resting_hr: number | null;
}

interface SleepTrendPoint {
  bucketKey: string;
  label: string;
  sleep_score: number | null;
  deep_min: number;
  light_min: number;
  rem_min: number;
  awake_min: number;
  sleep_duration_min: number | null;
}

interface LoadPoint {
  bucketKey: string;
  label: string;
  chronicLoad: number;
  acuteLoad: number;
  trainingStressBalance: number;
  chronicLoadEdwards: number;
  acuteLoadEdwards: number;
  tsbEdwards: number;
}

const periodOptions: Array<{ value: PeriodDays; label: string }> = [
  { value: 7, label: '7j' },
  { value: 30, label: '30j' },
  { value: 90, label: '3m' },
  { value: 180, label: '6m' },
  { value: 365, label: '1a' },
];

const periodValues = periodOptions.map((option) => option.value);

const granularityOptions: Array<{ value: TimeGranularity; label: string }> = [
  { value: 'day', label: 'Jour' },
  { value: 'week', label: 'Sem.' },
  { value: 'month', label: 'Mois' },
];

const granularityValues = granularityOptions.map((option) => option.value);

const analyticsStorageKeys = {
  period: 'agon.home.analytics.period',
  granularity: 'agon.home.analytics.granularity',
} as const;

const tabOptions: Array<{ value: DashboardTab; label: string; Icon: IconType }> = [
  { value: 'performance', label: 'Performance', Icon: LineChartIcon },
  { value: 'garmin', label: 'Garmin', Icon: Watch },
  { value: 'sleep', label: 'Sommeil', Icon: Moon },
  { value: 'load', label: 'Charge', Icon: Scale },
  { value: 'insights', label: 'Insights', Icon: Brain },
];

const metricConfigByKey: Record<
  MetricKey,
  { label: string; shortLabel: string; color: string; icon: IconType }
> = {
  distance: {
    label: 'Distance',
    shortLabel: 'km',
    color: 'var(--chart-2)',
    icon: Gauge,
  },
  duration: {
    label: 'Duree',
    shortLabel: 'temps',
    color: 'var(--info)',
    icon: Timer,
  },
  pace: {
    label: 'Allure',
    shortLabel: 'min/km',
    color: 'var(--accent-emerald)',
    icon: Activity,
  },
  elevation: {
    label: 'D+',
    shortLabel: 'm',
    color: 'var(--warning)',
    icon: TrendingUp,
  },
};

const garminMetricConfig: Record<GarminMetricKey, { label: string; color: string }> = {
  hrv_rmssd: { label: 'HRV', color: '#8b5cf6' },
  training_readiness: { label: 'Readiness', color: '#f59e0b' },
  sleep_score: { label: 'Sommeil', color: '#3b82f6' },
  stress_score: { label: 'Stress', color: '#ef4444' },
  body_battery_max: { label: 'Body Battery', color: '#22c55e' },
  resting_hr: { label: 'FC repos', color: '#f43f5e' },
};

const garminMetricKeys: GarminMetricKey[] = [
  'hrv_rmssd',
  'training_readiness',
  'sleep_score',
  'stress_score',
  'body_battery_max',
  'resting_hr',
];

const loadSeriesConfig = {
  chronicLoad: { label: 'CTL Banister', color: '#3b82f6' },
  acuteLoad: { label: 'ATL Banister', color: '#f97316' },
  trainingStressBalance: { label: 'TSB Banister', color: '#22c55e' },
  chronicLoadEdwards: { label: 'CTL Edwards', color: '#8b5cf6' },
  acuteLoadEdwards: { label: 'ATL Edwards', color: '#ec4899' },
  tsbEdwards: { label: 'TSB Edwards', color: '#14b8a6' },
};

export function MobileAnalyticsDashboard() {
  const [selectedPeriod, setSelectedPeriod] = useState<PeriodDays>(() =>
    readStoredPeriod(),
  );
  const [selectedMetric, setSelectedMetric] = useState<MetricKey>('distance');
  const [chartGranularity, setChartGranularity] = useState<TimeGranularity>(() =>
    readStoredGranularity(),
  );
  const [activeTab, setActiveTab] = useState<DashboardTab>('performance');
  const [collapsed, setCollapsed] = useState(false);

  const dateFrom = useMemo(() => daysAgoIso(selectedPeriod), [selectedPeriod]);
  const dateTo = useMemo(() => isoDate(new Date()), []);

  useEffect(() => {
    writeStoredValue(analyticsStorageKeys.period, selectedPeriod);
  }, [selectedPeriod]);

  useEffect(() => {
    writeStoredValue(analyticsStorageKeys.granularity, chartGranularity);
  }, [chartGranularity]);

  const enrichedStatsQuery = useQuery({
    queryKey: ['agon', 'home-consolidated-stats', selectedPeriod],
    queryFn: () => agonApi.getEnrichedActivityStats(selectedPeriod),
    staleTime: 5 * 60_000,
  });

  const performanceQuery = useQuery({
    queryKey: ['agon', 'home-performance-activities', selectedPeriod],
    queryFn: () => agonApi.getAllEnrichedActivities({ date_from: dateFrom }),
    staleTime: 5 * 60_000,
  });

  const garminStatusQuery = useQuery({
    queryKey: ['agon', 'home-garmin-status'],
    queryFn: () => agonApi.getGarminStatus(),
    staleTime: 30_000,
  });

  const garminConnected = garminStatusQuery.data?.connected ?? false;

  const garminDailyQuery = useQuery({
    queryKey: ['agon', 'home-garmin-daily', selectedPeriod],
    queryFn: () => agonApi.getGarminDaily(dateFrom, dateTo),
    staleTime: 5 * 60_000,
    enabled: garminConnected,
  });

  const trainingLoadQuery = useQuery({
    queryKey: ['agon', 'home-training-load', selectedPeriod],
    queryFn: () => agonApi.getTrainingLoad(dateFrom, dateTo),
    staleTime: 10 * 60_000,
  });

  const consolidatedActivities = useMemo(
    () => performanceQuery.data ?? [],
    [performanceQuery.data],
  );

  const weatherActivities = useMemo(
    () =>
      consolidatedActivities
        .filter((activity) => activity.has_weather === true)
        .slice(0, 40),
    [consolidatedActivities],
  );

  const weatherQueries = useQueries({
    queries: weatherActivities.map((activity) => {
      const activityId = activityDisplayId(activity);
      return {
        queryKey: ['agon', 'home-weather', activityId],
        queryFn: () => agonApi.getActivityWeather(activityId),
        staleTime: 30 * 60_000,
        retry: false,
        enabled: activity.has_weather === true,
      };
    }),
  });

  const weatherMap = useMemo(() => {
    const map = new Map<string, ActivityWeather>();
    weatherActivities.forEach((activity, index) => {
      const weather = weatherQueries[index]?.data;
      if (weather) {
        map.set(String(activity.activity_id), weather);
      }
    });
    return map;
  }, [weatherActivities, weatherQueries]);

  const statsSummary = useMemo(
    () => buildStatsSummary(enrichedStatsQuery.data, consolidatedActivities),
    [enrichedStatsQuery.data, consolidatedActivities],
  );

  const performanceData = useMemo(
    () => buildPerformanceData(consolidatedActivities, chartGranularity),
    [consolidatedActivities, chartGranularity],
  );

  const periodLabel =
    periodOptions.find((period) => period.value === selectedPeriod)?.label ??
    `${selectedPeriod}j`;
  const garminDaily = garminDailyQuery.data ?? [];
  const trainingLoad = trainingLoadQuery.data ?? [];

  return (
    <section className="space-y-3">
      <div className="relative z-20 flex items-center justify-between gap-3">
        <p className="text-eyebrow">Analytics</p>
        <div className="flex items-center gap-1.5">
          <AnalyticsControls
            selectedPeriod={selectedPeriod}
            onPeriodChange={setSelectedPeriod}
            granularity={chartGranularity}
            onGranularityChange={setChartGranularity}
          />
          <button
            type="button"
            aria-label={collapsed ? 'Afficher analytics' : 'Masquer analytics'}
            aria-expanded={!collapsed}
            onClick={() => setCollapsed((value) => !value)}
            className="flex h-7 w-7 items-center justify-center rounded-full border border-border-subtle bg-card text-muted-foreground transition active:bg-[var(--active-overlay)]"
          >
            <ChevronDown
              className={cn(
                'h-3.5 w-3.5 transition-transform',
                collapsed && '-rotate-90',
              )}
            />
          </button>
        </div>
      </div>

      <SectionTabs activeTab={activeTab} onChange={setActiveTab} />

      {collapsed ? null : (
        <div className="space-y-3">
          <GlobalStatsGrid
            summary={statsSummary}
            loading={enrichedStatsQuery.isLoading && !performanceQuery.data}
            periodLabel={periodLabel}
          />

          {activeTab === 'performance' ? (
            <PerformancePanel
              data={performanceData}
              loading={performanceQuery.isLoading}
              selectedMetric={selectedMetric}
              onMetricChange={setSelectedMetric}
              granularity={chartGranularity}
            />
          ) : null}

          {activeTab === 'garmin' ? (
            <GarminPanel
              data={garminDaily}
              loading={garminDailyQuery.isLoading}
              connected={garminConnected}
              granularity={chartGranularity}
              periodLabel={periodLabel}
            />
          ) : null}

          {activeTab === 'sleep' ? (
            <SleepPanel
              data={garminDaily}
              loading={garminDailyQuery.isLoading}
              connected={garminConnected}
              granularity={chartGranularity}
              periodLabel={periodLabel}
            />
          ) : null}

          {activeTab === 'load' ? (
            <TrainingLoadPanel
              data={trainingLoad}
              loading={trainingLoadQuery.isLoading}
              granularity={chartGranularity}
            />
          ) : null}

          {activeTab === 'insights' ? (
            <InsightsPanel
              activities={consolidatedActivities}
              garminDaily={garminDaily}
              weatherMap={weatherMap}
              trainingLoad={trainingLoad}
            />
          ) : null}
        </div>
      )}
    </section>
  );
}

function AnalyticsControls({
  selectedPeriod,
  onPeriodChange,
  granularity,
  onGranularityChange,
}: {
  selectedPeriod: PeriodDays;
  onPeriodChange: (period: PeriodDays) => void;
  granularity: TimeGranularity;
  onGranularityChange: (granularity: TimeGranularity) => void;
}) {
  const [openFilter, setOpenFilter] = useState<AnalyticsFilterKey | null>(null);

  const toggleFilter = (filter: AnalyticsFilterKey) => {
    setOpenFilter((current) => (current === filter ? null : filter));
  };

  return (
    <div className="flex shrink-0 items-center gap-1.5">
      <CompactFilterControl
        label="Durée"
        value={selectedPeriod}
        options={periodOptions}
        open={openFilter === 'period'}
        onToggle={() => toggleFilter('period')}
        onChange={(value) => {
          onPeriodChange(value);
          setOpenFilter(null);
        }}
      />
      <CompactFilterControl
        label="Détail"
        value={granularity}
        options={granularityOptions}
        open={openFilter === 'granularity'}
        onToggle={() => toggleFilter('granularity')}
        onChange={(value) => {
          onGranularityChange(value);
          setOpenFilter(null);
        }}
      />
    </div>
  );
}

function CompactFilterControl<T extends string | number>({
  label,
  value,
  options,
  open,
  onToggle,
  onChange,
}: {
  label: string;
  value: T;
  options: Array<{ value: T; label: string }>;
  open: boolean;
  onToggle: () => void;
  onChange: (value: T) => void;
}) {
  const selectedIndex = Math.max(
    0,
    options.findIndex((option) => option.value === value),
  );
  const selectedLabel = options[selectedIndex]?.label ?? String(value);

  return (
    <div className="relative w-[72px]">
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        className={cn(
          'flex h-7 w-full items-center justify-between gap-1 rounded-full border border-border-subtle bg-card px-2 text-left transition active:bg-[var(--active-overlay)]',
          open && 'border-brand-cyan/40 bg-brand-cyan/10 text-brand-cyan',
        )}
      >
        <span className="text-[8px] font-semibold uppercase text-muted-foreground">
          {label}
        </span>
        <span className="text-[11px] font-bold text-foreground">{selectedLabel}</span>
      </button>

      {open ? (
        <div className="bg-card/95 absolute right-0 top-8 z-30 w-[96px] rounded-md border border-border-subtle p-1 shadow-lg backdrop-blur">
          <div className="max-h-[148px] snap-y snap-mandatory overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {options.map((option) => (
              <button
                key={String(option.value)}
                type="button"
                onClick={() => onChange(option.value)}
                className={cn(
                  'block h-7 w-full snap-center rounded-md px-2 text-left text-xs font-semibold transition',
                  option.value === value
                    ? 'bg-brand-cyan/15 text-brand-cyan'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function SegmentButton({
  active,
  onClick,
  children,
  compact = false,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
  compact?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'shrink-0 rounded-md border px-3 text-xs font-semibold transition',
        compact ? 'h-8' : 'h-9',
        active
          ? 'border-brand-cyan/50 bg-brand-cyan/15 text-brand-cyan'
          : 'border-border-subtle bg-card text-muted-foreground hover:text-foreground',
      )}
    >
      {children}
    </button>
  );
}

function GlobalStatsGrid({
  summary,
  loading,
  periodLabel,
}: {
  summary: StatsSummary;
  loading: boolean;
  periodLabel: string;
}) {
  const cards: Array<{
    label: string;
    value: string;
    unit: string;
    Icon: IconType;
  }> = [
    {
      label: 'Activités',
      value: String(summary.totalActivities),
      unit: periodLabel,
      Icon: Activity,
    },
    {
      label: 'Distance',
      value: formatCompactNumber(summary.totalDistanceKm),
      unit: 'km',
      Icon: Gauge,
    },
    {
      label: 'Temps total',
      value: formatHours(summary.totalTimeHours),
      unit: '',
      Icon: Timer,
    },
    {
      label: 'Sports',
      value: String(summary.sportTypes),
      unit: summary.sportTypes > 1 ? 'types' : 'type',
      Icon: Flame,
    },
  ];

  return (
    <div>
      <div className="mb-2">
        <p className="text-eyebrow">Stats globales</p>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {cards.map((card) => (
          <KpiTile
            key={card.label}
            label={card.label}
            value={loading ? '...' : card.value}
            unit={card.unit}
            Icon={card.Icon}
          />
        ))}
      </div>
    </div>
  );
}

function SectionTabs({
  activeTab,
  onChange,
}: {
  activeTab: DashboardTab;
  onChange: (tab: DashboardTab) => void;
}) {
  return (
    <div className="flex gap-1 overflow-x-auto rounded-md border border-border-subtle bg-card p-1">
      {tabOptions.map(({ value, label, Icon }) => (
        <button
          key={value}
          type="button"
          onClick={() => onChange(value)}
          className={cn(
            'flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2.5 text-[11px] font-semibold transition',
            activeTab === value
              ? 'bg-brand-cyan/15 text-brand-cyan'
              : 'text-muted-foreground',
          )}
        >
          <Icon className="h-3.5 w-3.5" />
          {label}
        </button>
      ))}
    </div>
  );
}

function KpiTile({
  label,
  value,
  unit,
  Icon,
  tone = 'brand',
}: {
  label: string;
  value: string;
  unit?: string;
  Icon: IconType;
  tone?: 'brand' | 'blue' | 'green' | 'rose' | 'violet' | 'amber';
}) {
  const toneClasses: Record<
    NonNullable<Parameters<typeof KpiTile>[0]['tone']>,
    string
  > = {
    brand: 'bg-brand-cyan/10 text-brand-cyan border-brand-cyan/20',
    blue: 'border-[var(--tone-blue-bd)] bg-[var(--tone-blue-bg)] text-[var(--tone-blue-fg)]',
    green: 'border-[var(--tone-emerald-bd)] bg-[var(--tone-emerald-bg)] text-[var(--tone-emerald-fg)]',
    rose: 'border-[var(--tone-rose-bd)] bg-[var(--tone-rose-bg)] text-[var(--tone-rose-fg)]',
    violet: 'border-[var(--tone-violet-bd)] bg-[var(--tone-violet-bg)] text-[var(--tone-violet-fg)]',
    amber: 'border-[var(--tone-amber-bd)] bg-[var(--tone-amber-bg)] text-[var(--tone-amber-fg)]',
  };

  return (
    <div className="rounded-md border border-border-subtle bg-card p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase text-muted-foreground">
          {label}
        </p>
        <span className={cn('rounded-md border p-1.5', toneClasses[tone])}>
          <Icon className="h-3.5 w-3.5" />
        </span>
      </div>
      <div className="mt-2 flex items-baseline gap-1">
        <p className="font-display text-[22px] font-bold leading-none text-foreground">
          {value}
        </p>
        {unit ? (
          <span className="text-[11px] font-medium text-muted-foreground">{unit}</span>
        ) : null}
      </div>
    </div>
  );
}

function PerformancePanel({
  data,
  loading,
  selectedMetric,
  onMetricChange,
  granularity,
}: {
  data: PerformancePoint[];
  loading: boolean;
  selectedMetric: MetricKey;
  onMetricChange: (metric: MetricKey) => void;
  granularity: TimeGranularity;
}) {
  const metric = metricConfigByKey[selectedMetric];
  const MetricIcon = metric.icon;

  return (
    <div className="space-y-3">
      <PanelHeader
        title="Évolution des performances"
        subtitle={`Toutes les activités - ${granularityLabel(granularity)}`}
        Icon={MetricIcon}
      />

      <div className="grid grid-cols-4 gap-1.5">
        {(Object.keys(metricConfigByKey) as MetricKey[]).map((key) => {
          const option = metricConfigByKey[key];
          return (
            <button
              key={key}
              type="button"
              onClick={() => onMetricChange(key)}
              className={cn(
                'rounded-full border px-2 py-1.5 text-[10px] font-semibold transition',
                selectedMetric === key
                  ? 'border-brand-cyan/50 bg-brand-cyan/15 text-brand-cyan'
                  : 'border-border-subtle bg-card text-muted-foreground',
              )}
            >
              {option.label}
            </button>
          );
        })}
      </div>

      <ChartFrame loading={loading} empty={data.length === 0}>
        <ResponsiveContainer
          width="100%"
          height="100%"
          minWidth={1}
          minHeight={1}
          initialDimension={{ width: 1, height: 1 }}
        >
          <AreaChart data={data} margin={{ top: 12, right: 10, bottom: 0, left: -24 }}>
            <defs>
              <linearGradient id="performance-area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={metric.color} stopOpacity={0.34} />
                <stop offset="100%" stopColor={metric.color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={chartTickStyle}
              tickLine={false}
              axisLine={false}
              minTickGap={18}
            />
            <YAxis
              tick={chartTickStyle}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value: number) => formatAxisValue(selectedMetric, value)}
            />
            <Tooltip
              cursor={{ stroke: 'var(--chart-cursor)' }}
              contentStyle={tooltipStyle}
              labelStyle={tooltipLabelStyle}
              formatter={(value: unknown) =>
                formatMetricValue(selectedMetric, toNumber(value))
              }
            />
            <Area
              type="monotone"
              dataKey={selectedMetric}
              stroke={metric.color}
              strokeWidth={2.5}
              fill="url(#performance-area)"
              isAnimationActive={false}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </ChartFrame>
    </div>
  );
}

function GarminPanel({
  data,
  loading,
  connected,
  granularity,
  periodLabel,
}: {
  data: GarminDailyEntry[];
  loading: boolean;
  connected: boolean;
  granularity: TimeGranularity;
  periodLabel: string;
}) {
  const [visibleMetrics, setVisibleMetrics] = useState<GarminMetricKey[]>([
    'hrv_rmssd',
    'training_readiness',
    'sleep_score',
  ]);

  const ordered = useMemo(() => sortGarminDaily(data), [data]);
  const summary = useMemo(() => summarizeGarminDaily(ordered), [ordered]);
  const chartData = useMemo(
    () => aggregateGarminDaily(ordered, granularity),
    [ordered, granularity],
  );

  if (!connected) {
    return (
      <EmptyPanel
        Icon={Watch}
        title="Garmin non connecte"
        text="HRV, sommeil, readiness et Body Battery seront visibles apres synchronisation."
      />
    );
  }

  const toggleMetric = (key: GarminMetricKey) => {
    setVisibleMetrics((current) => {
      if (current.includes(key)) {
        return current.length > 1 ? current.filter((item) => item !== key) : current;
      }
      return [...current, key];
    });
  };

  return (
    <div className="space-y-3">
      <PanelHeader
        title="Garmin Daily"
        subtitle={`Periode ${periodLabel}`}
        Icon={Watch}
      />

      <div className="grid grid-cols-2 gap-2">
        <KpiTile
          label="HRV moyenne"
          value={formatNullable(summary.hrvAvg, 0)}
          unit="ms"
          Icon={Heart}
          tone="violet"
        />
        <KpiTile
          label="Readiness"
          value={formatNullable(summary.readinessAvg, 0)}
          Icon={Brain}
          tone="amber"
        />
        <KpiTile
          label="Sleep Score"
          value={formatNullable(summary.sleepScoreAvg, 0)}
          Icon={Moon}
          tone="blue"
        />
        <KpiTile
          label="FC repos"
          value={formatNullable(summary.restingHrAvg, 0)}
          unit={
            summary.latestRestingHr == null
              ? 'bpm'
              : `dern. ${Math.round(summary.latestRestingHr)}`
          }
          Icon={Activity}
          tone="rose"
        />
        {summary.latestVo2max != null ? (
          <KpiTile
            label="VO2max"
            value={summary.latestVo2max.toFixed(0)}
            unit="ml/kg/min"
            Icon={Gauge}
            tone="green"
          />
        ) : null}
        {summary.latestWeightKg != null ? (
          <KpiTile
            label="Poids"
            value={summary.latestWeightKg.toFixed(1)}
            unit="kg"
            Icon={Scale}
            tone="brand"
          />
        ) : null}
      </div>

      <div className="flex flex-wrap gap-1.5">
        <InfoPill label="Status" value={summary.trainingStatus ?? '--'} tone="green" />
        <InfoPill
          label="SpO2"
          value={summary.latestSpo2 == null ? '--' : `${Math.round(summary.latestSpo2)}%`}
          tone="blue"
        />
        <InfoPill
          label="Body Battery"
          value={
            summary.bodyBatteryMin == null || summary.bodyBatteryMax == null
              ? '--'
              : `${Math.round(summary.bodyBatteryMin)} -> ${Math.round(summary.bodyBatteryMax)}`
          }
          tone="amber"
        />
      </div>

      <div className="flex flex-wrap gap-1.5">
        {garminMetricKeys.map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => toggleMetric(key)}
            className={cn(
              'rounded-full border px-2.5 py-1 text-[11px] font-semibold',
              visibleMetrics.includes(key)
                ? 'border-brand-cyan/40 bg-brand-cyan/15 text-brand-cyan'
                : 'border-border-subtle bg-card text-muted-foreground',
            )}
          >
            {garminMetricConfig[key].label}
          </button>
        ))}
      </div>

      <ChartFrame loading={loading} empty={chartData.length === 0}>
        <ResponsiveContainer
          width="100%"
          height="100%"
          minWidth={1}
          minHeight={1}
          initialDimension={{ width: 1, height: 1 }}
        >
          <LineChart
            data={chartData}
            margin={{ top: 12, right: 10, bottom: 0, left: -24 }}
          >
            <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={chartTickStyle}
              tickLine={false}
              axisLine={false}
              minTickGap={18}
            />
            <YAxis tick={chartTickStyle} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} />
            {visibleMetrics.map((key) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                name={garminMetricConfig[key].label}
                stroke={garminMetricConfig[key].color}
                strokeWidth={2.2}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </ChartFrame>
    </div>
  );
}

function SleepPanel({
  data,
  loading,
  connected,
  granularity,
  periodLabel,
}: {
  data: GarminDailyEntry[];
  loading: boolean;
  connected: boolean;
  granularity: TimeGranularity;
  periodLabel: string;
}) {
  const ordered = useMemo(() => sortGarminDaily(data), [data]);
  const summary = useMemo(() => summarizeSleep(ordered), [ordered]);
  const trendData = useMemo(
    () => aggregateSleepTrend(ordered, granularity),
    [ordered, granularity],
  );
  const latestPhases = summary.latest ? sleepPhases(summary.latest) : [];

  if (!connected) {
    return (
      <EmptyPanel
        Icon={Moon}
        title="Sommeil Garmin indisponible"
        text="Connecte Garmin pour afficher score, phases et tendances."
      />
    );
  }

  return (
    <div className="space-y-3">
      <PanelHeader
        title="Sommeil Garmin"
        subtitle={`Periode ${periodLabel}`}
        Icon={Moon}
      />

      <div className="grid grid-cols-3 gap-2">
        <KpiTile
          label="Score moy."
          value={formatNullable(summary.avgScore, 0)}
          Icon={Moon}
          tone="blue"
        />
        <KpiTile
          label="Duree moy."
          value={
            summary.avgDurationMin == null ? '--' : formatMinutes(summary.avgDurationMin)
          }
          Icon={Timer}
          tone="violet"
        />
        <KpiTile
          label="Nuits"
          value={String(summary.nightsCount)}
          Icon={Calendar}
          tone="brand"
        />
      </div>

      {summary.latest ? (
        <div className="rounded-md border border-border-subtle bg-card p-3">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase text-muted-foreground">
                Derniere nuit
              </p>
              <p className="mt-1 text-sm font-semibold text-foreground">
                Score {formatNullable(summary.latest.sleep_score, 0)}
              </p>
            </div>
            <span className="font-display text-2xl font-bold text-brand-cyan">
              {summary.latest.sleep_duration_min == null
                ? '--'
                : formatMinutes(summary.latest.sleep_duration_min)}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <DataLine
              label="Coucher"
              value={formatClock(summary.latest.sleep_start_time)}
            />
            <DataLine label="Reveil" value={formatClock(summary.latest.sleep_end_time)} />
            <DataLine
              label="Respiration"
              value={
                summary.latest.average_respiration == null
                  ? '--'
                  : summary.latest.average_respiration.toFixed(1)
              }
            />
            <DataLine
              label="Stress"
              value={
                summary.latest.avg_sleep_stress == null
                  ? '--'
                  : summary.latest.avg_sleep_stress.toFixed(0)
              }
            />
            <DataLine
              label="SpO2"
              value={
                summary.latest.spo2 == null ? '--' : `${Math.round(summary.latest.spo2)}%`
              }
            />
          </div>

          <div className="mt-3 space-y-2">
            {latestPhases.map((phase) => (
              <div key={phase.key}>
                <div className="mb-1 flex items-center justify-between text-[11px]">
                  <span className="text-muted-foreground">{phase.label}</span>
                  <span className="font-semibold text-foreground">
                    {formatSeconds(phase.seconds)} - {phase.percent.toFixed(0)}%
                  </span>
                </div>
                <div className="bg-surface-3 h-1.5 overflow-hidden rounded-full">
                  <div
                    className={cn('h-full rounded-full', phase.className)}
                    style={{ width: `${phase.percent}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <EmptyPanel
          Icon={Moon}
          title="Aucune nuit"
          text="Pas de donnees sommeil sur cette periode."
          compact
        />
      )}

      <ChartFrame loading={loading} empty={trendData.length === 0}>
        <ResponsiveContainer
          width="100%"
          height="100%"
          minWidth={1}
          minHeight={1}
          initialDimension={{ width: 1, height: 1 }}
        >
          <ComposedChart
            data={trendData}
            margin={{ top: 12, right: 10, bottom: 0, left: -24 }}
          >
            <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={chartTickStyle}
              tickLine={false}
              axisLine={false}
              minTickGap={18}
            />
            <YAxis
              yAxisId="left"
              tick={chartTickStyle}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value: number) => `${Math.round(value / 60)}h`}
            />
            <YAxis yAxisId="right" orientation="right" domain={[0, 100]} hide />
            <Tooltip contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} />
            <Bar
              yAxisId="left"
              dataKey="deep_min"
              name="Profond"
              stackId="sleep"
              fill="#4338ca"
              isAnimationActive={false}
            />
            <Bar
              yAxisId="left"
              dataKey="light_min"
              name="Leger"
              stackId="sleep"
              fill="#60a5fa"
              isAnimationActive={false}
            />
            <Bar
              yAxisId="left"
              dataKey="rem_min"
              name="REM"
              stackId="sleep"
              fill="#a78bfa"
              isAnimationActive={false}
            />
            <Bar
              yAxisId="left"
              dataKey="awake_min"
              name="Eveille"
              stackId="sleep"
              fill="#9ca3af"
              isAnimationActive={false}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="sleep_score"
              name="Score"
              stroke="#f59e0b"
              strokeWidth={2.4}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartFrame>
    </div>
  );
}

function TrainingLoadPanel({
  data,
  loading,
  granularity,
}: {
  data: TrainingLoadEntry[];
  loading: boolean;
  granularity: TimeGranularity;
}) {
  const [model, setModel] = useState<LoadModel>('banister');
  const points = useMemo(
    () => aggregateTrainingLoad(data, granularity),
    [data, granularity],
  );
  const latest = lastOf(points);
  const previous = points.length > 1 ? (points[points.length - 2] ?? null) : null;
  const latestRaw = useMemo(() => lastWithRhr(data), [data]);
  const series = loadSeriesForModel(model);

  if (!loading && points.length === 0) {
    return (
      <EmptyPanel
        Icon={Scale}
        title="Charge indisponible"
        text="Au moins quelques jours de training-load sont necessaires."
      />
    );
  }

  const metrics = latest ? loadMetrics(latest, previous, model) : null;
  const status = metrics ? tsbStatus(metrics.tsb) : null;

  return (
    <div className="space-y-3">
      <PanelHeader
        title="Charge d'entrainement"
        subtitle={granularityLabel(granularity)}
        Icon={Scale}
      />

      <div className="grid grid-cols-3 gap-1.5">
        {(['banister', 'edwards', 'comparison'] as LoadModel[]).map((option) => (
          <SegmentButton
            key={option}
            active={model === option}
            onClick={() => setModel(option)}
            compact
          >
            {option === 'comparison' ? 'Compar.' : capitalize(option)}
          </SegmentButton>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <KpiTile
          label="Fitness 42j"
          value={metrics ? formatCompactNumber(metrics.ctl) : '--'}
          Icon={TrendingUp}
          tone="blue"
        />
        <KpiTile
          label="Fatigue 7j"
          value={metrics ? formatCompactNumber(metrics.atl) : '--'}
          Icon={Zap}
          tone="amber"
        />
        <KpiTile
          label="Forme TSB"
          value={metrics ? formatSigned(metrics.tsb, 1) : '--'}
          Icon={Scale}
          tone={status?.tone === 'red' ? 'rose' : (status?.tone ?? 'green')}
        />
        <KpiTile
          label="Delta RHR 7j"
          value={
            latestRaw?.rhr_delta_7d == null
              ? '--'
              : formatSigned(latestRaw.rhr_delta_7d, 0)
          }
          unit="bpm"
          Icon={Heart}
          tone={rhrTone(latestRaw?.rhr_delta_7d)}
        />
      </div>

      {status ? (
        <div className="flex items-start gap-2 rounded-md border border-border-subtle bg-card p-3">
          <span className={cn('mt-1 h-2.5 w-2.5 rounded-full', status.dot)} />
          <div>
            <p className={cn('text-sm font-semibold', status.textClass)}>
              {status.label}
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {status.recommendation}
            </p>
          </div>
        </div>
      ) : null}

      <ChartFrame loading={loading} empty={points.length === 0}>
        <ResponsiveContainer
          width="100%"
          height="100%"
          minWidth={1}
          minHeight={1}
          initialDimension={{ width: 1, height: 1 }}
        >
          <LineChart data={points} margin={{ top: 12, right: 10, bottom: 0, left: -24 }}>
            <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={chartTickStyle}
              tickLine={false}
              axisLine={false}
              minTickGap={18}
            />
            <YAxis tick={chartTickStyle} tickLine={false} axisLine={false} />
            <ReferenceLine y={0} stroke="var(--chart-ref)" strokeDasharray="4 4" />
            <Tooltip contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} />
            {series.map((key) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                name={loadSeriesConfig[key].label}
                stroke={loadSeriesConfig[key].color}
                strokeWidth={2.1}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </ChartFrame>
    </div>
  );
}

function InsightsPanel({
  activities,
  garminDaily,
  weatherMap,
  trainingLoad,
}: {
  activities: EnrichedActivity[];
  garminDaily: GarminDailyEntry[];
  weatherMap: Map<string, ActivityWeather>;
  trainingLoad: TrainingLoadEntry[];
}) {
  const orderedGarmin = useMemo(() => sortGarminDaily(garminDaily), [garminDaily]);
  const garminMap = useMemo(() => buildGarminMap(orderedGarmin), [orderedGarmin]);
  const weatherHr = useMemo(
    () => computeWeatherHr(activities, weatherMap),
    [activities, weatherMap],
  );
  const sleepLoad = useMemo(
    () => computeSleepLoad(activities, orderedGarmin),
    [activities, orderedGarmin],
  );
  const hrvPerf = useMemo(
    () => computeHrvPerformance(activities, garminMap),
    [activities, garminMap],
  );
  const volumeTrend = useMemo(() => computeVolumeTrend(activities), [activities]);
  const bestDay = useMemo(() => computeBestDay(activities), [activities]);
  const tsbZone = useMemo(() => computeTsbZone(trainingLoad), [trainingLoad]);

  return (
    <div className="space-y-3">
      <PanelHeader title="Insights" subtitle="Correler sans surcharger" Icon={Brain} />

      <InsightTile title="Meteo -> FC" Icon={Thermometer} tone="amber">
        {weatherHr.hasData ? (
          <div className="space-y-2">
            <MiniMetricRow
              label="<10C"
              value={weatherHr.cold?.avgHr ?? null}
              max={weatherHr.maxHr}
              unit="bpm"
            />
            <MiniMetricRow
              label="10-20C"
              value={weatherHr.mild?.avgHr ?? null}
              max={weatherHr.maxHr}
              unit="bpm"
            />
            <MiniMetricRow
              label=">20C"
              value={weatherHr.hot?.avgHr ?? null}
              max={weatherHr.maxHr}
              unit="bpm"
            />
            <p className="text-xs text-muted-foreground">
              Delta chaleur:{' '}
              {weatherHr.heatDelta == null ? '--' : formatSigned(weatherHr.heatDelta, 0)}{' '}
              bpm
            </p>
          </div>
        ) : (
          <SmallEmpty text="Pas assez de donnees meteo + FC." />
        )}
      </InsightTile>

      <InsightTile title="Sommeil -> Charge" Icon={Moon} tone="blue">
        {sleepLoad.hasData && sleepLoad.state ? (
          <div className="space-y-1.5">
            <StatusLine label={sleepLoad.stateLabel} tone={sleepLoad.tone} />
            <p className="text-xs text-muted-foreground">
              Sleep score moy.:{' '}
              <strong className="text-foreground">
                {sleepLoad.avgSleep7d?.toFixed(0)}
              </strong>{' '}
              - Activites 7j:{' '}
              <strong className="text-foreground">{sleepLoad.activityCount7d}</strong>
            </p>
            <p className="text-xs text-muted-foreground">{sleepLoad.recommendation}</p>
          </div>
        ) : (
          <SmallEmpty text="Minimum 7 jours Garmin requis." />
        )}
      </InsightTile>

      <InsightTile title="HRV -> Performance" Icon={Heart} tone="violet">
        {hrvPerf.hasData ? (
          <div className="space-y-1.5">
            <StatusLine label={hrvPerf.label} tone={hrvPerf.tone} />
            <p className="text-xs text-muted-foreground">
              Delta:{' '}
              <strong className="text-foreground">
                {hrvPerf.diffPct == null ? '--' : `${formatSigned(hrvPerf.diffPct, 1)}%`}
              </strong>
            </p>
            <p className="text-xs text-muted-foreground">{hrvPerf.recommendation}</p>
          </div>
        ) : (
          <SmallEmpty text="Pas assez de paires HRV J-1 + allure." />
        )}
      </InsightTile>

      <InsightTile title="Volume hebdo" Icon={BarChart3} tone="blue">
        {volumeTrend.hasData ? (
          <div className="space-y-2">
            {volumeTrend.weeks.map((week) => (
              <MiniMetricRow
                key={week.label}
                label={week.label}
                value={week.distanceKm}
                max={volumeTrend.maxKm}
                unit="km"
                count={week.count}
              />
            ))}
            <p className="text-xs text-muted-foreground">
              vs semaine precedente:{' '}
              {volumeTrend.currentVsPrevPct == null
                ? '--'
                : `${formatSigned(volumeTrend.currentVsPrevPct, 1)}%`}
            </p>
          </div>
        ) : (
          <SmallEmpty text="Pas assez d'activites recentes." />
        )}
      </InsightTile>

      <InsightTile title="Meilleur jour" Icon={Calendar} tone="green">
        {bestDay.hasData && bestDay.bestDay ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold text-foreground">{bestDay.bestDay}</span>
              <span className="text-xs text-muted-foreground">
                {bestDay.bestPace == null ? '--' : `${formatPace(bestDay.bestPace)} /km`}
              </span>
            </div>
            <div className="grid grid-cols-7 gap-1">
              {bestDay.days.map((day) => (
                <div
                  key={day.day}
                  className={cn(
                    'rounded-md border px-1 py-1 text-center text-[10px]',
                    day.day === bestDay.bestDay
                      ? 'border-brand-cyan/40 bg-brand-cyan/15 text-brand-cyan'
                      : 'bg-surface-2 border-border-subtle text-muted-foreground',
                  )}
                >
                  <div>{day.day}</div>
                  <div>{day.avgPace == null ? '--' : formatPace(day.avgPace)}</div>
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              Moyenne globale:{' '}
              {bestDay.globalAvgPace == null ? '--' : formatPace(bestDay.globalAvgPace)}{' '}
              /km
            </p>
          </div>
        ) : (
          <SmallEmpty text="Minimum 5 activites avec allure." />
        )}
      </InsightTile>

      <InsightTile title="Forme TSB" Icon={Zap} tone="amber">
        {tsbZone.hasData && tsbZone.zone ? (
          <div className="space-y-1.5">
            <StatusLine label={tsbZone.zone.label} tone={tsbZone.zone.tone} />
            <p className="text-xs text-muted-foreground">
              TSB{' '}
              <strong className="text-foreground">
                {formatSigned(tsbZone.currentTsb ?? 0, 1)}
              </strong>{' '}
              - CTL{' '}
              <strong className="text-foreground">
                {formatCompactNumber(tsbZone.ctl ?? 0)}
              </strong>{' '}
              - ATL{' '}
              <strong className="text-foreground">
                {formatCompactNumber(tsbZone.atl ?? 0)}
              </strong>
            </p>
            <p className="text-xs text-muted-foreground">
              Tendance 7j:{' '}
              {tsbZone.trend7d == null ? '--' : formatSigned(tsbZone.trend7d, 1)}.{' '}
              {tsbZone.zone.recommendation}
            </p>
          </div>
        ) : (
          <SmallEmpty text="Pas assez de donnees training-load." />
        )}
      </InsightTile>
    </div>
  );
}

function PanelHeader({
  title,
  subtitle,
  Icon,
}: {
  title: string;
  subtitle: string;
  Icon: IconType;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div>
        <h2 className="text-sm font-bold text-foreground">{title}</h2>
        <p className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</p>
      </div>
      <span className="border-brand-cyan/20 bg-brand-cyan/10 rounded-md border p-1.5 text-brand-cyan">
        <Icon className="h-3.5 w-3.5" />
      </span>
    </div>
  );
}

function ChartFrame({
  loading,
  empty,
  children,
}: {
  loading: boolean;
  empty: boolean;
  children: ReactNode;
}) {
  return (
    <div className="h-52 min-w-0 rounded-md border border-border-subtle bg-card p-3">
      {loading ? (
        <div className="h-full animate-pulse rounded-md bg-[var(--chip-bg)]" />
      ) : empty ? (
        <div className="flex h-full items-center justify-center text-center text-sm text-muted-foreground">
          Donnees insuffisantes
        </div>
      ) : (
        children
      )}
    </div>
  );
}

function EmptyPanel({
  Icon,
  title,
  text,
  compact = false,
}: {
  Icon: IconType;
  title: string;
  text: string;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        'rounded-md border border-border-subtle bg-card p-4 text-center',
        compact ? 'py-5' : 'py-7',
      )}
    >
      <Icon className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
      <p className="text-sm font-semibold text-foreground">{title}</p>
      <p className="mx-auto mt-1 max-w-[260px] text-xs text-muted-foreground">{text}</p>
    </div>
  );
}

function InsightTile({
  title,
  Icon,
  tone,
  children,
}: {
  title: string;
  Icon: IconType;
  tone: 'amber' | 'blue' | 'green' | 'violet';
  children: ReactNode;
}) {
  const toneClasses = {
    amber: 'border-[var(--tone-amber-bd)] bg-[var(--tone-amber-bg)] text-[var(--tone-amber-fg)]',
    blue: 'border-[var(--tone-blue-bd)] bg-[var(--tone-blue-bg)] text-[var(--tone-blue-fg)]',
    green: 'border-[var(--tone-emerald-bd)] bg-[var(--tone-emerald-bg)] text-[var(--tone-emerald-fg)]',
    violet: 'border-[var(--tone-violet-bd)] bg-[var(--tone-violet-bg)] text-[var(--tone-violet-fg)]',
  };

  return (
    <div className="rounded-md border border-border-subtle bg-card p-3">
      <div className="mb-3 flex items-center gap-2">
        <span className={cn('rounded-md border p-1.5', toneClasses[tone])}>
          <Icon className="h-3.5 w-3.5" />
        </span>
        <p className="text-sm font-semibold text-foreground">{title}</p>
      </div>
      {children}
    </div>
  );
}

function InfoPill({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: 'amber' | 'blue' | 'green';
}) {
  const classes = {
    amber: 'border-[var(--tone-amber-bd)] bg-[var(--tone-amber-bg)] text-[var(--tone-amber-fg)]',
    blue: 'border-[var(--tone-blue-bd)] bg-[var(--tone-blue-bg)] text-[var(--tone-blue-fg)]',
    green: 'border-[var(--tone-emerald-bd)] bg-[var(--tone-emerald-bg)] text-[var(--tone-emerald-fg)]',
  };
  return (
    <span
      className={cn(
        'rounded-full border px-2.5 py-1 text-[11px] font-semibold',
        classes[tone],
      )}
    >
      {label}: {value}
    </span>
  );
}

function DataLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-surface-2 rounded-md border border-border-subtle px-2 py-2">
      <p className="text-[10px] font-semibold uppercase text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
}

function MiniMetricRow({
  label,
  value,
  max,
  unit,
  count,
}: {
  label: string;
  value: number | null;
  max: number;
  unit: string;
  count?: number;
}) {
  const pct = value == null || max <= 0 ? 0 : Math.min(100, (value / max) * 100);
  return (
    <div className="grid grid-cols-[54px_1fr_74px] items-center gap-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      <div className="bg-surface-3 h-1.5 overflow-hidden rounded-full">
        <div className="h-full rounded-full bg-brand-cyan" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-right text-xs font-semibold text-foreground">
        {value == null ? '--' : value.toFixed(unit === 'km' ? 1 : 0)} {unit}
        {count == null ? '' : ` (${count})`}
      </span>
    </div>
  );
}

function StatusLine({
  label,
  tone,
}: {
  label: string;
  tone: 'green' | 'amber' | 'red' | 'blue' | 'violet';
}) {
  const colors = {
    green: 'bg-emerald-400 text-[var(--tone-emerald-fg)]',
    amber: 'bg-amber-400 text-[var(--tone-amber-fg)]',
    red: 'bg-red-400 text-[var(--tone-red-fg)]',
    blue: 'bg-blue-400 text-[var(--tone-blue-fg)]',
    violet: 'bg-violet-400 text-[var(--tone-violet-fg)]',
  };
  return (
    <div className="flex items-center gap-2">
      <span className={cn('h-2.5 w-2.5 rounded-full', colors[tone].split(' ')[0])} />
      <span className={cn('text-sm font-semibold', colors[tone].split(' ')[1])}>
        {label}
      </span>
    </div>
  );
}

function SmallEmpty({ text }: { text: string }) {
  return <p className="text-xs italic text-muted-foreground">{text}</p>;
}

function buildStatsSummary(
  enrichedStats: EnrichedActivityStats | undefined,
  activitiesFallback: EnrichedActivity[],
): StatsSummary {
  if (enrichedStats) {
    return {
      totalActivities: enrichedStats.total_activities,
      totalDistanceKm: enrichedStats.total_distance_km,
      totalTimeHours: enrichedStats.total_time_hours,
      sportTypes: Object.keys(enrichedStats.activities_by_sport_type ?? {}).length,
    };
  }

  return summarizeActivities(activitiesFallback);
}

function summarizeActivities(activities: EnrichedActivity[]): StatsSummary {
  const sportTypes = new Set<string>();
  let totalDistanceKm = 0;
  let totalTimeHours = 0;

  for (const activity of activities) {
    sportTypes.add(activity.sport_type);
    totalDistanceKm += (activity.distance_m ?? 0) / 1000;
    totalTimeHours += (activity.moving_time_s ?? 0) / 3600;
  }

  return {
    totalActivities: activities.length,
    totalDistanceKm,
    totalTimeHours,
    sportTypes: sportTypes.size,
  };
}

function buildPerformanceData(
  activities: EnrichedActivity[],
  granularity: TimeGranularity,
): PerformancePoint[] {
  const buckets = new Map<string, EnrichedActivity[]>();
  for (const activity of activities) {
    const key = getBucketKey(activity.start_date_utc, granularity);
    const current = buckets.get(key) ?? [];
    current.push(activity);
    buckets.set(key, current);
  }

  return Array.from(buckets.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([bucketKey, bucketActivities]) => {
      const distance = bucketActivities.reduce(
        (total, activity) => total + (activity.distance_m ?? 0) / 1000,
        0,
      );
      const duration = bucketActivities.reduce(
        (total, activity) => total + (activity.moving_time_s ?? 0),
        0,
      );
      const elevation = bucketActivities.reduce(
        (total, activity) => total + (activity.elev_gain_m ?? 0),
        0,
      );
      const pace = distance > 0 ? duration / 60 / distance : 0;
      return {
        bucketKey,
        label: formatBucketLabel(bucketKey, granularity),
        distance,
        duration,
        pace,
        elevation,
        count: bucketActivities.length,
      };
    });
}

function sortGarminDaily(data: GarminDailyEntry[]): GarminDailyEntry[] {
  return [...data].sort((a, b) => a.date.localeCompare(b.date));
}

function summarizeGarminDaily(data: GarminDailyEntry[]) {
  const latest = lastOf(data);
  return {
    hrvAvg: meanDefined(data.map((entry) => entry.hrv_rmssd)),
    readinessAvg: meanDefined(data.map((entry) => entry.training_readiness)),
    sleepScoreAvg: meanDefined(data.map((entry) => entry.sleep_score)),
    restingHrAvg: meanDefined(data.map((entry) => entry.resting_hr)),
    latestRestingHr: latest?.resting_hr ?? null,
    latestVo2max: latest?.vo2max_estimated ?? null,
    latestWeightKg: latest?.weight_kg ?? null,
    trainingStatus: latest?.training_status ?? null,
    latestSpo2: latest?.spo2 ?? null,
    bodyBatteryMin:
      latest?.body_battery_min ??
      meanDefined(data.map((entry) => entry.body_battery_min)),
    bodyBatteryMax:
      latest?.body_battery_max ??
      meanDefined(data.map((entry) => entry.body_battery_max)),
  };
}

function aggregateGarminDaily(
  data: GarminDailyEntry[],
  granularity: TimeGranularity,
): GarminPoint[] {
  const buckets = new Map<
    string,
    { sums: Record<GarminMetricKey, number>; counts: Record<GarminMetricKey, number> }
  >();

  for (const entry of data) {
    const key = getBucketKey(entry.date, granularity);
    const bucket = buckets.get(key) ?? {
      sums: emptyGarminRecord(),
      counts: emptyGarminRecord(),
    };
    for (const metric of garminMetricKeys) {
      const value = entry[metric];
      if (typeof value === 'number') {
        bucket.sums[metric] += value;
        bucket.counts[metric] += 1;
      }
    }
    buckets.set(key, bucket);
  }

  return Array.from(buckets.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([bucketKey, bucket]) => ({
      bucketKey,
      label: formatBucketLabel(bucketKey, granularity),
      hrv_rmssd: averageFromBucket(bucket.sums.hrv_rmssd, bucket.counts.hrv_rmssd),
      training_readiness: averageFromBucket(
        bucket.sums.training_readiness,
        bucket.counts.training_readiness,
      ),
      sleep_score: averageFromBucket(bucket.sums.sleep_score, bucket.counts.sleep_score),
      stress_score: averageFromBucket(
        bucket.sums.stress_score,
        bucket.counts.stress_score,
      ),
      body_battery_max: averageFromBucket(
        bucket.sums.body_battery_max,
        bucket.counts.body_battery_max,
      ),
      resting_hr: averageFromBucket(bucket.sums.resting_hr, bucket.counts.resting_hr),
    }));
}

function summarizeSleep(data: GarminDailyEntry[]) {
  const sleepDays = data.filter(hasSleepData);
  return {
    avgScore: meanDefined(sleepDays.map((entry) => entry.sleep_score)),
    avgDurationMin: meanDefined(sleepDays.map((entry) => entry.sleep_duration_min)),
    nightsCount: sleepDays.length,
    latest: [...sleepDays].reverse().find(hasSleepData) ?? null,
  };
}

function aggregateSleepTrend(
  data: GarminDailyEntry[],
  granularity: TimeGranularity,
): SleepTrendPoint[] {
  const sleepDays = data.filter(hasSleepData);

  if (granularity === 'day') {
    return sleepDays.map((entry) => ({
      bucketKey: entry.date,
      label: formatBucketLabel(entry.date, granularity),
      sleep_score: entry.sleep_score,
      deep_min: secondsToMinutes(entry.deep_sleep_seconds),
      light_min: secondsToMinutes(entry.light_sleep_seconds),
      rem_min: secondsToMinutes(entry.rem_sleep_seconds),
      awake_min: secondsToMinutes(entry.awake_sleep_seconds),
      sleep_duration_min: entry.sleep_duration_min,
    }));
  }

  const buckets = new Map<string, GarminDailyEntry[]>();
  for (const entry of sleepDays) {
    const key = getBucketKey(entry.date, granularity);
    const current = buckets.get(key) ?? [];
    current.push(entry);
    buckets.set(key, current);
  }

  return Array.from(buckets.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([bucketKey, entries]) => ({
      bucketKey,
      label: formatBucketLabel(bucketKey, granularity),
      sleep_score: meanDefined(entries.map((entry) => entry.sleep_score)),
      deep_min: secondsToMinutes(
        meanDefined(entries.map((entry) => entry.deep_sleep_seconds)),
      ),
      light_min: secondsToMinutes(
        meanDefined(entries.map((entry) => entry.light_sleep_seconds)),
      ),
      rem_min: secondsToMinutes(
        meanDefined(entries.map((entry) => entry.rem_sleep_seconds)),
      ),
      awake_min: secondsToMinutes(
        meanDefined(entries.map((entry) => entry.awake_sleep_seconds)),
      ),
      sleep_duration_min: meanDefined(entries.map((entry) => entry.sleep_duration_min)),
    }));
}

function aggregateTrainingLoad(
  data: TrainingLoadEntry[],
  granularity: TimeGranularity,
): LoadPoint[] {
  const sorted = [...data].sort((a, b) => a.date.localeCompare(b.date));

  if (granularity === 'day') {
    return sorted.map((entry) => ({
      bucketKey: entry.date,
      label: formatBucketLabel(entry.date, granularity),
      chronicLoad: entry.ctl_42d ?? 0,
      acuteLoad: entry.atl_7d ?? 0,
      trainingStressBalance: entry.tsb ?? 0,
      chronicLoadEdwards: entry.ctl_42d_edwards ?? 0,
      acuteLoadEdwards: entry.atl_7d_edwards ?? 0,
      tsbEdwards: entry.tsb_edwards ?? 0,
    }));
  }

  const buckets = new Map<string, TrainingLoadEntry[]>();
  for (const entry of sorted) {
    const key = getBucketKey(entry.date, granularity);
    const current = buckets.get(key) ?? [];
    current.push(entry);
    buckets.set(key, current);
  }

  return Array.from(buckets.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([bucketKey, entries]) => ({
      bucketKey,
      label: formatBucketLabel(bucketKey, granularity),
      chronicLoad: meanDefined(entries.map((entry) => entry.ctl_42d)) ?? 0,
      acuteLoad: meanDefined(entries.map((entry) => entry.atl_7d)) ?? 0,
      trainingStressBalance: meanDefined(entries.map((entry) => entry.tsb)) ?? 0,
      chronicLoadEdwards: meanDefined(entries.map((entry) => entry.ctl_42d_edwards)) ?? 0,
      acuteLoadEdwards: meanDefined(entries.map((entry) => entry.atl_7d_edwards)) ?? 0,
      tsbEdwards: meanDefined(entries.map((entry) => entry.tsb_edwards)) ?? 0,
    }));
}

function loadSeriesForModel(model: LoadModel): Array<keyof typeof loadSeriesConfig> {
  if (model === 'banister') return ['chronicLoad', 'acuteLoad', 'trainingStressBalance'];
  if (model === 'edwards')
    return ['chronicLoadEdwards', 'acuteLoadEdwards', 'tsbEdwards'];
  return [
    'chronicLoad',
    'acuteLoad',
    'trainingStressBalance',
    'chronicLoadEdwards',
    'acuteLoadEdwards',
    'tsbEdwards',
  ];
}

function loadMetrics(latest: LoadPoint, previous: LoadPoint | null, model: LoadModel) {
  if (model === 'edwards') {
    return {
      ctl: latest.chronicLoadEdwards,
      atl: latest.acuteLoadEdwards,
      tsb: latest.tsbEdwards,
      ctlDelta:
        latest.chronicLoadEdwards -
        (previous?.chronicLoadEdwards ?? latest.chronicLoadEdwards),
    };
  }

  return {
    ctl: latest.chronicLoad,
    atl: latest.acuteLoad,
    tsb: latest.trainingStressBalance,
    ctlDelta: latest.chronicLoad - (previous?.chronicLoad ?? latest.chronicLoad),
  };
}

function tsbStatus(tsb: number) {
  if (tsb > 10) {
    return {
      label: 'Frais',
      tone: 'green' as const,
      dot: 'bg-emerald-400',
      textClass: 'text-[var(--tone-emerald-fg)]',
      recommendation: 'Fraicheur elevee. Bon moment pour une seance qualite.',
    };
  }
  if (tsb > 0) {
    return {
      label: 'Forme',
      tone: 'green' as const,
      dot: 'bg-emerald-400',
      textClass: 'text-[var(--tone-emerald-fg)]',
      recommendation: 'Forme positive, charge recente bien absorbee.',
    };
  }
  if (tsb > -10) {
    return {
      label: 'Equilibre',
      tone: 'blue' as const,
      dot: 'bg-blue-400',
      textClass: 'text-[var(--tone-blue-fg)]',
      recommendation: 'Zone stable. Garde le volume sans forcer inutilement.',
    };
  }
  if (tsb > -20) {
    return {
      label: 'Fatigue',
      tone: 'amber' as const,
      dot: 'bg-amber-400',
      textClass: 'text-[var(--tone-amber-fg)]',
      recommendation: 'Fatigue visible. Prevois une journee plus legere.',
    };
  }
  return {
    label: 'Surmenage',
    tone: 'red' as const,
    dot: 'bg-red-400',
    textClass: 'text-[var(--tone-red-fg)]',
    recommendation: 'Charge trop haute. Repos ou recuperation active conseillee.',
  };
}

function rhrTone(value: number | null | undefined): 'green' | 'amber' | 'rose' {
  if (value == null) return 'amber';
  if (value > 0) return 'rose';
  if (value < 0) return 'green';
  return 'amber';
}

function lastWithRhr(data: TrainingLoadEntry[]): TrainingLoadEntry | null {
  return [...data].reverse().find((entry) => entry.rhr_delta_7d != null) ?? null;
}

function sleepPhases(entry: GarminDailyEntry) {
  const phases = [
    {
      key: 'deep',
      label: 'Profond',
      seconds: entry.deep_sleep_seconds ?? 0,
      className: 'bg-indigo-500',
    },
    {
      key: 'light',
      label: 'Leger',
      seconds: entry.light_sleep_seconds ?? 0,
      className: 'bg-blue-400',
    },
    {
      key: 'rem',
      label: 'REM',
      seconds: entry.rem_sleep_seconds ?? 0,
      className: 'bg-violet-400',
    },
    {
      key: 'awake',
      label: 'Eveille',
      seconds: entry.awake_sleep_seconds ?? 0,
      className: 'bg-stone-400',
    },
  ];
  const total = phases.reduce((sum, phase) => sum + phase.seconds, 0);
  return phases.map((phase) => ({
    ...phase,
    percent: total > 0 ? (phase.seconds / total) * 100 : 0,
  }));
}

function hasSleepData(entry: GarminDailyEntry): boolean {
  return (
    entry.sleep_score != null ||
    entry.sleep_duration_min != null ||
    entry.sleep_start_time != null ||
    entry.sleep_end_time != null ||
    (entry.deep_sleep_seconds ?? 0) +
      (entry.light_sleep_seconds ?? 0) +
      (entry.rem_sleep_seconds ?? 0) +
      (entry.awake_sleep_seconds ?? 0) >
      0
  );
}

function buildGarminMap(data: GarminDailyEntry[]): Map<string, GarminDailyEntry> {
  const map = new Map<string, GarminDailyEntry>();
  for (const entry of data) {
    map.set(entry.date, entry);
  }
  return map;
}

function computeWeatherHr(
  activities: EnrichedActivity[],
  weatherMap: Map<string, ActivityWeather>,
) {
  const buckets = {
    cold: [] as number[],
    mild: [] as number[],
    hot: [] as number[],
  };

  for (const activity of activities) {
    const hr = activity.avg_heartrate_bpm ?? 0;
    if (hr <= 0) continue;
    const weather = weatherMap.get(String(activity.activity_id));
    if (!weather || weather.temperature_c == null) continue;
    if (weather.temperature_c < 10) buckets.cold.push(hr);
    else if (weather.temperature_c <= 20) buckets.mild.push(hr);
    else buckets.hot.push(hr);
  }

  const cold = bucketAverage(buckets.cold);
  const mild = bucketAverage(buckets.mild);
  const hot = bucketAverage(buckets.hot);
  const total = buckets.cold.length + buckets.mild.length + buckets.hot.length;
  const values = [cold?.avgHr, mild?.avgHr, hot?.avgHr].filter(
    (value): value is number => value != null,
  );

  return {
    hasData: total >= 5,
    cold,
    mild,
    hot,
    heatDelta: hot && mild ? hot.avgHr - mild.avgHr : null,
    maxHr: values.length > 0 ? Math.max(...values) * 1.1 : 180,
  };
}

function bucketAverage(values: number[]): { count: number; avgHr: number } | null {
  if (values.length === 0) return null;
  return {
    count: values.length,
    avgHr: values.reduce((sum, value) => sum + value, 0) / values.length,
  };
}

function computeSleepLoad(
  activities: EnrichedActivity[],
  garminDaily: GarminDailyEntry[],
) {
  const last7 = garminDaily.slice(-7);
  const avgSleep7d = meanDefined(last7.map((entry) => entry.sleep_score));
  const sevenDaysAgo = addDays(new Date(), -7);
  const activityCount7d = activities.filter(
    (activity) => new Date(activity.start_date_utc) >= sevenDaysAgo,
  ).length;

  if (last7.length < 7 || avgSleep7d == null) {
    return { hasData: false, avgSleep7d, activityCount7d, state: null };
  }

  if (avgSleep7d >= 70 && activityCount7d <= 2) {
    return {
      hasData: true,
      avgSleep7d,
      activityCount7d,
      state: 'bonne_recuperation',
      stateLabel: 'Bonne recuperation',
      tone: 'blue' as const,
      recommendation: 'Sommeil solide et charge moderee. Fenetre favorable.',
    };
  }

  if (
    (avgSleep7d >= 60 && activityCount7d <= 5) ||
    (avgSleep7d >= 70 && activityCount7d <= 6)
  ) {
    return {
      hasData: true,
      avgSleep7d,
      activityCount7d,
      state: 'equilibre',
      stateLabel: 'Equilibre',
      tone: 'green' as const,
      recommendation: 'Ratio sommeil/charge coherent.',
    };
  }

  return {
    hasData: true,
    avgSleep7d,
    activityCount7d,
    state: 'attention',
    stateLabel: 'Attention',
    tone: 'amber' as const,
    recommendation: 'Charge elevee ou sommeil bas. Reduis la prochaine intensite.',
  };
}

function computeHrvPerformance(
  activities: EnrichedActivity[],
  garminMap: Map<string, GarminDailyEntry>,
) {
  const paired: Array<{ hrv: number; pace: number }> = [];

  for (const activity of activities) {
    const pace = activityPace(activity);
    if (pace == null) continue;
    const previousDay = isoDate(addDays(new Date(activity.start_date_utc), -1));
    const garmin = garminMap.get(previousDay);
    if (garmin?.hrv_rmssd == null) continue;
    paired.push({ hrv: garmin.hrv_rmssd, pace });
  }

  if (paired.length < 5) {
    return {
      hasData: false,
      diffPct: null,
      label: 'Stable',
      tone: 'green' as const,
      recommendation: '',
    };
  }

  const sorted = [...paired].sort((a, b) => a.hrv - b.hrv);
  const mid = Math.floor(sorted.length / 2);
  const low = sorted.slice(0, mid);
  const high = sorted.slice(mid);
  const lowAvg = meanDefined(low.map((item) => item.pace));
  const highAvg = meanDefined(high.map((item) => item.pace));
  const diffPct =
    lowAvg != null && highAvg != null && lowAvg > 0
      ? ((lowAvg - highAvg) / lowAvg) * 100
      : null;

  if (diffPct != null && diffPct > 2) {
    return {
      hasData: true,
      diffPct,
      label: 'Correlation positive',
      tone: 'green' as const,
      recommendation: 'Les seances qualite peuvent mieux tomber apres une HRV haute.',
    };
  }
  if (diffPct != null && diffPct < -2) {
    return {
      hasData: true,
      diffPct,
      label: 'Correlation inversee',
      tone: 'amber' as const,
      recommendation: 'Surveille les seances intenses lorsque la HRV est basse.',
    };
  }
  return {
    hasData: true,
    diffPct,
    label: 'Stable',
    tone: 'blue' as const,
    recommendation: 'Performance reguliere malgre les variations de recuperation.',
  };
}

function computeVolumeTrend(activities: EnrichedActivity[]) {
  const currentMonday = weekStart(new Date());
  const weeks: Array<{
    label: string;
    start: Date;
    end: Date;
    distanceKm: number;
    count: number;
  }> = [];

  for (let index = 0; index < 4; index += 1) {
    const start = addDays(currentMonday, -index * 7);
    weeks.push({
      label: index === 0 ? 'Actuelle' : `S-${index}`,
      start,
      end: addDays(start, 7),
      distanceKm: 0,
      count: 0,
    });
  }

  for (const activity of activities) {
    const date = new Date(activity.start_date_utc);
    const match = weeks.find((week) => date >= week.start && date < week.end);
    if (match) {
      match.distanceKm += (activity.distance_m ?? 0) / 1000;
      match.count += 1;
    }
  }

  const previousWeek = weeks[1] ?? null;
  const currentWeek = weeks[0] ?? null;
  const maxKm = Math.max(...weeks.map((week) => week.distanceKm), 1) * 1.1;
  return {
    hasData: weeks.some((week) => week.count > 0),
    weeks: weeks.map(({ label, distanceKm, count }) => ({ label, distanceKm, count })),
    currentVsPrevPct:
      currentWeek && previousWeek && previousWeek.distanceKm > 0
        ? ((currentWeek.distanceKm - previousWeek.distanceKm) / previousWeek.distanceKm) *
          100
        : null,
    maxKm,
  };
}

function computeBestDay(activities: EnrichedActivity[]) {
  const names = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
  const buckets = names.map((day) => ({ day, paces: [] as number[] }));

  for (const activity of activities) {
    const pace = activityPace(activity);
    if (pace == null) continue;
    const day = new Date(activity.start_date_utc).getDay();
    buckets[day]?.paces.push(pace);
  }

  const allPaces = buckets.flatMap((bucket) => bucket.paces);
  const globalAvgPace = meanDefined(allPaces);
  const days = buckets.map((bucket) => ({
    day: bucket.day,
    avgPace: meanDefined(bucket.paces),
    count: bucket.paces.length,
  }));

  const candidates = days.filter((day) => day.avgPace != null && day.count >= 2);
  const best = candidates.reduce<(typeof candidates)[number] | null>((current, day) => {
    if (!current) return day;
    if (day.avgPace != null && current.avgPace != null && day.avgPace < current.avgPace)
      return day;
    return current;
  }, null);

  return {
    hasData: allPaces.length >= 5,
    days,
    bestDay: best?.day ?? null,
    bestPace: best?.avgPace ?? null,
    globalAvgPace,
  };
}

function computeTsbZone(data: TrainingLoadEntry[]) {
  const points = aggregateTrainingLoad(data, 'day');
  if (points.length < 7) {
    return {
      hasData: false,
      currentTsb: null,
      trend7d: null,
      ctl: null,
      atl: null,
      zone: null,
    };
  }

  const latest = lastOf(points);
  const weekAgo = points[Math.max(0, points.length - 8)] ?? null;
  if (!latest || !weekAgo) {
    return {
      hasData: false,
      currentTsb: null,
      trend7d: null,
      ctl: null,
      atl: null,
      zone: null,
    };
  }

  const zone = tsbStatus(latest.trainingStressBalance);
  return {
    hasData: true,
    currentTsb: latest.trainingStressBalance,
    trend7d: latest.trainingStressBalance - weekAgo.trainingStressBalance,
    ctl: latest.chronicLoad,
    atl: latest.acuteLoad,
    zone,
  };
}

function activityPace(activity: EnrichedActivity): number | null {
  const speed = activity.avg_speed_m_s ?? activity.avg_speed_mps ?? null;
  if (speed != null && speed > 0) return 1000 / speed / 60;
  const distanceKm = (activity.distance_m ?? 0) / 1000;
  const durationMin = (activity.moving_time_s ?? 0) / 60;
  if (distanceKm <= 0 || durationMin <= 0) return null;
  return durationMin / distanceKm;
}

function getBucketKey(dateIso: string, granularity: TimeGranularity): string {
  const date = new Date(dateIso);
  date.setHours(0, 0, 0, 0);
  if (granularity === 'week') {
    const day = date.getDay();
    const offset = day === 0 ? 6 : day - 1;
    date.setDate(date.getDate() - offset);
  }
  if (granularity === 'month') {
    date.setDate(1);
  }
  return isoDate(date);
}

function formatBucketLabel(bucketKey: string, granularity: TimeGranularity): string {
  const date = new Date(bucketKey);
  if (granularity === 'week') {
    return `Sem. ${date.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })}`;
  }
  if (granularity === 'month') {
    return date.toLocaleDateString('fr-FR', { month: 'short', year: '2-digit' });
  }
  return date.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
}

function granularityLabel(granularity: TimeGranularity): string {
  if (granularity === 'day') return 'par jour';
  if (granularity === 'week') return 'par semaine';
  return 'par mois';
}

function formatMetricValue(metric: MetricKey, value: number): string {
  if (metric === 'duration') return formatSeconds(value);
  if (metric === 'pace') return `${formatPace(value)} /km`;
  if (metric === 'elevation') return `${Math.round(value)} m`;
  return `${value.toFixed(1)} km`;
}

function formatAxisValue(metric: MetricKey, value: number): string {
  if (metric === 'duration') return `${Math.round(value / 3600)}h`;
  if (metric === 'pace') return value.toFixed(1);
  if (metric === 'elevation') return `${Math.round(value)}`;
  return value >= 10 ? `${Math.round(value)}` : value.toFixed(1);
}

function formatCompactNumber(value: number): string {
  if (!Number.isFinite(value)) return '--';
  if (Math.abs(value) >= 100) return Math.round(value).toString();
  if (Math.abs(value) >= 10) return value.toFixed(1);
  return value.toFixed(1);
}

function formatNullable(value: number | null, decimals: number): string {
  if (value == null || !Number.isFinite(value)) return '--';
  return value.toFixed(decimals);
}

function formatSigned(value: number, decimals: number): string {
  const formatted = value.toFixed(decimals);
  if (value > 0) return `+${formatted}`;
  return formatted;
}

function formatHours(hours: number): string {
  if (!Number.isFinite(hours) || hours <= 0) return '0h';
  const h = Math.floor(hours);
  const min = Math.round((hours - h) * 60);
  if (h <= 0) return `${min}min`;
  return min > 0 ? `${h}h${String(min).padStart(2, '0')}` : `${h}h`;
}

function formatMinutes(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes <= 0) return '0min';
  const h = Math.floor(minutes / 60);
  const min = Math.round(minutes % 60);
  if (h <= 0) return `${min}min`;
  return min > 0 ? `${h}h${String(min).padStart(2, '0')}` : `${h}h`;
}

function formatSeconds(seconds: number): string {
  return formatMinutes(seconds / 60);
}

function formatPace(paceMinKm: number): string {
  if (!Number.isFinite(paceMinKm) || paceMinKm <= 0) return '--';
  const mins = Math.floor(paceMinKm);
  const secs = Math.round((paceMinKm - mins) * 60);
  return `${mins}:${String(secs).padStart(2, '0')}`;
}

function formatClock(value: string | null): string {
  if (!value) return '--';
  const date = new Date(value);
  if (!Number.isNaN(date.getTime()) && value.includes('T')) {
    return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
  }
  return value.slice(0, 5);
}

function meanDefined(values: Array<number | null | undefined>): number | null {
  const valid = values.filter(
    (value): value is number => typeof value === 'number' && Number.isFinite(value),
  );
  if (valid.length === 0) return null;
  return valid.reduce((sum, value) => sum + value, 0) / valid.length;
}

function averageFromBucket(sum: number, count: number): number | null {
  return count > 0 ? sum / count : null;
}

function emptyGarminRecord(): Record<GarminMetricKey, number> {
  return {
    hrv_rmssd: 0,
    training_readiness: 0,
    sleep_score: 0,
    stress_score: 0,
    body_battery_max: 0,
    resting_hr: 0,
  };
}

function secondsToMinutes(seconds: number | null): number {
  return seconds == null ? 0 : Math.round(seconds / 60);
}

function toNumber(value: unknown): number {
  if (typeof value === 'number') return value;
  if (typeof value === 'string') return Number(value);
  return 0;
}

function lastOf<T>(items: T[]): T | null {
  return items.length > 0 ? (items[items.length - 1] ?? null) : null;
}

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function daysAgoIso(days: number): string {
  return isoDate(addDays(new Date(), -days));
}

function addDays(date: Date, days: number): Date {
  const copy = new Date(date);
  copy.setDate(copy.getDate() + days);
  return copy;
}

function weekStart(date: Date): Date {
  const start = new Date(date);
  start.setHours(0, 0, 0, 0);
  const day = start.getDay();
  const offset = day === 0 ? 6 : day - 1;
  start.setDate(start.getDate() - offset);
  return start;
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function readStoredPeriod(): PeriodDays {
  const value = readStoredValue(analyticsStorageKeys.period);
  const parsed = Number(value);
  return periodValues.includes(parsed as PeriodDays) ? (parsed as PeriodDays) : 30;
}

function readStoredGranularity(): TimeGranularity {
  const value = readStoredValue(analyticsStorageKeys.granularity);
  return granularityValues.includes(value as TimeGranularity)
    ? (value as TimeGranularity)
    : 'day';
}

function readStoredValue(key: string): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStoredValue(key: string, value: string | number): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, String(value));
  } catch {
    // Storage can be unavailable in private contexts; the UI still works in memory.
  }
}

const chartTickStyle = {
  fill: 'var(--muted-foreground)',
  fontSize: 10,
};

const tooltipStyle = {
  background: 'var(--card)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 6,
  color: 'var(--foreground)',
};

const tooltipLabelStyle = {
  color: 'var(--foreground)',
  fontWeight: 700,
};

export default MobileAnalyticsDashboard;
