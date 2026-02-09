import { Activity } from 'lucide-react'
import DashboardActivityItem from './DashboardActivityItem'
import type { EnrichedActivity } from '../../services/activityService'
import type { ActivityWeather } from '../../services/dataService'

interface DashboardActivityListProps {
  activities: EnrichedActivity[]
  isLoading: boolean
  weatherMap?: Map<string, ActivityWeather>
}

export default function DashboardActivityList({ activities, isLoading, weatherMap }: DashboardActivityListProps) {
  const displayedActivities = activities.slice(0, 5)

  return (
    <div className="bg-white rounded-xl border border-gray-200/60 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-emerald-500" />
          <h3 className="text-base font-semibold text-gray-900">Activités récentes</h3>
        </div>
        {activities.length > 5 && (
          <span className="text-sm font-medium text-orange-600 hover:text-orange-700 cursor-pointer">
            Voir toutes →
          </span>
        )}
      </div>

      {/* Loading */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12 text-gray-400">
          <div className="h-6 w-6 border-2 border-gray-200 border-t-orange-500 rounded-full animate-spin" />
          <span className="ml-3 text-sm">Chargement...</span>
        </div>
      ) : displayedActivities.length === 0 ? (
        /* Empty state */
        <div className="flex flex-col items-center justify-center py-12 text-gray-400">
          <Activity className="h-10 w-10 mb-3 text-gray-300" />
          <p className="text-sm font-medium text-gray-500">Aucune activité récente</p>
          <p className="text-xs text-gray-400 mt-1">Les activités enrichies apparaîtront ici après synchronisation</p>
        </div>
      ) : (
        /* Activity list */
        <div className="divide-y divide-gray-100">
          {displayedActivities.map((activity) => (
            <DashboardActivityItem
              key={activity.activity_id}
              activity={activity}
              weather={weatherMap?.get(String(activity.activity_id)) ?? undefined}
            />
          ))}
        </div>
      )}
    </div>
  )
}
