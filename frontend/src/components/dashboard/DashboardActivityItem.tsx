import { useQuery } from '@tanstack/react-query'
import { Thermometer, Heart, Zap, Footprints, Timer, Flame, Clock, MoveVertical, ArrowLeftRight, Wind, Droplets, Cloud } from 'lucide-react'
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
    enabled: fitMetricsProp === undefined && activity.has_garmin === true,
  })

  const weather = weatherProp ?? weatherQuery
  const fitMetrics = fitMetricsProp ?? fitMetricsQuery

  const distanceKm = (activity.distance_m / 1000).toFixed(1)
  const duration = formatDuration(activity.moving_time_s)
  const badgeColor = sportBadgeColors[activity.sport_type] || 'bg-gray-100 text-gray-700'

  // WMO weather code → label
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

        {/* Météo — température + description */}
        {weather?.temperature_c != null && (
          <span className="inline-flex items-center gap-1 text-xs text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full">
            <Thermometer className="h-3 w-3" />
            {weather.temperature_c.toFixed(0)}°C
            {weatherLabel(weather.weather_code) && (
              <span className="text-amber-500 ml-0.5">· {weatherLabel(weather.weather_code)}</span>
            )}
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

        {/* FIT — Training Effect (aérobie + anaérobie) */}
        {fitMetrics?.aerobic_training_effect != null && (
          <span className="inline-flex items-center gap-1 text-xs text-green-700 bg-green-50 px-2 py-0.5 rounded-full">
            <Timer className="h-3 w-3" />
            TE {fitMetrics.aerobic_training_effect.toFixed(1)}
            {fitMetrics.anaerobic_training_effect != null && (
              <> / {fitMetrics.anaerobic_training_effect.toFixed(1)}</>
            )}
          </span>
        )}

        {/* FIT — Oscillation verticale */}
        {fitMetrics?.vertical_oscillation_avg != null && (
          <span className="inline-flex items-center gap-1 text-xs text-teal-700 bg-teal-50 px-2 py-0.5 rounded-full">
            <MoveVertical className="h-3 w-3" />
            OV {fitMetrics.vertical_oscillation_avg.toFixed(1)} cm
          </span>
        )}

        {/* FIT — Équilibre G/D */}
        {fitMetrics?.stance_time_balance_avg != null && (
          <span className="inline-flex items-center gap-1 text-xs text-slate-700 bg-slate-100 px-2 py-0.5 rounded-full">
            <ArrowLeftRight className="h-3 w-3" />
            G/D {fitMetrics.stance_time_balance_avg.toFixed(1)}%
          </span>
        )}

        {/* Calories */}
        {activity.calories_kcal > 0 && (
          <span className="inline-flex items-center gap-1 text-xs text-orange-700 bg-orange-50 px-2 py-0.5 rounded-full">
            <Flame className="h-3 w-3" />
            {Math.round(activity.calories_kcal)} kcal
          </span>
        )}

        {/* Temps total (si pauses significatives) */}
        {activity.elapsed_time_s > 0 && activity.elapsed_time_s - activity.moving_time_s > 60 && (
          <span className="inline-flex items-center gap-1 text-xs text-gray-600 bg-gray-100 px-2 py-0.5 rounded-full">
            <Clock className="h-3 w-3" />
            Total {formatDuration(activity.elapsed_time_s)}
          </span>
        )}

        {/* Météo — vent */}
        {weather?.wind_speed_kmh != null && weather.wind_speed_kmh > 0 && (
          <span className="inline-flex items-center gap-1 text-xs text-cyan-700 bg-cyan-50 px-2 py-0.5 rounded-full">
            <Wind className="h-3 w-3" />
            {weather.wind_speed_kmh.toFixed(0)} km/h
          </span>
        )}

        {/* Météo — humidité */}
        {weather?.humidity_pct != null && (
          <span className="inline-flex items-center gap-1 text-xs text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full">
            <Droplets className="h-3 w-3" />
            {weather.humidity_pct.toFixed(0)}%
          </span>
        )}

        {/* Météo — précipitations */}
        {weather?.precipitation_mm != null && weather.precipitation_mm > 0 && (
          <span className="inline-flex items-center gap-1 text-xs text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-full">
            <Cloud className="h-3 w-3" />
            {weather.precipitation_mm.toFixed(1)} mm
          </span>
        )}
      </div>
    </button>
  )
}
