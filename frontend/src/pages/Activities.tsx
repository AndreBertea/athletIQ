import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, MapPin, Clock, TrendingUp, Eye, Calendar, X, Heart, Target, Trophy, Mountain, Zap, Gauge, BarChart3, Layers, CloudSun, Watch } from 'lucide-react'
import { activityService } from '../services/activityService'
import { dataService } from '../services/dataService'
import { useToast } from '../contexts/ToastContext'
import HeartRateChart from '../components/HeartRateChart'
// @ts-expect-error: Types manquants pour react-plotly.js
import Plot from 'react-plotly.js'
import ActivityTypeEditor from '../components/ActivityTypeEditor'
import SegmentAnalysis from '../components/activity/SegmentAnalysis'
import LapsTable from '../components/activity/LapsTable'
import WeatherWidget from '../components/activity/WeatherWidget'

const PER_PAGE = 30

export default function Activities() {
  const toast = useToast()
  const [selectedActivityId, setSelectedActivityId] = useState<number | null>(null)
  const [selectedActivityDetail, setSelectedActivityDetail] = useState<any | null>(null)
  const [useEnrichedData, setUseEnrichedData] = useState<boolean>(true)
  const [page, setPage] = useState(1)
  const [activeTab, setActiveTab] = useState<'streams' | 'segments' | 'laps'>('streams')

  // Récupérer les activités originales (paginées)
  const { data: originalData, isLoading: originalLoading } = useQuery({
    queryKey: ['activities', page],
    queryFn: () => activityService.getActivities({ page, per_page: PER_PAGE }),
    staleTime: 5 * 60 * 1000,
    enabled: !useEnrichedData
  })

  // Récupérer les activités enrichies (paginées)
  const { data: enrichedData, isLoading: enrichedLoading } = useQuery({
    queryKey: ['enriched-activities', page],
    queryFn: () => activityService.getEnrichedActivities({ page, per_page: PER_PAGE }),
    staleTime: 5 * 60 * 1000,
    enabled: useEnrichedData
  })

  // Récupérer les streams de l'activité sélectionnée
  const { data: streamsData } = useQuery({
    queryKey: ['activity-streams', selectedActivityId],
    queryFn: () => selectedActivityId ? activityService.getEnrichedActivityStreams(selectedActivityId) : null,
    enabled: !!selectedActivityId,
    staleTime: 10 * 60 * 1000
  })

  // Récupérer la météo pour la modal détail
  const modalActivityId = selectedActivityDetail?.strava_id || selectedActivityDetail?.activity_id
  const { data: modalWeather } = useQuery({
    queryKey: ['activity-weather-modal', modalActivityId],
    queryFn: () => dataService.getWeather(String(modalActivityId)),
    enabled: !!modalActivityId,
    staleTime: 30 * 60 * 1000,
  })

  const isLoading = useEnrichedData ? enrichedLoading : originalLoading

  // Utiliser les bonnes données selon le toggle
  const paginatedData = useEnrichedData ? enrichedData : originalData
  const activities = paginatedData?.items || []
  const totalPages = paginatedData?.pages || 1
  const totalActivities = paginatedData?.total || 0

  // Créer un Map des activités enrichies pour vérification (toujours charger pour les badges)
  const { data: badgesData } = useQuery({
    queryKey: ['enriched-activities-for-badges', page],
    queryFn: () => activityService.getEnrichedActivities({ page, per_page: PER_PAGE }),
    staleTime: 5 * 60 * 1000
  })

  const enrichedMap = new Map((badgesData?.items || []).map((a: any) => [a.activity_id, a]))
  const enrichedIds = new Set((badgesData?.items || []).map((a: any) => a.activity_id))

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500"></div>
      </div>
    )
  }

  const formatDuration = (seconds: number) => {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    if (hours > 0) {
      return `${hours}h ${minutes}m`
    }
    return `${minutes}m`
  }

  const formatDistance = (meters: number) => {
    if (meters >= 1000) {
      return `${(meters / 1000).toFixed(1)} km`
    }
    return `${meters} m`
  }

  const formatPace = (pace?: number) => {
    if (!pace) return '--:--'
    const minutes = Math.floor(pace)
    const seconds = Math.round((pace % 1) * 60)
    return `${minutes}:${String(seconds).padStart(2, '0')}`
  }

  const getActivityTypeColor = (type: string) => {
    switch (type.toLowerCase()) {
      case 'run': return 'bg-green-100 text-green-800'
      case 'trailrun': return 'bg-orange-100 text-orange-800'
      case 'racketsport': return 'bg-purple-100 text-purple-800'
      case 'workout': return 'bg-blue-100 text-blue-800'
      case 'swim': return 'bg-cyan-100 text-cyan-800'
      case 'ride': case 'bike': return 'bg-yellow-100 text-yellow-800'
      default: return 'bg-gray-100 text-gray-800'
    }
  }

  const handleActivityClick = async (activity: any) => {
    try {
      if (useEnrichedData) {
        // Pour les données enrichies, utiliser directement les données
        setSelectedActivityDetail({
          ...activity,
          // Mapper les champs enrichis vers les champs standards
          // Trouver l'UUID correspondant dans les activités originales
          id: activities.find(a => a.strava_id === activity.activity_id)?.id || activity.activity_id,
          name: activity.name,
          activity_type: activity.sport_type,
          distance: activity.distance_m,
          moving_time: activity.moving_time_s,
          start_date: activity.start_date_utc,
          strava_id: activity.activity_id,
          enrichedData: activity,
          isEnriched: true
        })
      } else {
        // Pour les données originales, récupérer les détails
        const detail = await activityService.getActivity(activity.id)
        const enrichedData = enrichedMap.get(activity.strava_id)
        setSelectedActivityDetail({
          ...detail,
          enrichedData,
          isEnriched: !!enrichedData
        })
      }
    } catch (error) {
      console.error('Erreur lors du chargement du détail:', error)
      toast.error('Impossible de charger les détails de l\'activité')
    }
  }

  const handleStreamsToggle = (activityId: number) => {
    setSelectedActivityId(selectedActivityId === activityId ? null : activityId)
  }

  return (
    <div className="space-y-6">
      {/* Header avec toggle */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Mes activités</h1>
          <p className="mt-2 text-gray-600">
            Historique de vos activités sportives avec données enrichies
            {useEnrichedData && (
              <span className="ml-2 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                <Trophy className="h-3 w-3 mr-1" />
                Données enrichies
              </span>
            )}
          </p>
        </div>
        
        {/* Toggle pour choisir la source de données */}
        <div className="flex items-center space-x-2">
          <label className="text-sm font-medium text-gray-700">Source :</label>
          <button
            onClick={() => { setUseEnrichedData(true); setPage(1) }}
            className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
              useEnrichedData
                ? 'bg-green-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            Enrichies
          </button>
          <button
            onClick={() => { setUseEnrichedData(false); setPage(1) }}
            className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
              !useEnrichedData
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            Classiques
          </button>
        </div>
      </div>

      {/* Liste des activités */}
      <div className="grid gap-4">
        {activities?.map((activity: any) => {
          // Gérer les IDs selon le type de données
          const activityId = useEnrichedData ? activity.activity_id : activity.strava_id
          const isEnriched = useEnrichedData ? true : enrichedIds.has(activityId)
          const enrichedData = useEnrichedData ? activity : enrichedMap.get(activityId)
          const showStreams = selectedActivityId === activityId

          // Données à afficher (enrichies ou originales)
          const displayData = {
            name: useEnrichedData ? activity.name : activity.name,
            sport_type: useEnrichedData ? activity.sport_type : (enrichedData?.sport_type || activity.activity_type),
            distance: useEnrichedData ? activity.distance_m : activity.distance,
            moving_time: useEnrichedData ? activity.moving_time_s : activity.moving_time,
            start_date: useEnrichedData ? activity.start_date_utc : activity.start_date,
            avg_heartrate: useEnrichedData ? activity.avg_heartrate_bpm : null,
            max_heartrate: useEnrichedData ? activity.max_heartrate_bpm : null,
            elev_gain: useEnrichedData ? activity.elev_gain_m : null
          }

          return (
            <div key={useEnrichedData ? activity.activity_id : activity.id} className="bg-white rounded-lg border shadow-sm">
              <div className="p-6">
                <div className="flex items-start justify-between">
                  <div 
                    className="flex items-start space-x-4 flex-1 cursor-pointer hover:bg-gray-50 -m-2 p-2 rounded"
                    onClick={() => handleActivityClick(activity)}
                  >
                    <div className="flex-shrink-0">
                      <div className="w-12 h-12 bg-primary-100 rounded-lg flex items-center justify-center">
                        <Activity className="h-6 w-6 text-primary-600" />
                      </div>
                    </div>
                    
                    <div className="flex-1 min-w-0">
                      {/* Titre et type */}
                      <div className="flex items-center space-x-2 mb-2">
                        <h3 className="text-lg font-medium text-gray-900 truncate">
                          {displayData.name}
                        </h3>
                        {!useEnrichedData && isEnriched && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                            <Eye className="h-3 w-3 mr-1" />
                            Enrichie
                          </span>
                        )}
                      </div>
                      
                      {/* Éditeur de type d'activité */}
                      <div className="mb-2">
                        <ActivityTypeEditor 
                          activity={{
                            id: useEnrichedData ? activity.activity_id : activity.id,
                            activity_type: displayData.sport_type
                          }}
                          onSave={() => {
                            // Rafraîchir les données après modification
                            window.location.reload()
                          }}
                        />
                      </div>

                      {/* Métriques */}
                      <div className="flex items-center space-x-6 text-sm text-gray-500">
                        <div className="flex items-center">
                          <TrendingUp className="h-4 w-4 mr-1" />
                          <span>{formatDistance(displayData.distance)}</span>
                        </div>
                        <div className="flex items-center">
                          <Clock className="h-4 w-4 mr-1" />
                          <span>{formatDuration(displayData.moving_time)}</span>
                        </div>
                        <div className="flex items-center">
                          <Calendar className="h-4 w-4 mr-1" />
                          <span>{new Date(displayData.start_date).toLocaleDateString('fr-FR')}</span>
                        </div>
                        {!useEnrichedData && activity.average_pace && (
                          <div className="flex items-center">
                            <Target className="h-4 w-4 mr-1" />
                            <span>{formatPace(activity.average_pace)}/km</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Actions + badges sources */}
                  <div className="flex flex-col items-end space-y-2">
                    {isEnriched ? (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleStreamsToggle(activityId)
                        }}
                        className="flex items-center px-3 py-1.5 bg-green-100 hover:bg-green-200 text-green-800 rounded-md text-sm font-medium transition-colors"
                      >
                        <Eye className="h-4 w-4 mr-1" />
                        {showStreams ? 'Masquer' : 'Graphiques'}
                      </button>
                    ) : (
                      <div className="flex items-center px-3 py-1.5 bg-gray-100 text-gray-500 rounded-md text-sm">
                        <MapPin className="h-4 w-4 mr-1" />
                        {activity.location_city || 'Non enrichi'}
                      </div>
                    )}

                    {/* Badges sources de données */}
                    <div className="flex items-center space-x-1.5">
                      {(activity.has_strava || activity.strava_id || activityId) && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-700" title="Données Strava">
                          <svg className="h-3 w-3 mr-0.5" viewBox="0 0 24 24" fill="currentColor"><path d="M15.387 17.944l-2.089-4.116h-3.065L15.387 24l5.15-10.172h-3.066m-7.008-5.599l2.836 5.598h4.172L10.463 0l-7 13.828h4.169"/></svg>
                          Strava
                        </span>
                      )}
                      {activity.has_garmin && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700" title="Données Garmin FIT">
                          <Watch className="h-3 w-3 mr-0.5" />
                          Garmin
                        </span>
                      )}
                      {activity.has_weather && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700" title="Données météo">
                          <CloudSun className="h-3 w-3 mr-0.5" />
                          Météo
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Graphiques / Analyse (si sélectionné et enrichi) */}
                {showStreams && isEnriched && (
                  <div className="mt-6 pt-6 border-t">
                    {/* Onglets */}
                    <div className="flex space-x-1 mb-4 border-b">
                      {([
                        { id: 'streams' as const, label: 'Streams', icon: <Eye className="h-3.5 w-3.5 mr-1.5" /> },
                        { id: 'segments' as const, label: 'Segments', icon: <BarChart3 className="h-3.5 w-3.5 mr-1.5" /> },
                        { id: 'laps' as const, label: 'Tours', icon: <Layers className="h-3.5 w-3.5 mr-1.5" /> },
                      ]).map(tab => (
                        <button
                          key={tab.id}
                          onClick={(e) => { e.stopPropagation(); setActiveTab(tab.id) }}
                          className={`inline-flex items-center px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                            activeTab === tab.id
                              ? 'border-primary-600 text-primary-600'
                              : 'border-transparent text-gray-500 hover:text-gray-700'
                          }`}
                        >
                          {tab.icon}{tab.label}
                        </button>
                      ))}
                    </div>

                    {/* Contenu des onglets */}
                    {activeTab === 'streams' && streamsData && (
                      <div className="space-y-4">
                        {/* Métriques clés */}
                        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                          <div className="bg-blue-50 p-3 rounded-lg text-center">
                            <TrendingUp className="h-4 w-4 mx-auto mb-1 text-blue-600" />
                            <div className="text-xs text-blue-600">Distance</div>
                            <div className="text-sm font-bold text-blue-800">{formatDistance(displayData.distance)}</div>
                          </div>
                          <div className="bg-green-50 p-3 rounded-lg text-center">
                            <Clock className="h-4 w-4 mx-auto mb-1 text-green-600" />
                            <div className="text-xs text-green-600">Durée</div>
                            <div className="text-sm font-bold text-green-800">{formatDuration(displayData.moving_time)}</div>
                          </div>
                          {displayData.avg_heartrate && (
                            <div className="bg-red-50 p-3 rounded-lg text-center">
                              <Heart className="h-4 w-4 mx-auto mb-1 text-red-600" />
                              <div className="text-xs text-red-600">FC moy / max</div>
                              <div className="text-sm font-bold text-red-800">{Math.round(displayData.avg_heartrate)}{displayData.max_heartrate ? ` / ${Math.round(displayData.max_heartrate)}` : ''} bpm</div>
                            </div>
                          )}
                          {displayData.elev_gain && (
                            <div className="bg-emerald-50 p-3 rounded-lg text-center">
                              <Mountain className="h-4 w-4 mx-auto mb-1 text-emerald-600" />
                              <div className="text-xs text-emerald-600">Dénivelé +</div>
                              <div className="text-sm font-bold text-emerald-800">{Math.round(displayData.elev_gain)} m</div>
                            </div>
                          )}
                          {activity.avg_cadence && (
                            <div className="bg-purple-50 p-3 rounded-lg text-center">
                              <Zap className="h-4 w-4 mx-auto mb-1 text-purple-600" />
                              <div className="text-xs text-purple-600">Cadence</div>
                              <div className="text-sm font-bold text-purple-800">{Math.round(activity.avg_cadence * 2)} ppm</div>
                            </div>
                          )}
                        </div>

                        {/* Graphique de fréquence cardiaque */}
                        {streamsData.streams?.heartrate && streamsData.streams?.time && (
                          <HeartRateChart
                            timeData={streamsData.streams.time.data || streamsData.streams.time}
                            heartrateData={streamsData.streams.heartrate.data || streamsData.streams.heartrate}
                            distanceData={streamsData.streams.distance?.data || streamsData.streams.distance}
                            showMiniVersion={false}
                          />
                        )}

                        {/* Graphique d'altitude */}
                        {streamsData.streams?.altitude && streamsData.streams?.time && (
                          <div className="w-full bg-white rounded-lg border">
                            <div className="flex items-center p-3 border-b">
                              <Mountain className="h-4 w-4 mr-2 text-emerald-500" />
                              <span className="text-sm font-medium text-gray-900">Profil altimétrique</span>
                            </div>
                            <div className="p-2">
                              {(() => {
                                const altData = streamsData.streams.altitude.data || streamsData.streams.altitude
                                const distData = streamsData.streams.distance?.data || streamsData.streams.distance
                                const timeArr = streamsData.streams.time.data || streamsData.streams.time
                                const xAxis = distData ? distData.map((d: number) => d / 1000) : timeArr.map((t: number) => t / 60)
                                return (
                                  // @ts-expect-error: Types manquants pour react-plotly.js
                                  <Plot
                                    data={[{
                                      x: xAxis,
                                      y: altData,
                                      type: 'scatter',
                                      mode: 'lines',
                                      fill: 'tozeroy',
                                      line: { color: '#10b981', width: 2 },
                                      fillcolor: 'rgba(16, 185, 129, 0.15)',
                                      hovertemplate: `<b>%{y:.0f} m</b><br>${distData ? 'Distance: %{x:.1f} km' : 'Temps: %{x:.1f} min'}<extra></extra>`
                                    }]}
                                    layout={{
                                      margin: { t: 20, r: 20, b: 40, l: 50 },
                                      height: 200,
                                      xaxis: { title: distData ? 'Distance (km)' : 'Temps (min)' },
                                      yaxis: { title: 'Altitude (m)' },
                                      showlegend: false,
                                      font: { family: 'Inter, system-ui, sans-serif', size: 12 },
                                      plot_bgcolor: 'rgba(0,0,0,0)',
                                      paper_bgcolor: 'rgba(0,0,0,0)'
                                    }}
                                    config={{ displayModeBar: false, responsive: true }}
                                    style={{ width: '100%' }}
                                  />
                                )
                              })()}
                            </div>
                          </div>
                        )}

                        {/* Graphique de vitesse */}
                        {streamsData.streams?.velocity_smooth && streamsData.streams?.time && (
                          <div className="w-full bg-white rounded-lg border">
                            <div className="flex items-center p-3 border-b">
                              <Gauge className="h-4 w-4 mr-2 text-orange-500" />
                              <span className="text-sm font-medium text-gray-900">Vitesse</span>
                            </div>
                            <div className="p-2">
                              {(() => {
                                const velData = streamsData.streams.velocity_smooth.data || streamsData.streams.velocity_smooth
                                const timeArr = streamsData.streams.time.data || streamsData.streams.time
                                return (
                                  // @ts-expect-error: Types manquants pour react-plotly.js
                                  <Plot
                                    data={[{
                                      x: timeArr.map((t: number) => t / 60),
                                      y: velData.map((v: number) => v * 3.6),
                                      type: 'scatter',
                                      mode: 'lines',
                                      line: { color: '#f97316', width: 2 },
                                      hovertemplate: '<b>%{y:.1f} km/h</b><br>Temps: %{x:.1f} min<extra></extra>'
                                    }]}
                                    layout={{
                                      margin: { t: 20, r: 20, b: 40, l: 50 },
                                      height: 200,
                                      xaxis: { title: 'Temps (min)' },
                                      yaxis: { title: 'Vitesse (km/h)' },
                                      showlegend: false,
                                      font: { family: 'Inter, system-ui, sans-serif', size: 12 },
                                      plot_bgcolor: 'rgba(0,0,0,0)',
                                      paper_bgcolor: 'rgba(0,0,0,0)'
                                    }}
                                    config={{ displayModeBar: false, responsive: true }}
                                    style={{ width: '100%' }}
                                  />
                                )
                              })()}
                            </div>
                          </div>
                        )}

                        {/* Graphique de cadence */}
                        {streamsData.streams?.cadence && streamsData.streams?.time && (
                          <div className="w-full bg-white rounded-lg border">
                            <div className="flex items-center p-3 border-b">
                              <Zap className="h-4 w-4 mr-2 text-purple-500" />
                              <span className="text-sm font-medium text-gray-900">Cadence</span>
                            </div>
                            <div className="p-2">
                              {(() => {
                                const cadData = streamsData.streams.cadence.data || streamsData.streams.cadence
                                const timeArr = streamsData.streams.time.data || streamsData.streams.time
                                return (
                                  // @ts-expect-error: Types manquants pour react-plotly.js
                                  <Plot
                                    data={[{
                                      x: timeArr.map((t: number) => t / 60),
                                      y: cadData.map((c: number) => c * 2),
                                      type: 'scatter',
                                      mode: 'lines',
                                      line: { color: '#8b5cf6', width: 2 },
                                      hovertemplate: '<b>%{y:.0f} ppm</b><br>Temps: %{x:.1f} min<extra></extra>'
                                    }]}
                                    layout={{
                                      margin: { t: 20, r: 20, b: 40, l: 50 },
                                      height: 200,
                                      xaxis: { title: 'Temps (min)' },
                                      yaxis: { title: 'Cadence (ppm)' },
                                      showlegend: false,
                                      font: { family: 'Inter, system-ui, sans-serif', size: 12 },
                                      plot_bgcolor: 'rgba(0,0,0,0)',
                                      paper_bgcolor: 'rgba(0,0,0,0)'
                                    }}
                                    config={{ displayModeBar: false, responsive: true }}
                                    style={{ width: '100%' }}
                                  />
                                )
                              })()}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {activeTab === 'segments' && (
                      <SegmentAnalysis activityId={activityId} />
                    )}

                    {activeTab === 'laps' && (
                      <LapsTable lapsData={streamsData?.laps_data} />
                    )}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-gray-600">
            {totalActivities} activit{totalActivities > 1 ? 'és' : 'é'} — Page {page} / {totalPages}
          </p>
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="px-3 py-1.5 text-sm rounded-md border transition-colors disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
            >
              Précédent
            </button>
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              let pageNum: number
              if (totalPages <= 5) {
                pageNum = i + 1
              } else if (page <= 3) {
                pageNum = i + 1
              } else if (page >= totalPages - 2) {
                pageNum = totalPages - 4 + i
              } else {
                pageNum = page - 2 + i
              }
              return (
                <button
                  key={pageNum}
                  onClick={() => setPage(pageNum)}
                  className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                    page === pageNum
                      ? 'bg-primary-600 text-white'
                      : 'border hover:bg-gray-50'
                  }`}
                >
                  {pageNum}
                </button>
              )
            })}
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="px-3 py-1.5 text-sm rounded-md border transition-colors disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
            >
              Suivant
            </button>
          </div>
        </div>
      )}

      {/* Modal détail activité */}
      {selectedActivityDetail && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center p-6 border-b">
              <div>
                <h2 className="text-xl font-semibold text-gray-900">
                  {selectedActivityDetail.name}
                </h2>
                <div className="flex items-center space-x-2 mt-1">
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getActivityTypeColor(selectedActivityDetail.activity_type)}`}>
                    {selectedActivityDetail.activity_type}
                  </span>
                  {selectedActivityDetail.isEnriched && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                      <Eye className="h-3 w-3 mr-1" />
                      Données enrichies
                    </span>
                  )}
                </div>
              </div>
              <button
                onClick={() => setSelectedActivityDetail(null)}
                className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-50 rounded-lg"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            
            <div className="p-6 space-y-6">
              {/* Métriques principales */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="text-center">
                  <div className="text-2xl font-bold text-blue-600">
                    {formatDistance(selectedActivityDetail.distance)}
                  </div>
                  <div className="text-sm text-gray-500">Distance</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-green-600">
                    {formatDuration(selectedActivityDetail.moving_time)}
                  </div>
                  <div className="text-sm text-gray-500">Durée</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-orange-600">
                    {formatPace(selectedActivityDetail.average_pace)}
                  </div>
                  <div className="text-sm text-gray-500">Allure moy.</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-purple-600">
                    {selectedActivityDetail.enrichedData?.elev_gain_m ? Math.round(selectedActivityDetail.enrichedData.elev_gain_m) : (selectedActivityDetail.total_elevation_gain?.toFixed(0) || 0)}m
                  </div>
                  <div className="text-sm text-gray-500">Dénivelé</div>
                </div>
              </div>

              {/* Widget météo */}
              {modalWeather && <WeatherWidget weather={modalWeather} />}

              {/* Graphiques détaillés - chargés automatiquement */}
              {(() => {
                const stravaId = selectedActivityDetail.strava_id || selectedActivityDetail.activity_id
                if (stravaId && selectedActivityId !== stravaId) {
                  // Auto-charger les streams
                  setTimeout(() => setSelectedActivityId(stravaId), 0)
                }
                return streamsData?.streams && Object.keys(streamsData.streams).length > 0 ? (
                  <div className="space-y-4">
                    <h3 className="text-lg font-medium text-gray-900">Graphiques détaillés</h3>

                    {streamsData.streams?.heartrate && streamsData.streams?.time && (
                      <HeartRateChart
                        timeData={streamsData.streams.time.data || streamsData.streams.time}
                        heartrateData={streamsData.streams.heartrate.data || streamsData.streams.heartrate}
                        distanceData={streamsData.streams.distance?.data || streamsData.streams.distance}
                        showMiniVersion={false}
                      />
                    )}

                    {streamsData.streams?.altitude && streamsData.streams?.time && (
                      <div className="w-full bg-white rounded-lg border">
                        <div className="flex items-center p-3 border-b">
                          <Mountain className="h-4 w-4 mr-2 text-emerald-500" />
                          <span className="text-sm font-medium text-gray-900">Profil altimétrique</span>
                        </div>
                        <div className="p-2">
                          <Plot
                            data={[{
                              x: (streamsData.streams.distance?.data || streamsData.streams.distance || (streamsData.streams.time.data || streamsData.streams.time).map((t: number) => t / 60)).map((d: number) => streamsData.streams.distance ? d / 1000 : d),
                              y: streamsData.streams.altitude.data || streamsData.streams.altitude,
                              type: 'scatter',
                              mode: 'lines',
                              fill: 'tozeroy',
                              line: { color: '#10b981', width: 2 },
                              fillcolor: 'rgba(16, 185, 129, 0.15)',
                            }]}
                            layout={{ margin: { t: 20, r: 20, b: 40, l: 50 }, height: 200, xaxis: { title: streamsData.streams.distance ? 'Distance (km)' : 'Temps (min)' }, yaxis: { title: 'Altitude (m)' }, showlegend: false, plot_bgcolor: 'rgba(0,0,0,0)', paper_bgcolor: 'rgba(0,0,0,0)', font: { family: 'Inter, system-ui, sans-serif', size: 12 } }}
                            config={{ displayModeBar: false, responsive: true }}
                            style={{ width: '100%' }}
                          />
                        </div>
                      </div>
                    )}

                    {streamsData.streams?.velocity_smooth && streamsData.streams?.time && (
                      <div className="w-full bg-white rounded-lg border">
                        <div className="flex items-center p-3 border-b">
                          <Gauge className="h-4 w-4 mr-2 text-orange-500" />
                          <span className="text-sm font-medium text-gray-900">Vitesse</span>
                        </div>
                        <div className="p-2">
                          <Plot
                            data={[{
                              x: (streamsData.streams.time.data || streamsData.streams.time).map((t: number) => t / 60),
                              y: (streamsData.streams.velocity_smooth.data || streamsData.streams.velocity_smooth).map((v: number) => v * 3.6),
                              type: 'scatter',
                              mode: 'lines',
                              line: { color: '#f97316', width: 2 },
                            }]}
                            layout={{ margin: { t: 20, r: 20, b: 40, l: 50 }, height: 200, xaxis: { title: 'Temps (min)' }, yaxis: { title: 'km/h' }, showlegend: false, plot_bgcolor: 'rgba(0,0,0,0)', paper_bgcolor: 'rgba(0,0,0,0)', font: { family: 'Inter, system-ui, sans-serif', size: 12 } }}
                            config={{ displayModeBar: false, responsive: true }}
                            style={{ width: '100%' }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-4 text-gray-500 text-sm">
                    <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-500 mx-auto mb-2"></div>
                    Chargement des graphiques...
                  </div>
                )
              })()}

              {/* Informations générales */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-4">
                  <h3 className="font-medium text-gray-900 flex items-center">
                    <TrendingUp className="h-4 w-4 mr-2" />
                    Performance
                  </h3>
                  <div className="space-y-2 text-sm">
                    {selectedActivityDetail.average_speed && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">Vitesse moyenne</span>
                        <span>{(selectedActivityDetail.average_speed * 3.6).toFixed(1)} km/h</span>
                      </div>
                    )}
                    {selectedActivityDetail.max_speed && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">Vitesse max</span>
                        <span>{(selectedActivityDetail.max_speed * 3.6).toFixed(1)} km/h</span>
                      </div>
                    )}
                  </div>
                </div>

                {(selectedActivityDetail.average_heartrate || selectedActivityDetail.enrichedData?.avg_heartrate_bpm) && (
                  <div className="space-y-4">
                    <h3 className="font-medium text-gray-900 flex items-center">
                      <Heart className="h-4 w-4 mr-2 text-red-500" />
                      Fréquence cardiaque
                    </h3>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-500">FC moyenne</span>
                        <span>{Math.round(selectedActivityDetail.enrichedData?.avg_heartrate_bpm || selectedActivityDetail.average_heartrate)} bpm</span>
                      </div>
                      {(selectedActivityDetail.max_heartrate || selectedActivityDetail.enrichedData?.max_heartrate_bpm) && (
                        <div className="flex justify-between">
                          <span className="text-gray-500">FC max</span>
                          <span>{Math.round(selectedActivityDetail.enrichedData?.max_heartrate_bpm || selectedActivityDetail.max_heartrate)} bpm</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Description */}
              {selectedActivityDetail.description && (
                <div className="space-y-4">
                  <h3 className="font-medium text-gray-900">Description</h3>
                  <p className="text-sm text-gray-600">{selectedActivityDetail.description}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Message si aucune activité */}
      {!activities || activities.length === 0 ? (
        <div className="text-center py-12">
          <Activity className="h-12 w-12 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">Aucune activité trouvée</h3>
          <p className="text-gray-500">
            {useEnrichedData 
              ? 'Aucune activité enrichie disponible. Enrichissez vos activités via Connexion Strava.'
              : 'Connectez-vous à Strava pour importer vos activités'
            }
          </p>
        </div>
      ) : null}
    </div>
  )
} 