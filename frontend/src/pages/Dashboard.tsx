import { useState, useMemo } from 'react'
import { useQuery, useQueries } from '@tanstack/react-query'
import { Trophy } from 'lucide-react'
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
  { value: 'distance', label: 'Distance (km)', formatter: (v: number) => `${(v ?? 0).toFixed(1)} km` },
  { value: 'duration', label: 'Durée (h)', formatter: (v: number) => `${((v ?? 0) / 3600).toFixed(1)}h` },
  { value: 'pace', label: 'Pace (min/km)', formatter: (v: number) => `${(v ?? 0).toFixed(1)} min/km` },
  { value: 'elevation', label: 'Dénivelé (m)', formatter: (v: number) => `${(v ?? 0).toFixed(0)} m` },
]

const periodOptions = [
  { days: 7, label: '7 derniers jours' },
  { days: 30, label: '30 derniers jours' },
  { days: 90, label: '3 mois' },
  { days: 365, label: 'Cette année' },
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

export default function Dashboard() {
  const [selectedPeriod, setSelectedPeriod] = useState(30)
  const [useEnrichedData, setUseEnrichedData] = useState(true)
  const [selectedSportFilter, setSelectedSportFilter] = useState('all')
  const [selectedMetric, setSelectedMetric] = useState('distance')
  const [chartInterval, setChartInterval] = useState<'day' | 'week' | 'month'>('day')

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

  const { data: chronicLoadData, isLoading: chronicLoadLoading } = useQuery({
    queryKey: ['chronic-load', selectedPeriod],
    queryFn: () => {
      const end = new Date().toISOString().split('T')[0]
      const start = new Date()
      start.setDate(start.getDate() - selectedPeriod)
      return chronicLoadService.getChronicLoadData(start.toISOString().split('T')[0], end)
    },
    staleTime: 10 * 60_000,
  })

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

  const filteredActivities = useMemo((): EnrichedActivity[] => {
    if (!useEnrichedData) return []
    if (selectedSportFilter === 'all') return enrichedItems
    const targets = sportTypeMapping[selectedSportFilter] || []
    return enrichedItems.filter(a => targets.includes(a.sport_type))
  }, [enrichedItems, selectedSportFilter, useEnrichedData])

  const chartData = useMemo(
    () => generateChartData(filteredActivities, selectedSportFilter, chartInterval),
    [filteredActivities, selectedSportFilter, chartInterval],
  )

  // --- Rendu ---

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500" />
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Tableau de bord</h1>
          <p className="mt-2 text-gray-600">
            Aperçu de vos performances sportives
            {useEnrichedData && (
              <span className="ml-2 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                <Trophy className="h-3 w-3 mr-1" />
                Données enrichies
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <label className="text-sm font-medium text-gray-700">Source :</label>
            <button onClick={() => setUseEnrichedData(true)} className={`px-3 py-1.5 text-sm rounded-md transition-colors ${useEnrichedData ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}>
              Enrichies
            </button>
            <button onClick={() => setUseEnrichedData(false)} className={`px-3 py-1.5 text-sm rounded-md transition-colors ${!useEnrichedData ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}>
              Originales
            </button>
          </div>
          {stravaStatus?.connected && stravaStatus.last_sync && (
            <div className="text-sm text-gray-500 text-right">
              <div className="font-medium">Dernière mise à jour :</div>
              <div>{new Date(stravaStatus.last_sync).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
            </div>
          )}
        </div>
      </div>

      {/* Filtres */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-medium text-gray-900">Période d'analyse</h3>
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <label className="text-sm font-medium text-gray-700">Filtrer par :</label>
              <select value={selectedSportFilter} onChange={(e) => setSelectedSportFilter(e.target.value)} className="px-3 py-1.5 text-sm rounded-md border border-gray-300 focus:border-primary-500 focus:ring-primary-500">
                {sportFilterOptions.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
              </select>
            </div>
            <div className="flex items-center space-x-2">
              <label className="text-sm font-medium text-gray-700">Analyser les :</label>
              <div className="flex space-x-2">
                {periodOptions.map((p) => (
                  <button key={p.days} onClick={() => setSelectedPeriod(p.days)} className={`px-3 py-1.5 text-sm rounded-md transition-colors ${selectedPeriod === p.days ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}>
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
        <div className="text-sm text-gray-600">
          <strong>Période sélectionnée :</strong> {periodOptions.find(p => p.days === selectedPeriod)?.label || `${selectedPeriod} jours`}
          {selectedSportFilter !== 'all' && (
            <span className="ml-2"> • <strong>Filtre :</strong> {sportFilterOptions.find(o => o.value === selectedSportFilter)?.label}</span>
          )}
        </div>
      </div>

      {/* Stats Cards */}
      <DashboardStatsCards stats={filteredStats ?? null} useEnrichedData={useEnrichedData} />

      {/* Graphique Performance */}
      <DashboardPerformanceChart chartData={chartData} selectedMetric={selectedMetric} onMetricChange={setSelectedMetric} chartInterval={chartInterval} onIntervalChange={setChartInterval} metricOptions={metricOptions} isLoading={isLoading} />

      {/* Garmin Daily Monitor */}
      <GarminDailyMonitor
        data={garminDaily ?? []}
        isLoading={garminDailyLoading}
        isConnected={garminConnected}
      />

      {/* Charge Chronique */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-medium text-gray-900">Charge Chronique d'Entraînement</h3>
          <div className="text-sm text-gray-500">Modèle de Banister (TRIMP)</div>
        </div>
        <ChronicLoadChart data={chronicLoadData || []} isLoading={chronicLoadLoading} />
      </div>

      {/* Liste d'activités récentes */}
      <DashboardActivityList
        activities={enrichedItems}
        isLoading={!recentEnrichedActivities && !enrichedStats}
        weatherMap={weatherMap}
      />

      {/* Insights & Corrélations */}
      <CorrelationInsights
        activities={enrichedItems}
        garminDaily={garminDaily ?? []}
        weatherData={weatherMap}
      />

      {/* Plans d'Entraînement */}
      <DashboardWorkoutPlans workoutPlans={workoutPlans} />
    </div>
  )
}
