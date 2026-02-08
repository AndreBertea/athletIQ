import { Activity, Loader2 } from 'lucide-react'
import DashboardActivityItem from './DashboardActivityItem'
import type { EnrichedActivity } from '../../services/activityService'
import type { ActivityWeather } from '../../services/dataService'

interface DashboardActivityListProps {
  activities: EnrichedActivity[]
  isLoading: boolean
  weatherMap?: Map<string, ActivityWeather>
}

export default function DashboardActivityList({ activities, isLoading, weatherMap }: DashboardActivityListProps) {
  return (
    <div className="card">
      <div className="flex items-center space-x-2 mb-4">
        <Activity className="h-5 w-5 text-primary-500" />
        <h3 className="text-lg font-medium text-gray-900">Activités récentes</h3>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-32">
          <Loader2 className="h-8 w-8 animate-spin text-primary-500" />
        </div>
      ) : activities.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-gray-400">
          <Activity className="h-12 w-12 mb-3" />
          <p className="text-sm">Aucune activité enrichie</p>
        </div>
      ) : (
        <div className="max-h-[600px] overflow-y-auto space-y-3 pr-1">
          {activities.map((activity) => (
            <DashboardActivityItem
              key={activity.activity_id}
              activity={activity}
              onClick={() => {}}
              weather={weatherMap?.get(String(activity.activity_id)) ?? undefined}
            />
          ))}
        </div>
      )}
    </div>
  )
}
