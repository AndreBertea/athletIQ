import { useQuery } from '@tanstack/react-query'
import { Activity, Clock, TrendingUp, Target, Trophy, Zap, Calendar, CheckCircle, ChevronDown, ChevronUp } from 'lucide-react'
import { activityService } from '../services/activityService'
import { authService } from '../services/authService'
import { workoutPlanService } from '../services/workoutPlanService'
import { chronicLoadService } from '../services/chronicLoadService'
import { useState } from 'react'
import { AreaChart } from '../components/ui/area-chart'
import ChronicLoadChart from '../components/ChronicLoadChart'
import RacePredictor from '../components/RacePredictor'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'

export default function Dashboard() {
  const [selectedPeriod, setSelectedPeriod] = useState<number>(30)
  const [useEnrichedData, setUseEnrichedData] = useState<boolean>(true)
  const [selectedSportFilter, setSelectedSportFilter] = useState<string>('all')
  const [showMoreWorkoutPlans, setShowMoreWorkoutPlans] = useState<boolean>(false)
  const [selectedMetric, setSelectedMetric] = useState<string>('distance')
  const [chartInterval, setChartInterval] = useState<'day' | 'week' | 'month'>('day')

  // Options de filtres par type de sport
  const sportFilterOptions = [
    { value: 'all', label: 'Toutes les activités' },
    { value: 'racket', label: 'Sports de raquette' },
    { value: 'swim', label: 'Natation' },
    { value: 'bike', label: 'Vélo' },
    { value: 'run', label: 'Course à pied' },
    { value: 'trailrun', label: 'Trail running' },
    { value: 'all_running', label: 'Toutes les courses (Run + TrailRun)' }
  ]

  // Options de métriques pour le graphique
  const metricOptions = [
    { value: 'distance', label: 'Distance (km)', formatter: (value: number) => `${typeof value === 'number' ? value.toFixed(1) : '0.0'} km` },
    { value: 'duration', label: 'Durée (h)', formatter: (value: number) => `${typeof value === 'number' ? (value / 3600).toFixed(1) : '0.0'}h` },
    { value: 'pace', label: 'Pace (min/km)', formatter: (value: number) => `${typeof value === 'number' ? value.toFixed(1) : '0.0'} min/km` },
    { value: 'elevation', label: 'Dénivelé (m)', formatter: (value: number) => `${typeof value === 'number' ? value.toFixed(0) : '0'} m` }
  ]

  // Query pour les données enrichies (recommandé)
  const { data: enrichedStats, isLoading: enrichedStatsLoading } = useQuery({
    queryKey: ['enriched-activity-stats', selectedPeriod, selectedSportFilter],
    queryFn: () => activityService.getEnrichedActivityStats(selectedPeriod),
    staleTime: 5 * 60 * 1000, // 5 minutes
    enabled: useEnrichedData
  })

  // Query pour les données originales (fallback)
  const { data: originalStats, isLoading: originalStatsLoading } = useQuery({
    queryKey: ['activity-stats', selectedPeriod, selectedSportFilter],
    queryFn: () => activityService.getActivityStats(selectedPeriod),
    staleTime: 5 * 60 * 1000, // 5 minutes
    enabled: !useEnrichedData
  })

  const { data: stravaStatus } = useQuery({
    queryKey: ['strava-status'],
    queryFn: () => authService.getStravaStatus(),
    staleTime: 30 * 1000 // 30 secondes
  })

  // Query pour les plans d'entraînement
  const { data: workoutPlans = [] } = useQuery({
    queryKey: ['workout-plans-dashboard'],
    queryFn: () => workoutPlanService.getWorkoutPlans(),
    staleTime: 5 * 60 * 1000 // 5 minutes
  })

  // Query pour les données de charge chronique
  const { data: chronicLoadData, isLoading: chronicLoadLoading } = useQuery({
    queryKey: ['chronic-load', selectedPeriod],
    queryFn: () => {
      const endDate = new Date().toISOString().split('T')[0]
      const startDate = new Date()
      startDate.setDate(startDate.getDate() - selectedPeriod)
      return chronicLoadService.getChronicLoadData(
        startDate.toISOString().split('T')[0],
        endDate
      )
    },
    staleTime: 10 * 60 * 1000, // 10 minutes
    enabled: true
  })

  // Utiliser les données enrichies par défaut
  const stats = useEnrichedData ? enrichedStats : originalStats
  const isLoading = useEnrichedData ? enrichedStatsLoading : originalStatsLoading

  // Fonction pour filtrer les données selon le sport sélectionné
  const getFilteredStats = (rawStats: any) => {
    if (!rawStats || selectedSportFilter === 'all') return rawStats

    const filteredStats = { ...rawStats }
    
    if (useEnrichedData) {
      // Filtrage pour les données enrichies
      const sportTypeMapping: Record<string, string[]> = {
        'racket': ['RacketSport', 'Tennis', 'Badminton', 'Squash'],
        'swim': ['swim', 'Swim', 'Swimming'],
        'bike': ['Ride', 'Bike', 'Cycling'],
        'run': ['run', 'Run'],
        'trailrun': ['TrailRun'],
        'all_running': ['run', 'Run', 'TrailRun']
      }

      const targetSports = sportTypeMapping[selectedSportFilter] || []
      
      // Filtrer les activités par type de sport
      if (filteredStats.activities_by_sport_type) {
        const filteredActivities: Record<string, number> = {}
        const filteredDistance: Record<string, number> = {}
        const filteredTime: Record<string, number> = {}
        const filteredPace: Record<string, number> = {}

        Object.keys(filteredStats.activities_by_sport_type).forEach(sport => {
          if (targetSports.includes(sport)) {
            filteredActivities[sport] = filteredStats.activities_by_sport_type[sport]
            filteredDistance[sport] = filteredStats.distance_by_sport_type?.[sport] || 0
            filteredTime[sport] = filteredStats.time_by_sport_type?.[sport] || 0
            filteredPace[sport] = filteredStats.average_pace_by_sport?.[sport] || 0
          }
        })

        filteredStats.activities_by_sport_type = filteredActivities
        filteredStats.distance_by_sport_type = filteredDistance
        filteredStats.time_by_sport_type = filteredTime
        filteredStats.average_pace_by_sport = filteredPace
        filteredStats.total_activities = Object.values(filteredActivities).reduce((a: number, b: number) => a + b, 0)
        filteredStats.total_distance_km = Object.values(filteredDistance).reduce((a: number, b: number) => a + b, 0)
        filteredStats.total_time_hours = Object.values(filteredTime).reduce((a: number, b: number) => a + b, 0)
      }
    } else {
      // Filtrage pour les données originales
      const activityTypeMapping: Record<string, string[]> = {
        'racket': ['RacketSport', 'Tennis', 'Badminton'],
        'swim': ['swim', 'Swim', 'Swimming'],
        'bike': ['Ride', 'Bike'],
        'run': ['run', 'Run'],
        'trailrun': ['TrailRun'],
        'all_running': ['run', 'Run', 'TrailRun']
      }

      const targetTypes = activityTypeMapping[selectedSportFilter] || []
      
      if (filteredStats.activities_by_type) {
        const filteredActivities: Record<string, number> = {}
        const filteredDistance: Record<string, number> = {}
        const filteredTime: Record<string, number> = {}
        
        Object.keys(filteredStats.activities_by_type).forEach(type => {
          if (targetTypes.includes(type)) {
            filteredActivities[type] = filteredStats.activities_by_type[type]
            filteredDistance[type] = filteredStats.distance_by_type?.[type] || 0
            filteredTime[type] = filteredStats.time_by_type?.[type] || 0
          }
        })
        
        filteredStats.activities_by_type = filteredActivities
        filteredStats.distance_by_type = filteredDistance
        filteredStats.time_by_type = filteredTime
        filteredStats.total_activities = Object.values(filteredActivities).reduce((a: number, b: number) => a + b, 0)
        filteredStats.total_distance = Object.values(filteredDistance).reduce((a: number, b: number) => a + b, 0)
        filteredStats.total_time = Object.values(filteredTime).reduce((a: number, b: number) => a + b, 0)
      }
    }

    return filteredStats
  }

  const filteredStats = getFilteredStats(stats)

  // Fonction pour filtrer les activités selon le filtre de sport
  const filterActivitiesBySport = (activities: any[], sportFilter: string) => {
    if (sportFilter === 'all') return activities
    
    const sportTypeMapping: Record<string, string[]> = {
      'racket': ['RacketSport', 'Tennis', 'Badminton', 'Squash'],
      'swim': ['swim', 'Swim', 'Swimming'],
      'bike': ['Ride', 'Bike', 'Cycling'],
      'run': ['run', 'Run'],
      'trailrun': ['TrailRun'],
      'all_running': ['run', 'Run', 'TrailRun']
    }
    
    const targetTypes = sportTypeMapping[sportFilter] || []
    return activities.filter(activity => targetTypes.includes(activity.sport_type))
  }

  // Filtrer les activités selon le filtre de sport
  const filteredActivities = useEnrichedData && filteredStats ? 
    filterActivitiesBySport((filteredStats as any).activities || [], selectedSportFilter) : []

  // Fonction pour générer les données du graphique pour les activités de course
  const generateChartData = () => {
    if (!filteredActivities || filteredActivities.length === 0) return []

    // Filtrer uniquement les activités de course (run + trail)
    const runningActivities = filteredActivities.filter(activity => 
      ['run', 'Run', 'TrailRun'].includes(activity.sport_type)
    )

    if (runningActivities.length === 0) return []

    // Trier par date
    const sortedActivities = runningActivities.sort((a, b) => 
      new Date(a.start_date_utc || a.start_date).getTime() - new Date(b.start_date_utc || b.start_date).getTime()
    )

    // Grouper selon l'intervalle sélectionné
    const groupedData: { [key: string]: any[] } = {}
    
    sortedActivities.forEach(activity => {
      const date = new Date(activity.start_date_utc || activity.start_date)
      let dateKey = ''
      
      if (chartInterval === 'day') {
        // Grouper par jour
        dateKey = date.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' })
      } else if (chartInterval === 'week') {
        // Grouper par semaine (début de semaine)
        const dayOfWeek = date.getDay()
        const daysToSubtract = dayOfWeek === 0 ? 6 : dayOfWeek - 1 // Lundi = 0, Dimanche = 6
        const weekStart = new Date(date.getTime() - daysToSubtract * 24 * 60 * 60 * 1000)
        dateKey = `Sem. ${weekStart.getDate()}/${weekStart.getMonth() + 1}`
      } else if (chartInterval === 'month') {
        // Grouper par mois
        dateKey = date.toLocaleDateString('fr-FR', { month: 'short', year: '2-digit' })
      }
      
      if (!groupedData[dateKey]) {
        groupedData[dateKey] = []
      }
      groupedData[dateKey].push(activity)
    })

    // Créer les données pour le graphique
    return Object.entries(groupedData).map(([date, activities]) => {
      const totalDistance = activities.reduce((sum, activity) => 
        sum + ((activity.distance_m || activity.distance || 0) / 1000), 0
      )
      const totalDuration = activities.reduce((sum, activity) => 
        sum + (activity.moving_time_s || activity.moving_time || 0), 0
      )
      const totalElevation = activities.reduce((sum, activity) => 
        sum + (activity.elev_gain_m || activity.total_elevation_gain || 0), 0
      )
      const avgPace = totalDistance > 0 ? (totalDuration / 60) / totalDistance : 0

      return {
        date,
        distance: Number.isFinite(totalDistance) ? totalDistance : 0,
        duration: Number.isFinite(totalDuration) ? totalDuration : 0,
        pace: Number.isFinite(avgPace) ? avgPace : 0,
        elevation: Number.isFinite(totalElevation) ? totalElevation : 0
      }
    })
  }

  const chartData = generateChartData()
  const selectedMetricOption = metricOptions.find(opt => opt.value === selectedMetric)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500"></div>
      </div>
    )
  }





  return (
    <div className="space-y-8">
      {/* Header avec sélecteur de données */}
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
          {/* Toggle pour choisir la source de données */}
          <div className="flex items-center space-x-2">
            <label className="text-sm font-medium text-gray-700">Source :</label>
            <button
              onClick={() => setUseEnrichedData(true)}
              className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                useEnrichedData
                  ? 'bg-green-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Enrichies
            </button>
            <button
              onClick={() => setUseEnrichedData(false)}
              className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                !useEnrichedData
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Originales
            </button>
          </div>
          
          <div className="text-right">
            {stravaStatus?.connected && stravaStatus.last_sync && (
              <div className="text-sm text-gray-500">
                <div className="font-medium">Dernière mise à jour :</div>
                <div>
                  {new Date(stravaStatus.last_sync).toLocaleDateString('fr-FR', {
                    day: '2-digit',
                    month: '2-digit',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit'
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Filtres de période */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-medium text-gray-900">
            Période d'analyse
          </h3>
          <div className="flex items-center space-x-4">
            {/* Sélecteur de type de sport */}
            <div className="flex items-center space-x-2">
              <label className="text-sm font-medium text-gray-700">Filtrer par :</label>
              <select
                value={selectedSportFilter}
                onChange={(e) => setSelectedSportFilter(e.target.value)}
                className="px-3 py-1.5 text-sm rounded-md border border-gray-300 focus:border-primary-500 focus:ring-primary-500"
              >
                {sportFilterOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            
            <div className="flex items-center space-x-2">
              <label className="text-sm font-medium text-gray-700">Analyser les :</label>
              <div className="flex space-x-2">
                {[
                  { days: 7, label: '7 derniers jours' },
                  { days: 30, label: '30 derniers jours' },
                  { days: 90, label: '3 mois' },
                  { days: 365, label: 'Cette année' }
                ].map((period) => (
                  <button
                    key={period.days}
                    onClick={() => setSelectedPeriod(period.days)}
                    className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                      selectedPeriod === period.days
                        ? 'bg-primary-600 text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    {period.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
          

        </div>
        
        <div className="text-sm text-gray-600">
          <strong>Période sélectionnée :</strong> {
            selectedPeriod === 7 ? '7 derniers jours' :
            selectedPeriod === 30 ? '30 derniers jours' :
            selectedPeriod === 90 ? '3 derniers mois' :
            'Cette année (365 jours)'
          }
          {selectedSportFilter !== 'all' && (
            <span className="ml-2">
              • <strong>Filtre :</strong> {sportFilterOptions.find(opt => opt.value === selectedSportFilter)?.label}
            </span>
          )}

        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="card">
          <div className="flex items-center">
            <div className="p-3 rounded-lg bg-primary-100">
              <Activity className="h-6 w-6 text-primary-600" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500">Activités</p>
              <p className="text-2xl font-semibold text-gray-900">
                {filteredStats?.total_activities || 0}
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
                {useEnrichedData ? (filteredStats as any)?.total_distance_km?.toFixed(1) || 0 : (filteredStats as any)?.total_distance?.toFixed(1) || 0} km
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
                {useEnrichedData ? Math.round((filteredStats as any)?.total_time_hours || 0) : Math.round((filteredStats as any)?.total_time / 3600 || 0)}h
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
                {useEnrichedData ? Object.keys((filteredStats as any)?.activities_by_sport_type || {}).length : Object.keys((filteredStats as any)?.activities_by_type || {}).length}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Graphique Area Chart */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-medium text-gray-900">
            Évolution des performances - Course à pied
          </h3>
          <div className="flex items-center space-x-4">
            {/* Boutons d'intervalle J/S/M */}
            <div className="flex items-center space-x-1">
              {[
                { value: 'day', label: 'J' },
                { value: 'week', label: 'S' },
                { value: 'month', label: 'M' }
              ].map((interval) => (
                <button
                  key={interval.value}
                  onClick={() => setChartInterval(interval.value as 'day' | 'week' | 'month')}
                  className={`px-2 py-1 text-xs rounded transition-colors ${
                    chartInterval === interval.value
                      ? 'bg-orange-600 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                  title={`Par ${interval.value === 'day' ? 'jour' : interval.value === 'week' ? 'semaine' : 'mois'}`}
                >
                  {interval.label}
                </button>
              ))}
            </div>
            
            {/* Sélecteur de métrique */}
            <div className="flex items-center space-x-2">
              <label className="text-sm font-medium text-gray-700">Métrique :</label>
              <Select value={selectedMetric} onValueChange={setSelectedMetric}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {metricOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        {/* Graphique */}
        {isLoading ? (
          <div className="h-64 flex items-center justify-center text-gray-500">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-orange-500 mr-3"></div>
            Chargement des données...
          </div>
        ) : chartData.length > 0 ? (
          <AreaChart
            data={chartData}
            index="date"
            categories={[selectedMetric]}
            colors={["hsl(var(--chart-1))"]}
            valueFormatter={selectedMetricOption?.formatter || ((value: number) => value.toString())}
            showAnimation={true}
            showTooltip={true}
            showGrid={true}
          />
        ) : (
          <div className="h-64 flex items-center justify-center text-gray-500 bg-gray-50 rounded-lg">
            <div className="text-center">
              <div className="text-4xl mb-2">🏃‍♂️</div>
              <p>Aucune activité de course trouvée pour cette période</p>
              <p className="text-sm text-gray-400 mt-1">
                Commencez à courir pour voir vos données ici !
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Section Charge Chronique de Banister */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-medium text-gray-900">
            Charge Chronique d'Entraînement
          </h3>
          <div className="text-sm text-gray-500">
            Modèle de Banister (TRIMP)
          </div>
        </div>
        
        <ChronicLoadChart 
          data={chronicLoadData || []} 
          isLoading={chronicLoadLoading}
        />
      </div>

      {/* Section Prédicteur de Course */}
      <div className="card">
        <RacePredictor />
      </div>

      {/* Section Plans d'Entraînement */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-medium text-gray-900">
            Plans d'Entraînement
          </h3>
          <a
            href="/plans"
            className="inline-flex items-center px-3 py-2 text-sm font-medium text-primary-600 bg-primary-50 rounded-md hover:bg-primary-100"
          >
            <Calendar className="h-4 w-4 mr-2" />
            Voir tous les plans
          </a>
        </div>

        {workoutPlans.length === 0 ? (
          <div className="text-center py-8">
            <Calendar className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <h4 className="text-lg font-medium text-gray-900 mb-2">Aucun plan d'entraînement</h4>
            <p className="text-gray-600 mb-4">
              Créez votre premier plan d'entraînement pour commencer à suivre vos objectifs
            </p>
            <a
              href="/plans"
              className="inline-flex items-center px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700"
            >
              Créer un plan
            </a>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Statistiques des plans */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <div className="bg-gray-50 p-4 rounded-lg">
                <div className="flex items-center">
                  <Target className="h-5 w-5 text-blue-500 mr-2" />
                  <span className="text-sm font-medium text-gray-700">Total</span>
                </div>
                <p className="text-2xl font-bold text-gray-900 mt-1">{workoutPlans.length}</p>
              </div>
              <div className="bg-gray-50 p-4 rounded-lg">
                <div className="flex items-center">
                  <CheckCircle className="h-5 w-5 text-green-500 mr-2" />
                  <span className="text-sm font-medium text-gray-700">Terminés</span>
                </div>
                <p className="text-2xl font-bold text-gray-900 mt-1">
                  {workoutPlans.filter(p => p.is_completed).length}
                </p>
              </div>
              <div className="bg-gray-50 p-4 rounded-lg">
                <div className="flex items-center">
                  <TrendingUp className="h-5 w-5 text-orange-500 mr-2" />
                  <span className="text-sm font-medium text-gray-700">Taux moyen</span>
                </div>
                <p className="text-2xl font-bold text-gray-900 mt-1">
                  {workoutPlans.length > 0 
                    ? Math.round(workoutPlans.reduce((sum, p) => sum + (p.completion_percentage || 0), 0) / workoutPlans.length)
                    : 0}%
                </p>
              </div>
            </div>

            {/* Plans à venir */}
            <div>
              <h4 className="text-md font-medium text-gray-900 mb-3">Prochaines séances</h4>
              <div className="space-y-2">
                {workoutPlans
                  .filter(plan => {
                    const planDate = new Date(plan.planned_date)
                    const today = new Date()
                    today.setHours(0, 0, 0, 0)
                    return planDate >= today
                  })
                  .sort((a, b) => new Date(a.planned_date).getTime() - new Date(b.planned_date).getTime())
                  .slice(0, showMoreWorkoutPlans ? 8 : 3)
                  .map(plan => {
                    const planDate = new Date(plan.planned_date)
                    const today = new Date()
                    today.setHours(0, 0, 0, 0)
                    const isToday = planDate.getTime() === today.getTime()
                    const isTomorrow = planDate.getTime() === today.getTime() + 24 * 60 * 60 * 1000
                    
                    return (
                      <div key={plan.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                        <div className="flex items-center">
                          <div className={`w-3 h-3 rounded-full mr-3 ${
                            plan.is_completed ? 'bg-green-500' : 
                            isToday ? 'bg-blue-500' : 
                            isTomorrow ? 'bg-orange-500' : 'bg-yellow-500'
                          }`} />
                          <div>
                            <p className="font-medium text-gray-900">{plan.name}</p>
                            <p className="text-sm text-gray-600">
                              {isToday ? 'Aujourd\'hui' : 
                               isTomorrow ? 'Demain' : 
                               planDate.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })} • {plan.planned_distance}km
                            </p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-medium text-gray-900">
                            {(plan.completion_percentage || 0).toFixed(0)}%
                          </p>
                          <p className="text-xs text-gray-500">
                            {plan.is_completed ? 'Terminé' : 
                             isToday ? 'Aujourd\'hui' : 
                             isTomorrow ? 'Demain' : 'À venir'}
                          </p>
                        </div>
                      </div>
                    )
                  })}
                
                {/* Bouton "Voir plus" */}
                {workoutPlans.filter(plan => {
                  const planDate = new Date(plan.planned_date)
                  const today = new Date()
                  today.setHours(0, 0, 0, 0)
                  return planDate >= today
                }).length > 3 && (
                  <button
                    onClick={() => setShowMoreWorkoutPlans(!showMoreWorkoutPlans)}
                    className="w-full mt-3 flex items-center justify-center px-4 py-2 text-sm font-medium text-primary-600 bg-primary-50 rounded-md hover:bg-primary-100 transition-colors"
                  >
                    {showMoreWorkoutPlans ? (
                      <>
                        <ChevronUp className="h-4 w-4 mr-2" />
                        Voir moins
                      </>
                    ) : (
                      <>
                        <ChevronDown className="h-4 w-4 mr-2" />
                        Voir plus ({workoutPlans.filter(plan => {
                          const planDate = new Date(plan.planned_date)
                          const today = new Date()
                          today.setHours(0, 0, 0, 0)
                          return planDate >= today
                        }).length - 3} autres)
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
} 