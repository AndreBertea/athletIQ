import { Activity, TrendingUp, Clock, Flame } from 'lucide-react'
import type { ActivityStats, EnrichedActivityStats } from '../../services/activityService'

interface DashboardStatsCardsProps {
  stats: ActivityStats | EnrichedActivityStats | null
  useEnrichedData: boolean
  isLoading?: boolean
}

interface KpiCardData {
  label: string
  value: string
  unit: string
  icon: React.ElementType
}

function KpiCardSkeleton() {
  return (
    <div className="bg-gray-50 rounded-lg p-4 border border-gray-100 animate-pulse">
      <div className="flex items-center gap-3">
        <div className="p-2.5 rounded-lg bg-gray-200 h-10 w-10" />
        <div className="flex-1">
          <div className="h-3 w-16 bg-gray-200 rounded mb-2" />
          <div className="h-7 w-20 bg-gray-200 rounded" />
        </div>
      </div>
      <div className="mt-2 h-3 w-24 bg-gray-200 rounded" />
    </div>
  )
}

export default function DashboardStatsCards({ stats, useEnrichedData, isLoading }: DashboardStatsCardsProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 xl:flex xl:flex-col gap-4">
        {[1, 2, 3, 4].map(i => <KpiCardSkeleton key={i} />)}
      </div>
    )
  }

  const enriched = useEnrichedData ? stats as EnrichedActivityStats | null : null
  const original = !useEnrichedData ? stats as ActivityStats | null : null

  const totalActivities = stats?.total_activities || 0
  const distance = useEnrichedData
    ? (enriched?.total_distance_km || 0)
    : (original?.total_distance || 0) / 1000
  const totalTimeHours = useEnrichedData
    ? (enriched?.total_time_hours || 0)
    : (original?.total_time || 0) / 3600
  const hours = Math.floor(totalTimeHours)
  const minutes = Math.round((totalTimeHours - hours) * 60)
  const sportTypes = useEnrichedData
    ? Object.keys(enriched?.activities_by_sport_type || {}).length
    : Object.keys(original?.activities_by_type || {}).length

  const cards: KpiCardData[] = [
    {
      label: 'Activites',
      value: String(totalActivities),
      unit: '',
      icon: Activity,
    },
    {
      label: 'Distance',
      value: distance.toFixed(1),
      unit: 'km',
      icon: TrendingUp,
    },
    {
      label: 'Temps total',
      value: hours > 0 ? `${hours}h${minutes > 0 ? ` ${minutes}` : ''}` : `${minutes}`,
      unit: hours > 0 && minutes > 0 ? 'min' : (hours > 0 ? '' : 'min'),
      icon: Clock,
    },
    {
      label: 'Sports',
      value: String(sportTypes),
      unit: sportTypes === 1 ? 'type' : 'types',
      icon: Flame,
    },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 xl:flex xl:flex-col gap-4">
      {cards.map((card) => (
        <div key={card.label} className="bg-gray-50 rounded-lg p-4 border border-gray-100 hover:border-gray-200 hover:bg-white hover:shadow-sm transition-all duration-200">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-orange-100">
              <card.icon className="h-5 w-5 text-orange-600" />
            </div>
            <div>
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{card.label}</p>
              <div className="flex items-baseline gap-1">
                <p className="text-2xl font-bold text-gray-900">{card.value}</p>
                {card.unit && (
                  <span className="text-sm font-normal text-gray-400">{card.unit}</span>
                )}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
