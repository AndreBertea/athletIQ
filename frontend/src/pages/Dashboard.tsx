import { useState, useMemo } from 'react'
import { useQuery, useQueries } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import DashboardStatsCards from '../components/dashboard/DashboardStatsCards'
import DashboardPerformanceChart from '../components/dashboard/DashboardPerformanceChart'
import DashboardWorkoutPlans from '../components/dashboard/DashboardWorkoutPlans'
import GarminDailyMonitor from '../components/dashboard/GarminDailyMonitor'
import DashboardActivityList from '../components/dashboard/DashboardActivityList'
import CorrelationInsights from '../components/dashboard/CorrelationInsights'
import ChronicLoadChart from '../components/ChronicLoadChart'
import { activityService } from '../services/activityService'
import type { ActivityStats, EnrichedActivityStats, EnrichedActivity } from '../services/activityService'
import { authService } from '../services/authService'
import { workoutPlanService } from '../services/workoutPlanService'
import { chronicLoadService } from '../services/chronicLoadService'
import { garminService } from '../services/garminService'
import { dataService } from '../services/dataService'
import type { ActivityWeather } from '../services/dataService'
import { formatBucketLabel, getBucketKey, GRANULARITY_LABELS, type TimeGranularity } from '../utils/timeBuckets'

// --- Options statiques ---

const sportFilterOptions = [
  { value: 'all', label: 'Toutes les activités' },
  { value: 'racket', label: 'Sports de raquette' },
  { value: 'swim', label: 'Natation' },
  { value: 'bike', label: 'Vélo' },
  { value: 'run', label: 'Course à pied' },
  { value: 'trailrun', label: 'Trail running' },
  { value: 'all_running', label: 'Toutes les courses (Run + TrailRun)' },
]

const metricOptions = [
  { value: 'distance', label: 'Distance (km)', shortLabel: 'Dist.', formatter: (v: number) => `${(v ?? 0).toFixed(1)} km` },
  { value: 'duration', label: 'Durée (h)', shortLabel: 'Durée', formatter: (v: number) => `${((v ?? 0) / 3600).toFixed(1)}h` },
  { value: 'pace', label: 'Pace (min/km)', shortLabel: 'Pace', formatter: (v: number) => `${(v ?? 0).toFixed(1)} min/km` },
  { value: 'elevation', label: 'Dénivelé (m)', shortLabel: 'D+', formatter: (v: number) => `${(v ?? 0).toFixed(0)} m` },
]

const periodOptions = [
  { days: 7, label: '7j' },
  { days: 30, label: '30j' },
  { days: 90, label: '3m' },
  { days: 180, label: '6m' },
  { days: 365, label: '1a' },
]

const granularityOptions: Array<{ value: TimeGranularity; label: string }> = [
  { value: 'day', label: GRANULARITY_LABELS.day },
  { value: 'week', label: GRANULARITY_LABELS.week },
  { value: 'month', label: GRANULARITY_LABELS.month },
]

const sportTypeMapping: Record<string, string[]> = {
  racket: ['RacketSport', 'Tennis', 'Badminton', 'Squash'],
  swim: ['swim', 'Swim', 'Swimming'],
  bike: ['Ride', 'Bike', 'Cycling'],
  run: ['run', 'Run'],
  trailrun: ['TrailRun'],
  all_running: ['run', 'Run', 'TrailRun'],
}

// --- Helpers ---

function filterEnrichedStats(rawStats: EnrichedActivityStats, sportFilter: string): EnrichedActivityStats {
  const stats = { ...rawStats }
  const targetTypes = sportTypeMapping[sportFilter] || []

  const filtered: Record<string, Record<string, number>> = { activities: {}, distance: {}, time: {}, pace: {} }
  for (const sport of Object.keys(stats.activities_by_sport_type)) {
    if (targetTypes.includes(sport)) {
      filtered.activities[sport] = stats.activities_by_sport_type[sport]
      filtered.distance[sport] = stats.distance_by_sport_type?.[sport] || 0
      filtered.time[sport] = stats.time_by_sport_type?.[sport] || 0
      filtered.pace[sport] = stats.average_pace_by_sport?.[sport] || 0
    }
  }
  stats.activities_by_sport_type = filtered.activities
  stats.distance_by_sport_type = filtered.distance
  stats.time_by_sport_type = filtered.time
  stats.average_pace_by_sport = filtered.pace
  stats.total_activities = Object.values(filtered.activities).reduce((a, b) => a + b, 0)
  stats.total_distance_km = Object.values(filtered.distance).reduce((a, b) => a + b, 0)
  stats.total_time_hours = Object.values(filtered.time).reduce((a, b) => a + b, 0)
  return stats
}

