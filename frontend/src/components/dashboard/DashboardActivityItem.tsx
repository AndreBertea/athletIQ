import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Thermometer, Heart, Zap, Footprints, Timer, Flame,
  Clock, MoveVertical, ArrowLeftRight, Wind, Droplets,
  Cloud, ChevronDown
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { dataService } from '../../services/dataService'
import type { ActivityWeather } from '../../services/dataService'
import { garminService } from '../../services/garminService'
import type { FitMetrics } from '../../services/garminService'
import type { EnrichedActivity } from '../../services/activityService'
import { formatDateShort, formatDuration } from '../../lib/format'

interface DashboardActivityItemProps {
  activity: EnrichedActivity
  weather?: ActivityWeather | null
  fitMetrics?: FitMetrics | null
}

const sportBadgeColors: Record<string, string> = {
  Run: 'bg-green-100 text-green-700',
  TrailRun: 'bg-emerald-100 text-emerald-700',
  Ride: 'bg-blue-100 text-blue-700',
  Swim: 'bg-cyan-100 text-cyan-700',
  RacketSport: 'bg-orange-100 text-orange-700',
  Tennis: 'bg-orange-100 text-orange-700',
  Workout: 'bg-purple-100 text-purple-700',
  Hike: 'bg-amber-100 text-amber-700',
  Walk: 'bg-yellow-100 text-yellow-700',
}

function weatherLabel(code: number | null | undefined): string | null {
  if (code == null) return null
  if (code === 0) return 'Clair'
  if (code <= 3) return 'Nuageux'
  if (code >= 45 && code <= 48) return 'Brouillard'
  if (code >= 51 && code <= 57) return 'Bruine'
  if (code >= 61 && code <= 67) return 'Pluie'
  if (code >= 71 && code <= 77) return 'Neige'
  if (code >= 80 && code <= 82) return 'Averses'
  if (code >= 95 && code <= 99) return 'Orage'
  return null
}

