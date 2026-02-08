import { Activity, TrendingUp, Clock, Zap } from 'lucide-react'
import type { ActivityStats, EnrichedActivityStats } from '../../services/activityService'

interface DashboardStatsCardsProps {
  stats: ActivityStats | EnrichedActivityStats | null
  useEnrichedData: boolean
}

export default function DashboardStatsCards({ stats, useEnrichedData }: DashboardStatsCardsProps) {
  const enriched = useEnrichedData ? stats as EnrichedActivityStats | null : null
  const original = !useEnrichedData ? stats as ActivityStats | null : null

  const distance = useEnrichedData
    ? (enriched?.total_distance_km?.toFixed(1) || 0)
    : (original?.total_distance?.toFixed(1) || 0)

  const totalTime = useEnrichedData
    ? Math.round(enriched?.total_time_hours || 0)
    : Math.round((original?.total_time || 0) / 3600)

  const sportTypes = useEnrichedData
    ? Object.keys(enriched?.activities_by_sport_type || {}).length
    : Object.keys(original?.activities_by_type || {}).length

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      <div className="card">
        <div className="flex items-center">
          <div className="p-3 rounded-lg bg-primary-100">
            <Activity className="h-6 w-6 text-primary-600" />
          </div>
          <div className="ml-4">
            <p className="text-sm font-medium text-gray-500">Activités</p>
            <p className="text-2xl font-semibold text-gray-900">
              {stats?.total_activities || 0}
            </p>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="flex items-center">
          <div className="p-3 rounded-lg bg-blue-100">
            <TrendingUp className="h-6 w-6 text-blue-600" />
          </div>
          <div className="ml-4">
            <p className="text-sm font-medium text-gray-500">Distance totale</p>
            <p className="text-2xl font-semibold text-gray-900">
              {distance} km
            </p>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="flex items-center">
          <div className="p-3 rounded-lg bg-green-100">
            <Clock className="h-6 w-6 text-green-600" />
          </div>
          <div className="ml-4">
            <p className="text-sm font-medium text-gray-500">Temps total</p>
            <p className="text-2xl font-semibold text-gray-900">
              {totalTime}h
            </p>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="flex items-center">
          <div className="p-3 rounded-lg bg-purple-100">
            <Zap className="h-6 w-6 text-purple-600" />
          </div>
          <div className="ml-4">
            <p className="text-sm font-medium text-gray-500">Types de sport</p>
            <p className="text-2xl font-semibold text-gray-900">
              {sportTypes}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