function filterOriginalStats(rawStats: ActivityStats, sportFilter: string): ActivityStats {
  const stats = { ...rawStats }
  const targetTypes = sportTypeMapping[sportFilter] || []

  const filtered: Record<string, Record<string, number>> = { activities: {}, distance: {}, time: {} }
  for (const type of Object.keys(stats.activities_by_type)) {
    if (targetTypes.includes(type)) {
      filtered.activities[type] = stats.activities_by_type[type]
      filtered.distance[type] = (stats as ActivityStats & { distance_by_type?: Record<string, number> }).distance_by_type?.[type] || 0
      filtered.time[type] = (stats as ActivityStats & { time_by_type?: Record<string, number> }).time_by_type?.[type] || 0
    }
  }
  stats.activities_by_type = filtered.activities
  stats.total_activities = Object.values(filtered.activities).reduce((a, b) => a + b, 0)
  stats.total_distance = Object.values(filtered.distance).reduce((a, b) => a + b, 0)
  stats.total_time = Object.values(filtered.time).reduce((a, b) => a + b, 0)
  return stats
}

function generateChartData(activities: EnrichedActivity[], sportFilter: string, interval: 'day' | 'week' | 'month') {
  const targetTypes = sportFilter === 'all'
    ? ['run', 'Run', 'TrailRun']
    : (sportTypeMapping[sportFilter] || []).filter(t => ['run', 'Run', 'TrailRun'].includes(t))

  const running = activities
    .filter(a => targetTypes.includes(a.sport_type))
    .sort((a, b) => new Date(a.start_date_utc).getTime() - new Date(b.start_date_utc).getTime())

  if (running.length === 0) return []

  const grouped: Record<string, EnrichedActivity[]> = {}
  for (const activity of running) {
    const date = new Date(activity.start_date_utc)
    let key: string
    if (interval === 'day') {
      key = date.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' })
    } else if (interval === 'week') {
      const dow = date.getDay()
      const ws = new Date(date.getTime() - (dow === 0 ? 6 : dow - 1) * 86400000)
      key = `Sem. ${ws.getDate()}/${ws.getMonth() + 1}`
    } else {
      key = date.toLocaleDateString('fr-FR', { month: 'short', year: '2-digit' })
    }
    ;(grouped[key] ??= []).push(activity)
  }

  return Object.entries(grouped).map(([date, acts]) => {
    const dist = acts.reduce((s, a) => s + ((a.distance_m || 0) / 1000), 0)
    const dur = acts.reduce((s, a) => s + (a.moving_time_s || 0), 0)
    const elev = acts.reduce((s, a) => s + (a.elev_gain_m || 0), 0)
    const pace = dist > 0 ? (dur / 60) / dist : 0
    return {
      date,
      distance: Number.isFinite(dist) ? dist : 0,
      duration: Number.isFinite(dur) ? dur : 0,
      pace: Number.isFinite(pace) ? pace : 0,
      elevation: Number.isFinite(elev) ? elev : 0,
    }
  })
}

type ChronicLoadPoint = {
  date: string
  chronicLoad: number
  acuteLoad: number
  trainingStressBalance: number
  chronicLoadEdwards: number
  acuteLoadEdwards: number
  tsbEdwards: number
}

function aggregateChronicLoadData(data: ChronicLoadPoint[], granularity: TimeGranularity): ChronicLoadPoint[] {
  if (!data || data.length === 0) return []
  if (granularity === 'day') return data

  const buckets = new Map<string, {
    count: number
    sums: Omit<ChronicLoadPoint, 'date'>
  }>()

  for (const entry of data) {
    const key = getBucketKey(entry.date, granularity)
    const bucket = buckets.get(key) ?? {
      count: 0,
      sums: {
        chronicLoad: 0,
        acuteLoad: 0,
        trainingStressBalance: 0,
        chronicLoadEdwards: 0,
        acuteLoadEdwards: 0,
        tsbEdwards: 0,
      },
    }
    bucket.count += 1
    bucket.sums.chronicLoad += entry.chronicLoad
    bucket.sums.acuteLoad += entry.acuteLoad
    bucket.sums.trainingStressBalance += entry.trainingStressBalance
    bucket.sums.chronicLoadEdwards += entry.chronicLoadEdwards
    bucket.sums.acuteLoadEdwards += entry.acuteLoadEdwards
    bucket.sums.tsbEdwards += entry.tsbEdwards
    buckets.set(key, bucket)
  }

  return Array.from(buckets.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, bucket]) => ({
      date: formatBucketLabel(key, granularity),
      chronicLoad: bucket.sums.chronicLoad / bucket.count,
      acuteLoad: bucket.sums.acuteLoad / bucket.count,
      trainingStressBalance: bucket.sums.trainingStressBalance / bucket.count,
      chronicLoadEdwards: bucket.sums.chronicLoadEdwards / bucket.count,
      acuteLoadEdwards: bucket.sums.acuteLoadEdwards / bucket.count,
      tsbEdwards: bucket.sums.tsbEdwards / bucket.count,
    }))
}

