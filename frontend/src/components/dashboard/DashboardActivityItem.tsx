import { useQuery } from '@tanstack/react-query'
import { Thermometer, Heart, Zap, Footprints, Timer } from 'lucide-react'
import { cn } from '../../lib/utils'
import { dataService } from '../../services/dataService'
import type { ActivityWeather } from '../../services/dataService'
import { garminService } from '../../services/garminService'
import type { FitMetrics } from '../../services/garminService'
import type { EnrichedActivity } from '../../services/activityService'
import { formatDateShort, formatDuration } from '../../lib/format'

interface DashboardActivityItemProps {
  activity: EnrichedActivity
  onClick: () => void
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

export default function DashboardActivityItem({ activity, onClick, weather: weatherProp, fitMetrics: fitMetricsProp }: DashboardActivityItemProps) {
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
    enabled: fitMetricsProp === undefined,
  })

  const weather = weatherProp ?? weatherQuery
  const fitMetrics = fitMetricsProp ?? fitMetricsQuery

  const distanceKm = (activity.distance_m / 1000).toFixed(1)
  const duration = formatDuration(activity.moving_time_s)
  const badgeColor = sportBadgeColors[activity.sport_type] || 'bg-gray-100 text-gray-700'

  const dateFormatted = formatDateShort(activity.start_date_utc)

  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left p-4 rounded-lg border border-gray-200 hover:border-primary-300 hover:bg-gray-50 transition-colors"
    >
      {/* Ligne principale */}
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-gray-900 truncate">{activity.name}</span>
            <span className={cn('px-2 py-0.5 rounded-full text-xs font-medium', badgeColor)}>
              {activity.sport_type}
            </span>
          </div>
          <p className="text-sm text-gray-500 mt-0.5">{dateFormatted}</p>
        </div>

        <div className="flex items-center gap-4 text-sm text-gray-600 shrink-0">
          {activity.distance_m > 0 && (
            <span className="font-medium">{distanceKm} km</span>
          )}
          <span>{duration}</span>
        </div>
      </div>

      {/* Badges secondaires */}
      <div className="flex items-center gap-3 mt-2 flex-wrap">
        {/* FC */}
        {activity.avg_heartrate_bpm > 0 && (
          <span className="inline-flex items-center gap-1 text-xs text-red-600 bg-red-50 px-2 py-0.5 rounded-full">
            <Heart className="h-3 w-3" />
            {Math.round(activity.avg_heartrate_bpm)}/{Math.round(activity.max_heartrate_bpm)} bpm
          </span>
        )}

        {/* Météo */}
        {weather?.temperature_c != null && (
          <span className="inline-flex items-center gap-1 text-xs text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full">
            <Thermometer className="h-3 w-3" />
            {weather.temperature_c.toFixed(0)}°C
          </span>
        )}

        {/* FIT — GCT */}
        {fitMetrics?.ground_contact_time_avg != null && (
          <span className="inline-flex items-center gap-1 text-xs text-purple-700 bg-purple-50 px-2 py-0.5 rounded-full">
            <Footprints className="h-3 w-3" />
            GCT {fitMetrics.ground_contact_time_avg.toFixed(0)} ms
          </span>
        )}

        {/* FIT — Puissance */}
        {fitMetrics?.power_avg != null && (
          <span className="inline-flex items-center gap-1 text-xs text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full">
            <Zap className="h-3 w-3" />
            {fitMetrics.power_avg.toFixed(0)} W
          </span>
        )}

        {/* FIT — Training Effect */}
        {fitMetrics?.aerobic_training_effect != null && (
          <span className="inline-flex items-center gap-1 text-xs text-green-700 bg-green-50 px-2 py-0.5 rounded-full">
            <Timer className="h-3 w-3" />
            TE {fitMetrics.aerobic_training_effect.toFixed(1)}
          </span>
        )}
      </div>
    </button>
  )
}