export default function DashboardActivityItem({ activity, weather: weatherProp, fitMetrics: fitMetricsProp }: DashboardActivityItemProps) {
  const [expanded, setExpanded] = useState(false)
  const activityId = String(activity.activity_id)

  const { data: weatherQuery } = useQuery({
    queryKey: ['weather', activity.activity_id],
    queryFn: () => dataService.getWeather(activityId),
    staleTime: 30 * 60 * 1000,
    retry: false,
    enabled: weatherProp === undefined,
  })

  const { data: fitMetricsQuery } = useQuery({
    queryKey: ['fit-metrics', activity.activity_id],
    queryFn: () => garminService.getActivityFitMetrics(activityId),
    staleTime: 30 * 60 * 1000,
    retry: false,
    enabled: fitMetricsProp === undefined && activity.has_garmin === true,
  })

  const weather = weatherProp ?? weatherQuery
  const fitMetrics = fitMetricsProp ?? fitMetricsQuery

  const distanceKm = (activity.distance_m / 1000).toFixed(1)
  const duration = formatDuration(activity.moving_time_s)
  const badgeColor = sportBadgeColors[activity.sport_type] || 'bg-gray-100 text-gray-700'
  const dateFormatted = formatDateShort(activity.start_date_utc)

  // Collect secondary badges
  const secondaryBadges: { key: string; icon: typeof Heart; label: string; color: string }[] = []

  if (fitMetrics?.ground_contact_time_avg != null)
    secondaryBadges.push({ key: 'gct', icon: Footprints, label: `GCT ${fitMetrics.ground_contact_time_avg.toFixed(0)} ms`, color: 'text-purple-700 bg-purple-50' })
  if (fitMetrics?.power_avg != null)
    secondaryBadges.push({ key: 'power', icon: Zap, label: `${fitMetrics.power_avg.toFixed(0)} W`, color: 'text-blue-700 bg-blue-50' })
  if (fitMetrics?.vertical_oscillation_avg != null)
    secondaryBadges.push({ key: 'vo', icon: MoveVertical, label: `OV ${fitMetrics.vertical_oscillation_avg.toFixed(1)} cm`, color: 'text-teal-700 bg-teal-50' })
  if (fitMetrics?.stance_time_balance_avg != null)
    secondaryBadges.push({ key: 'balance', icon: ArrowLeftRight, label: `G/D ${fitMetrics.stance_time_balance_avg.toFixed(1)}%`, color: 'text-slate-700 bg-slate-100' })
  if (activity.elapsed_time_s > 0 && activity.elapsed_time_s - activity.moving_time_s > 60)
    secondaryBadges.push({ key: 'elapsed', icon: Clock, label: `Total ${formatDuration(activity.elapsed_time_s)}`, color: 'text-gray-600 bg-gray-100' })
  if (weather?.wind_speed_kmh != null && weather.wind_speed_kmh > 0)
    secondaryBadges.push({ key: 'wind', icon: Wind, label: `${weather.wind_speed_kmh.toFixed(0)} km/h`, color: 'text-cyan-700 bg-cyan-50' })
  if (weather?.humidity_pct != null)
    secondaryBadges.push({ key: 'humidity', icon: Droplets, label: `${weather.humidity_pct.toFixed(0)}%`, color: 'text-blue-600 bg-blue-50' })
  if (weather?.precipitation_mm != null && weather.precipitation_mm > 0)
    secondaryBadges.push({ key: 'precip', icon: Cloud, label: `${weather.precipitation_mm.toFixed(1)} mm`, color: 'text-indigo-700 bg-indigo-50' })

  const hasSecondary = secondaryBadges.length > 0

  return (
    <div className="py-4 first:pt-0 last:pb-0 group cursor-default">
      {/* Row 1: Name + Sport badge | Distance + Duration */}
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-gray-900 truncate text-sm">{activity.name}</span>
            <span className={cn('inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium', badgeColor)}>
              {activity.sport_type}
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">{dateFormatted}</p>
        </div>

        <div className="flex items-center gap-4 text-sm shrink-0">
          {activity.distance_m > 0 && (
            <span className="font-semibold text-gray-900">{distanceKm} km</span>
          )}
          <span className="text-gray-500">{duration}</span>
        </div>
      </div>

      {/* Row 2: Primary badges (max 4) */}
      <div className="flex items-center gap-2 mt-2 flex-wrap">
        {/* FC */}
        {activity.avg_heartrate_bpm > 0 && (
          <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-red-50 text-red-700">
            <Heart className="h-3 w-3" />
            {Math.round(activity.avg_heartrate_bpm)}/{Math.round(activity.max_heartrate_bpm)} bpm
          </span>
        )}

        {/* Temperature + weather */}
        {weather?.temperature_c != null && (
          <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-amber-50 text-amber-700">
            <Thermometer className="h-3 w-3" />
            {weather.temperature_c.toFixed(0)}°C
            {weatherLabel(weather.weather_code) && (
              <span className="text-amber-500 ml-0.5">· {weatherLabel(weather.weather_code)}</span>
            )}
          </span>
        )}

        {/* Training Effect */}
        {fitMetrics?.aerobic_training_effect != null && (
          <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-green-50 text-green-700">
            <Timer className="h-3 w-3" />
            TE {fitMetrics.aerobic_training_effect.toFixed(1)}
            {fitMetrics.anaerobic_training_effect != null && (
              <> / {fitMetrics.anaerobic_training_effect.toFixed(1)}</>
            )}
          </span>
        )}

        {/* Calories */}
        {activity.calories_kcal > 0 && (
          <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-orange-50 text-orange-700">
            <Flame className="h-3 w-3" />
            {Math.round(activity.calories_kcal)} kcal
          </span>
        )}

        {/* Expand toggle for secondary badges */}
        {hasSecondary && (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="inline-flex items-center gap-0.5 text-xs text-gray-400 hover:text-gray-600 transition-colors ml-auto"
          >
            <span>{expanded ? 'Moins' : `+${secondaryBadges.length}`}</span>
            <ChevronDown className={cn('h-3.5 w-3.5 transition-transform duration-200', expanded && 'rotate-180')} />
          </button>
        )}
      </div>

      {/* Row 3: Secondary badges (expandable) */}
      {expanded && hasSecondary && (
        <div className="flex items-center gap-2 mt-2 flex-wrap">
          {secondaryBadges.map(({ key, icon: Icon, label, color }) => (
            <span key={key} className={cn('inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full', color)}>
              <Icon className="h-3 w-3" />
              {label}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