export default function Dashboard() {
  const [selectedPeriod, setSelectedPeriod] = useState(30)
  const [useEnrichedData, setUseEnrichedData] = useState(true)
  const [selectedSportFilter, setSelectedSportFilter] = useState('all')
  const [selectedMetric, setSelectedMetric] = useState('distance')
  const [chartGranularity, setChartGranularity] = useState<TimeGranularity>('day')

  // --- Queries existantes ---

  const { data: enrichedStats, isLoading: enrichedLoading } = useQuery({
    queryKey: ['enriched-activity-stats', selectedPeriod, selectedSportFilter],
    queryFn: () => activityService.getEnrichedActivityStats(selectedPeriod),
    staleTime: 5 * 60_000,
    enabled: useEnrichedData,
  })

  const { data: originalStats, isLoading: originalLoading } = useQuery({
    queryKey: ['activity-stats', selectedPeriod, selectedSportFilter],
    queryFn: () => activityService.getActivityStats(selectedPeriod),
    staleTime: 5 * 60_000,
    enabled: !useEnrichedData,
  })

  const { data: stravaStatus } = useQuery({
    queryKey: ['strava-status'],
    queryFn: () => authService.getStravaStatus(),
    staleTime: 30_000,
  })

  const { data: workoutPlans = [] } = useQuery({
    queryKey: ['workout-plans-dashboard'],
    queryFn: () => workoutPlanService.getWorkoutPlans(),
    staleTime: 5 * 60_000,
  })

  const { data: chronicLoadResult, isLoading: chronicLoadLoading } = useQuery({
    queryKey: ['chronic-load', selectedPeriod],
    queryFn: () => {
      const end = new Date().toISOString().split('T')[0]
      const start = new Date()
      start.setDate(start.getDate() - selectedPeriod)
      return chronicLoadService.getChronicLoadDataWithRhr(start.toISOString().split('T')[0], end)
    },
    staleTime: 10 * 60_000,
  })

  const chronicLoadData = chronicLoadResult?.data
  const lastRhrDelta7d = chronicLoadResult?.lastRhrDelta7d

  // --- Nouvelles queries ---

  const { data: garminStatus } = useQuery({
    queryKey: ['garmin-status'],
    queryFn: () => garminService.getGarminStatus(),
    staleTime: 30_000,
  })

  const garminConnected = garminStatus?.connected ?? false

  const { data: garminDaily, isLoading: garminDailyLoading } = useQuery({
    queryKey: ['garmin-daily-dashboard', selectedPeriod],
    queryFn: () => {
      const end = new Date().toISOString().split('T')[0]
      const start = new Date()
      start.setDate(start.getDate() - selectedPeriod)
      return garminService.getGarminDaily(start.toISOString().split('T')[0], end)
    },
    staleTime: 5 * 60_000,
    enabled: garminConnected,
  })

  const { data: recentEnrichedActivities } = useQuery({
    queryKey: ['recent-enriched-activities'],
    queryFn: () => activityService.getEnrichedActivities({ page: 1, per_page: 15 }),
    staleTime: 5 * 60_000,
  })

  const enrichedItems = recentEnrichedActivities?.items ?? []

  const performanceDateFrom = useMemo(() => {
    const start = new Date()
    start.setDate(start.getDate() - selectedPeriod)
    return start.toISOString().split('T')[0]
  }, [selectedPeriod])

  const { data: performanceActivities = [], isLoading: performanceLoading } = useQuery({
    queryKey: ['performance-activities', selectedPeriod],
    queryFn: () => activityService.getAllEnrichedActivities(undefined, performanceDateFrom),
    staleTime: 5 * 60_000,
  })

  // Charger la météo pour chaque activité récente (pour CorrelationInsights)
  const weatherQueries = useQueries({
    queries: enrichedItems.map((act) => ({
      queryKey: ['weather', act.activity_id],
      queryFn: () => dataService.getWeather(String(act.activity_id)),
      staleTime: 30 * 60_000,
      retry: false,
    })),
  })

  const weatherMap = useMemo(() => {
    const map = new Map<string, ActivityWeather>()
    enrichedItems.forEach((act, i) => {
      const result = weatherQueries[i]
      if (result?.data) {
        map.set(String(act.activity_id), result.data)
      }
    })
    return map
  }, [enrichedItems, weatherQueries])

  // --- Données dérivées ---

  const isLoading = useEnrichedData ? enrichedLoading : originalLoading
  const filteredStats = useMemo((): ActivityStats | EnrichedActivityStats | null | undefined => {
    if (useEnrichedData) {
      if (!enrichedStats || selectedSportFilter === 'all') return enrichedStats
      return filterEnrichedStats(enrichedStats, selectedSportFilter)
    } else {
      if (!originalStats || selectedSportFilter === 'all') return originalStats
      return filterOriginalStats(originalStats, selectedSportFilter)
    }
  }, [enrichedStats, originalStats, selectedSportFilter, useEnrichedData])

  const chartData = useMemo(
    () => generateChartData(performanceActivities, selectedSportFilter, chartInterval),
    [performanceActivities, selectedSportFilter, chartInterval],
  )

  // --- Rendu ---

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 text-gray-400">
        <div className="h-6 w-6 border-2 border-gray-200 border-t-orange-500 rounded-full animate-spin" />
        <span className="ml-3 text-sm">Chargement...</span>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Votre résumé</h1>
          <p className="text-sm text-gray-500 mt-1">
            {new Intl.DateTimeFormat('fr-FR', {
              weekday: 'long',
              day: 'numeric',
              month: 'long',
              year: 'numeric',
            }).format(new Date())}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Toggle source compact */}
          <div className="inline-flex items-center bg-gray-100 rounded-lg p-1 gap-0.5">
            <button
              onClick={() => setUseEnrichedData(true)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200 ${
                useEnrichedData
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Enrichies
            </button>
            <button
              onClick={() => setUseEnrichedData(false)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200 ${
                !useEnrichedData
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Originales
            </button>
          </div>
          {/* Badge sync */}
          {stravaStatus?.connected && stravaStatus.last_sync && (
            <div className="flex items-center gap-1.5 text-xs text-gray-400">
              <RefreshCw className="h-3 w-3" />
              <span>
                {(() => {
                  const diff = Date.now() - new Date(stravaStatus.last_sync).getTime()
                  const mins = Math.floor(diff / 60000)
                  if (mins < 1) return 'Sync à l\'instant'
                  if (mins < 60) return `Sync il y a ${mins}min`
                  const hours = Math.floor(mins / 60)
                  if (hours < 24) return `Sync il y a ${hours}h`
                  return `Sync il y a ${Math.floor(hours / 24)}j`
                })()}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Filtres — sticky bar */}
      <div className="sticky top-0 z-10 bg-gray-50/80 backdrop-blur-sm border-b border-gray-200/60 -mx-4 px-4 py-3 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          {/* Toggle période */}
          <div className="inline-flex items-center bg-gray-100 rounded-lg p-1 gap-0.5">
            {periodOptions.map((p) => (
              <button
                key={p.days}
                onClick={() => setSelectedPeriod(p.days)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200 ${
                  selectedPeriod === p.days
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          {/* Select sport */}
          <select
            value={selectedSportFilter}
            onChange={(e) => setSelectedSportFilter(e.target.value)}
            className="text-sm rounded-lg border-gray-200 bg-white px-3 py-1.5 pr-8 focus:ring-orange-500 focus:border-orange-500 cursor-pointer"
          >
            {sportFilterOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Zone KPIs + Performance Chart */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-1">
          <DashboardStatsCards stats={filteredStats ?? null} useEnrichedData={useEnrichedData} isLoading={isLoading} />
        </div>
        <div className="xl:col-span-2">
          <DashboardPerformanceChart chartData={chartData} selectedMetric={selectedMetric} onMetricChange={setSelectedMetric} chartInterval={chartInterval} onIntervalChange={setChartInterval} metricOptions={metricOptions} isLoading={isLoading || performanceLoading} selectedSportLabel={sportFilterOptions.find(o => o.value === selectedSportFilter)?.label || 'Toutes les activités'} />
        </div>
      </div>

      {/* Garmin Daily Monitor */}
      <GarminDailyMonitor
        data={garminDaily ?? []}
        isLoading={garminDailyLoading}
        isConnected={garminConnected}
      />

      {/* Charge Chronique */}
      <ChronicLoadChart data={chronicLoadData || []} isLoading={chronicLoadLoading} rhrDelta7d={lastRhrDelta7d} />

      {/* Zone Activités + Insights */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3">
          <DashboardActivityList
            activities={enrichedItems}
            isLoading={!recentEnrichedActivities && !enrichedStats}
            weatherMap={weatherMap}
          />
        </div>
        <div className="lg:col-span-2">
          <CorrelationInsights
            activities={performanceActivities}
            garminDaily={garminDaily ?? []}
            weatherData={weatherMap}
            trainingLoadData={chronicLoadData}
          />
        </div>
      </div>

      {/* Plans d'Entraînement */}
      <DashboardWorkoutPlans workoutPlans={workoutPlans} />
    </div>
  )
}
