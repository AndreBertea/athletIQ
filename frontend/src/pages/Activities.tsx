import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, MapPin, Clock, TrendingUp, Eye, Calendar, X, Heart, Target, Trophy } from 'lucide-react'
import { activityService } from '../services/activityService'
import HeartRateChart from '../components/HeartRateChart'

export default function Activities() {
  const [selectedActivityId, setSelectedActivityId] = useState<number | null>(null)
  const [selectedActivityDetail, setSelectedActivityDetail] = useState<any | null>(null)
  const [useEnrichedData, setUseEnrichedData] = useState<boolean>(true)
  
  // Récupérer les activités originales
  const { data: originalActivities, isLoading: originalLoading } = useQuery({
    queryKey: ['activities'],
    queryFn: () => activityService.getActivities({ limit: 50 }),
    staleTime: 5 * 60 * 1000,
    enabled: !useEnrichedData
  })

  // Récupérer les activités enrichies (directement un tableau maintenant)
  const { data: enrichedActivities, isLoading: enrichedLoading } = useQuery({
    queryKey: ['enriched-activities'],
    queryFn: () => activityService.getEnrichedActivities({ limit: 50 }),
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

  const isLoading = useEnrichedData ? enrichedLoading : originalLoading
  
  // Utiliser les bonnes données selon le toggle
  const activities = useEnrichedData ? enrichedActivities : originalActivities
  
  // Créer un Map des activités enrichies pour vérification (toujours charger pour les badges)
  const { data: allEnrichedActivities } = useQuery({
    queryKey: ['enriched-activities-for-badges'],
    queryFn: () => activityService.getEnrichedActivities({ limit: 100 }),
    staleTime: 5 * 60 * 1000
  })
  
  const enrichedMap = new Map((allEnrichedActivities || []).map((a: any) => [a.activity_id, a]))
  const enrichedIds = new Set((allEnrichedActivities || []).map((a: any) => a.activity_id))

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
          id: activity.activity_id,
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
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getActivityTypeColor(displayData.sport_type)}`}>
                          {displayData.sport_type}
                        </span>
                        {!useEnrichedData && isEnriched && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                            <Eye className="h-3 w-3 mr-1" />
                            Enrichie
                          </span>
                        )}
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

                  {/* Actions */}
                  <div className="flex items-center space-x-2">
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
                  </div>
                </div>

                {/* Graphiques des streams (si sélectionné et enrichi) */}
                {showStreams && isEnriched && streamsData && (
                  <div className="mt-6 pt-6 border-t">
                    <div className="space-y-4">
                      {/* Graphique de fréquence cardiaque */}
                      {streamsData.streams.heartrate && streamsData.streams.time && (
                        <HeartRateChart
                          timeData={streamsData.streams.time}
                          heartrateData={streamsData.streams.heartrate}
                          distanceData={streamsData.streams.distance}
                          showMiniVersion={false}
                        />
                      )}

                      {/* Informations détaillées */}
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
                        {displayData.avg_heartrate && (
                          <div className="bg-red-50 p-3 rounded-lg">
                            <div className="text-sm text-red-600 font-medium">FC moyenne</div>
                            <div className="text-lg font-bold text-red-800">{Math.round(displayData.avg_heartrate)} bpm</div>
                          </div>
                        )}
                        {displayData.max_heartrate && (
                          <div className="bg-red-50 p-3 rounded-lg">
                            <div className="text-sm text-red-600 font-medium">FC max</div>
                            <div className="text-lg font-bold text-red-800">{Math.round(displayData.max_heartrate)} bpm</div>
                          </div>
                        )}
                        {displayData.elev_gain && (
                          <div className="bg-green-50 p-3 rounded-lg">
                            <div className="text-sm text-green-600 font-medium">Dénivelé</div>
                            <div className="text-lg font-bold text-green-800">{Math.round(displayData.elev_gain)} m</div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

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

              {/* Graphiques pour activités enrichies */}
              {selectedActivityDetail.isEnriched && (
                <div className="space-y-4">
                  <h3 className="text-lg font-medium text-gray-900">Données détaillées</h3>
                  <button
                    onClick={() => setSelectedActivityId(selectedActivityDetail.strava_id || selectedActivityDetail.id)}
                    className="px-4 py-2 bg-green-100 hover:bg-green-200 text-green-800 rounded-md text-sm font-medium"
                  >
                    Charger les graphiques détaillés
                  </button>
                </div>
              )}

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