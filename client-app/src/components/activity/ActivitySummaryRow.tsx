import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronRight, Heart, Thermometer, Timer, Zap } from 'lucide-react';
import {
  activityDisplayId,
  agonApi,
  type ActivityWeather,
  type EnrichedActivity,
  type FitMetrics,
} from '@/lib/api/agon';
import {
  formatDateShort,
  formatDistance,
  formatDuration,
  getSportPresentation,
} from '@/lib/activity-format';
import { cn } from '@/lib/utils';

interface ActivitySummaryRowProps {
  activity: EnrichedActivity;
  isLast?: boolean;
  variant?: 'home' | 'list';
}

export function ActivitySummaryRow({
  activity,
  isLast = false,
  variant = 'list',
}: ActivitySummaryRowProps) {
  const activityId = activityDisplayId(activity);
  const { Icon, label, toneClass } = getSportPresentation(activity.sport_type);

  const weatherQuery = useQuery({
    queryKey: ['agon', 'activity-weather', activityId],
    queryFn: () => agonApi.getActivityWeather(activityId),
    staleTime: 30 * 60_000,
    retry: false,
    enabled: activity.has_weather === true,
  });

  const fitQuery = useQuery({
    queryKey: ['agon', 'activity-fit', activityId],
    queryFn: () => agonApi.getActivityFitMetrics(activityId),
    staleTime: 30 * 60_000,
    retry: false,
    enabled: activity.has_fit_metrics === true,
  });

  const chips = buildMetricChips(activity, weatherQuery.data, fitQuery.data);

  return (
    <Link
      to={`/activities/${activityId}`}
      className={cn(
        'group block px-3.5 py-3 transition hover:bg-[var(--hover-overlay)] active:bg-[var(--active-overlay)]',
        !isLast && 'border-b border-border-subtle',
      )}
    >
      <div className="flex items-start gap-2.5">
        <div
          className={cn(
            'flex h-9 w-9 shrink-0 items-center justify-center rounded-md border',
            toneClass,
          )}
          aria-label={label}
        >
          <Icon className="h-4 w-4" />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="min-w-0 truncate text-sm font-semibold text-foreground">
              {activity.name}
            </p>
            <div className="flex shrink-0 items-center gap-1.5">
              <span className="text-sm font-bold text-foreground">
                {formatDistance(activity.distance_m)}
              </span>
              {variant === 'list' ? (
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition group-hover:text-foreground" />
              ) : null}
            </div>
          </div>

          <div className="mt-0.5 flex items-center justify-between gap-2">
            <p className="truncate text-xs text-muted-foreground">
              {formatDateShort(activity.start_date_utc)} · {label}
            </p>
            <p className="shrink-0 text-xs text-muted-foreground">
              {formatDuration(activity.moving_time_s)}
            </p>
          </div>

          {chips.length > 0 ? (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {chips.map((chip) => (
                <span
                  key={chip.key}
                  className={cn(
                    'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold leading-4',
                    chip.className,
                  )}
                >
                  <chip.Icon className="h-3 w-3" />
                  {chip.label}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </Link>
  );
}

function buildMetricChips(
  activity: EnrichedActivity,
  weather?: ActivityWeather,
  fit?: FitMetrics,
): Array<{
  key: string;
  label: string;
  Icon: typeof Heart;
  className: string;
}> {
  const chips: Array<{
    key: string;
    label: string;
    Icon: typeof Heart;
    className: string;
  }> = [];

  if (activity.avg_heartrate_bpm != null && activity.avg_heartrate_bpm > 0) {
    const max =
      activity.max_heartrate_bpm != null && activity.max_heartrate_bpm > 0
        ? `/${Math.round(activity.max_heartrate_bpm)}`
        : '';
    chips.push({
      key: 'hr',
      Icon: Heart,
      label: `${Math.round(activity.avg_heartrate_bpm)}${max} bpm`,
      className: 'border-[var(--tone-red-bd)] bg-[var(--tone-red-bg)] text-[var(--tone-red-fg)]',
    });
  }

  if (weather?.temperature_c != null) {
    chips.push({
      key: 'temperature',
      Icon: Thermometer,
      label: `${weather.temperature_c.toFixed(0)}°C`,
      className: 'border-[var(--tone-amber-bd)] bg-[var(--tone-amber-bg)] text-[var(--tone-amber-fg)]',
    });
  }

  if (fit?.aerobic_training_effect != null) {
    const anaerobic =
      fit.anaerobic_training_effect != null
        ? `/${fit.anaerobic_training_effect.toFixed(1)}`
        : '';
    chips.push({
      key: 'te',
      Icon: Timer,
      label: `TE ${fit.aerobic_training_effect.toFixed(1)}${anaerobic}`,
      className: 'border-[var(--tone-emerald-bd)] bg-[var(--tone-emerald-bg)] text-[var(--tone-emerald-fg)]',
    });
  }

  if (fit?.power_avg != null) {
    chips.push({
      key: 'power',
      Icon: Zap,
      label: `${fit.power_avg.toFixed(0)} W`,
      className: 'border-sky-400/20 bg-sky-400/10 text-sky-200',
    });
  }

  return chips.slice(0, 4);
}

export default ActivitySummaryRow;
