import React, { useState, useEffect, useRef } from 'react'
import { Activity, Target, Upload, FileText } from 'lucide-react'
import { activityService } from '../services/activityService'
import { useQuery } from '@tanstack/react-query'
import { Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Line, ComposedChart, ScatterChart, Scatter } from 'recharts'

interface RacePrediction {
  distance: number
  elevation: number
  predictedTime: number
  pace: number
  confidence: number
  similarActivities: number
  difficulty: 'Easy' | 'Moderate' | 'Hard' | 'Very Hard'
}

interface RacePredictorProps {
  className?: string
}

export default function RacePredictor({ className = '' }: RacePredictorProps) {
  const [isAnalyzingStreams, setIsAnalyzingStreams] = useState<boolean>(false)
  const [detailedZoneAnalysis, setDetailedZoneAnalysis] = useState<any>(null)
  const [boxplotData, setBoxplotData] = useState<any[]>([])
  const [elevationPaceData, setElevationPaceData] = useState<any[]>([])
  const [gpxPrediction, setGpxPrediction] = useState<any>(null)
  const [isUploadingGpx, setIsUploadingGpx] = useState<boolean>(false)
  const [customRavitos, setCustomRavitos] = useState<Array<{km: number, name: string}>>([])
  const [newRavitoKm, setNewRavitoKm] = useState<number>(0)
  const [newRavitoName, setNewRavitoName] = useState<string>('')
  const [segmentMode] = useState<boolean>(false)
  const [selectedSegment, setSelectedSegment] = useState<{start: number, end: number} | null>(null)
  const [isSelecting, setIsSelecting] = useState<boolean>(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Récupérer les activités enrichies des 6 derniers mois pour l'analyse
  const { data: enrichedActivities = [] } = useQuery({
    queryKey: ['enriched-activities-predictor'],
    queryFn: () => activityService.getEnrichedActivities({ limit: 1000 }),
    staleTime: 5 * 60 * 1000, // 5 minutes
  })

  // Fonction pour appliquer des filtres de base sur les activités
  const applyActivityFilters = (activities: any[]) => {
    return activities.filter(activity => {
      // Filtre 1: Distance minimale réaliste (au moins 1km)
      if (!activity.distance_km || activity.distance_km < 1) return false
      
      // Filtre 2: Temps minimum réaliste (au moins 5 minutes)
      if (!activity.time_hours || activity.time_hours < 0.083) return false // 5 min = 0.083h
      
      // Filtre 3: Rythme réaliste (entre 2 et 15 min/km)
      if (!activity.pace_per_km || activity.pace_per_km < 2/60 || activity.pace_per_km > 15/60) return false
      
      // Filtre 4: Dénivelé cohérent (pas plus de 200m/km)
      if (activity.elevation_per_km && activity.elevation_per_km > 200) return false
      
      // Filtre 5: FC moyenne réaliste (entre 60 et 200 BPM)
      if (activity.average_heartrate && (activity.average_heartrate < 60 || activity.average_heartrate > 200)) return false
      
      return true
    })
  }

  // Filtrer les activités de course des 6 derniers mois (données enrichies)
  const runningActivities = React.useMemo(() => {
    const sixMonthsAgo = new Date()
    sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6)
    
    // Filtre de base : période, type, données complètes
    const baseFiltered = enrichedActivities.filter(activity => {
      const activityDate = new Date(activity.start_date_utc)
      return activityDate >= sixMonthsAgo && 
             ['Run', 'TrailRun'].includes(activity.sport_type) &&
             activity.distance_m && 
             activity.moving_time_s &&
             activity.distance_m > 1000 // Au moins 1km
    }).map(activity => ({
      ...activity,
      distance_km: activity.distance_m / 1000,
      time_hours: activity.moving_time_s / 3600,
      pace_per_km: (activity.moving_time_s / 3600) / (activity.distance_m / 1000),
      elevation_per_km: (activity.elev_gain_m || 0) / (activity.distance_m / 1000),
      activity_type: activity.sport_type,
      average_heartrate: activity.avg_heartrate_bpm
    }))

    // Appliquer les filtres avancés
    const filteredActivities = applyActivityFilters(baseFiltered)
    
    console.log(`Filtrage activités: ${baseFiltered.length} → ${filteredActivities.length} activités valides`)
    return filteredActivities
  }, [enrichedActivities])

  // Préparer les données pour le graphique dénivelé/rythme (déjà filtrées)
  const prepareElevationPaceData = React.useMemo(() => {
    if (runningActivities.length === 0) return []

    // Les données sont déjà filtrées par applyActivityFilters
    const data = runningActivities.map(activity => ({
      elevationPerKm: activity.elevation_per_km || 0,
      pacePerKm: activity.pace_per_km * 60, // Convertir en min/km
      distance: activity.distance_km,
      activityType: activity.activity_type,
      activityName: activity.name,
      date: activity.start_date_utc,
      totalElevation: activity.elevation_per_km * activity.distance_km,
      avgHeartRate: activity.average_heartrate || 0,
      fill: activity.activity_type === 'Run' ? '#3b82f6' : '#f59e0b' // Bleu pour route, orange pour trail
    }))

    console.log('Données dénivelé/rythme préparées (filtrées):', data.length, 'activités')
    setElevationPaceData(data)
    return data
  }, [runningActivities])

  // Debug: afficher les données préparées
  console.log('Données graphique dénivelé:', prepareElevationPaceData.length, 'activités')

  // Séparer Running et Trail Running
  const roadRunningActivities = React.useMemo(() => {
    return runningActivities.filter(activity => activity.activity_type === 'Run')
  }, [runningActivities])

  const trailRunningActivities = React.useMemo(() => {
    return runningActivities.filter(activity => activity.activity_type === 'TrailRun')
  }, [runningActivities])

  // Analyser les zones de rythme cardiaque avec données détaillées
  const heartRateZoneAnalysis = React.useMemo(() => {
    const zones = [
      { name: 'Zone 100-110', min: 100, max: 110, color: 'bg-blue-100' },
      { name: 'Zone 110-120', min: 110, max: 120, color: 'bg-blue-200' },
      { name: 'Zone 120-130', min: 120, max: 130, color: 'bg-green-100' },
      { name: 'Zone 130-140', min: 130, max: 140, color: 'bg-green-200' },
      { name: 'Zone 140-150', min: 140, max: 150, color: 'bg-yellow-100' },
      { name: 'Zone 150-160', min: 150, max: 160, color: 'bg-yellow-200' },
      { name: 'Zone 160-170', min: 160, max: 170, color: 'bg-orange-100' },
      { name: 'Zone 170-180', min: 170, max: 180, color: 'bg-orange-200' },
      { name: 'Zone 180-190', min: 180, max: 190, color: 'bg-red-100' },
      { name: 'Zone 190+', min: 190, max: 220, color: 'bg-red-200' }
    ]

    // Pour l'instant, on utilise la FC moyenne en attendant l'implémentation des streams
    // TODO: Implémenter l'analyse des streams détaillés
    const activitiesWithHR = runningActivities.filter(activity => 
      activity.average_heartrate && activity.average_heartrate > 0
    )

    if (activitiesWithHR.length === 0) {
      return { zones: [], hasData: false }
    }

    // Analyser chaque zone (méthode actuelle avec FC moyenne)
    const zoneAnalysis = zones.map(zone => {
      const activitiesInZone = activitiesWithHR.filter(activity => 
        activity.average_heartrate >= zone.min && activity.average_heartrate < zone.max
      )

      if (activitiesInZone.length === 0) {
        return {
          ...zone,
          count: 0,
          avgPace: null,
          avgDistance: null,
          totalTime: 0,
          totalDataPoints: 0
        }
      }

        const avgDistance = activitiesInZone.reduce((sum, act) => sum + act.distance_km, 0) / activitiesInZone.length
        const totalTime = activitiesInZone.reduce((sum, act) => sum + act.time_hours, 0)

      return {
        ...zone,
        count: activitiesInZone.length,
        avgPace: activitiesInZone.reduce((sum, act) => sum + act.pace_per_km, 0) / activitiesInZone.length,
        avgDistance,
        totalTime,
        totalDataPoints: 0 // Sera calculé avec les streams
      }
    })

    return { zones: zoneAnalysis, hasData: true }
  }, [runningActivities])

  // Fonction pour appliquer des filtres et lisser les données des streams
  const applyDataFilters = (heartrateData: number[], velocityData: number[], timeData: number[], distanceData: number[]) => {
    if (!heartrateData || !velocityData || !timeData || heartrateData.length === 0) {
      return []
    }

    const filteredPoints: any[] = []
    const maxVelocity = 8.0 // 8 m/s = ~28.8 km/h (vitesse max réaliste)
    const minVelocity = 0.5 // 0.5 m/s = ~1.8 km/h (vitesse min réaliste)
    const maxHRChange = 50 // Changement max de FC entre deux points (BPM) - plus permissif pour haute intensité
    const minTimeInterval = 0.0001 // Intervalle minimum entre points (secondes)

    for (let i = 0; i < heartrateData.length; i++) {
      const hr = heartrateData[i]
      const velocity = velocityData[i]
      const time = timeData[i]

      // Filtre 1: Vérifications de base
      if (!hr || !velocity || !time || hr < 50 || hr > 220 || velocity < 0) {
        continue
      }

      // Filtre 2: Vitesses aberrantes
      if (velocity > maxVelocity || velocity < minVelocity) {
        continue
      }

      // Filtre 3: Changements de FC trop brusques
      if (i > 0) {
        const prevHR = heartrateData[i - 1]
        if (prevHR && Math.abs(hr - prevHR) > maxHRChange) {
          continue
        }
      }

      // Filtre 4: Intervalle de temps minimum
      if (i > 0) {
        const timeDiff = time - timeData[i - 1]
        if (timeDiff < minTimeInterval) {
          continue
        }
      }

      // Utiliser la vitesse brute (pas de lissage)
      const smoothedVelocity = velocity

      // Calcul de la distance parcourue
      let distanceInterval = 0
      if (distanceData && distanceData.length > i) {
        const currentDistance = distanceData[i] || 0
        const previousDistance = i > 0 ? (distanceData[i - 1] || 0) : 0
        distanceInterval = Math.max(0, (currentDistance - previousDistance) / 1000) // Convertir en km
      } else {
        // Estimation basée sur la vitesse lissée et le temps
        const timeDiff = i > 0 ? time - timeData[i - 1] : 5
        distanceInterval = (smoothedVelocity * timeDiff) / 1000 // km
      }

      // Pas de filtre sur la distance parcourue

      // Filtre 7: IQR (Interquartile Range) pour détecter les outliers - moins restrictif
      if (filteredPoints.length > 15) {
        const recentVelocities = filteredPoints.slice(-15).map(p => p.velocity)
        const sorted = [...recentVelocities].sort((a, b) => a - b)
        const q1 = sorted[Math.floor(sorted.length * 0.25)]
        const q3 = sorted[Math.floor(sorted.length * 0.75)]
        const iqr = q3 - q1
        const lowerBound = q1 - 2.5 * iqr  // Plus permissif (était 1.5)
        const upperBound = q3 + 2.5 * iqr  // Plus permissif (était 1.5)

        if (smoothedVelocity < lowerBound || smoothedVelocity > upperBound) {
          continue
        }
      }

      filteredPoints.push({
        hr,
        velocity: smoothedVelocity,
        time,
        distanceInterval
      })
    }

    // Statistiques par zone FC pour debug
    const zoneStats: { [key: string]: number } = {}
    filteredPoints.forEach(point => {
      if (point.hr >= 190) {
        zoneStats['190+'] = (zoneStats['190+'] || 0) + 1
      } else if (point.hr >= 180) {
        zoneStats['180-190'] = (zoneStats['180-190'] || 0) + 1
      } else if (point.hr >= 170) {
        zoneStats['170-180'] = (zoneStats['170-180'] || 0) + 1
      }
    })
    
    console.log(`Filtrage: ${heartrateData.length} points → ${filteredPoints.length} points valides`)
    console.log('Points haute intensité:', zoneStats)
    return filteredPoints
  }

  // Fonction pour calculer les statistiques des boîtes à moustaches
  const calculateBoxplotStats = (values: number[]) => {
    if (values.length === 0) return null
    
    const sorted = [...values].sort((a, b) => a - b)
    const n = sorted.length
    
    const q1 = sorted[Math.floor(n * 0.25)]
    const median = sorted[Math.floor(n * 0.5)]
    const q3 = sorted[Math.floor(n * 0.75)]
    const mean = values.reduce((sum, val) => sum + val, 0) / n
    
    // Calcul des whiskers (extrêmes)
    const iqr = q3 - q1
    const lowerWhisker = Math.max(sorted[0], q1 - 1.5 * iqr)
    const upperWhisker = Math.min(sorted[n - 1], q3 + 1.5 * iqr)
    
    return {
      min: sorted[0],
      q1,
      median,
      mean,
      q3,
      max: sorted[n - 1],
      lowerWhisker,
      upperWhisker,
      count: n
    }
  }

  // Fonction pour analyser les streams détaillés et calculer les rythmes par zone FC
  const analyzeDetailedStreams = async () => {
    setIsAnalyzingStreams(true)
    
    try {
      const zones = [
        { name: 'Zone 100-110', min: 100, max: 110, color: 'bg-blue-100' },
        { name: 'Zone 110-120', min: 110, max: 120, color: 'bg-blue-200' },
        { name: 'Zone 120-130', min: 120, max: 130, color: 'bg-green-100' },
        { name: 'Zone 130-140', min: 130, max: 140, color: 'bg-green-200' },
        { name: 'Zone 140-150', min: 140, max: 150, color: 'bg-yellow-100' },
        { name: 'Zone 150-160', min: 150, max: 160, color: 'bg-yellow-200' },
        { name: 'Zone 160-170', min: 160, max: 170, color: 'bg-orange-100' },
        { name: 'Zone 170-180', min: 170, max: 180, color: 'bg-orange-200' },
        { name: 'Zone 180-190', min: 180, max: 190, color: 'bg-red-100' },
        { name: 'Zone 190+', min: 190, max: 220, color: 'bg-red-200' }
      ]

      // Initialiser les zones avec des tableaux pour stocker tous les rythmes et distances
      const zoneData: { [key: string]: { paces: number[], distances: number[] } } = {}
      zones.forEach(zone => {
        zoneData[zone.name] = { paces: [], distances: [] }
      })


      // Analyser chaque activité avec streams
      const activitiesWithStreams = runningActivities.filter(activity => 
        activity.activity_id && activity.average_heartrate > 0
      )

      console.log(`Analyse de ${activitiesWithStreams.length} activités avec streams...`)

      for (const activity of activitiesWithStreams) {
        try {
          // Récupérer les streams de l'activité
          const streamsData = await activityService.getEnrichedActivityStreams(activity.activity_id)
          
          if (streamsData?.streams?.heartrate && streamsData?.streams?.velocity_smooth && streamsData?.streams?.time) {
            const heartrateData = streamsData.streams.heartrate
            const velocityData = streamsData.streams.velocity_smooth // m/s
            const timeData = streamsData.streams.time // secondes
            const distanceData = streamsData.streams.distance || [] // mètres

            // Appliquer des filtres pour lisser les données
            const filteredData = applyDataFilters(heartrateData, velocityData, timeData, distanceData)
            
            // Analyser chaque point de données filtré
            for (const point of filteredData) {
              const { hr, velocity, time, distanceInterval } = point
              
              if (hr && hr >= 100 && hr < 220 && velocity && velocity > 0 && time) {
                // Convertir la vitesse en rythme (min/km)
                const paceMinutesPerKm = (1000 / velocity) / 60 // (1000m / vitesse_m_s) / 60s
                
                // La distance est déjà calculée dans applyDataFilters
                
                // Trouver la zone correspondante
                const zone = zones.find(z => hr >= z.min && hr < z.max)
                if (zone && distanceInterval > 0) {
                  zoneData[zone.name].paces.push(paceMinutesPerKm)
                  zoneData[zone.name].distances.push(distanceInterval)
                }
              }
            }
          }
        } catch (error) {
          console.warn(`Erreur analyse streams activité ${activity.activity_id}:`, error)
        }
      }

      // Calculer les moyennes et statistiques pour chaque zone
      const zoneAnalysis = zones.map(zone => {
        const zonePaces = zoneData[zone.name].paces
        const zoneDistances = zoneData[zone.name].distances
        const count = zonePaces.length
        
        if (count === 0) {
          return {
            ...zone,
            count: 0,
            avgPace: null,
            totalDistance: 0,
            totalTime: 0,
            totalDataPoints: 0,
            boxplotStats: null
          }
        }

        const avgPaceMinutes = zonePaces.reduce((sum, pace) => sum + pace, 0) / count
        const totalDistance = zoneDistances.reduce((sum, dist) => sum + dist, 0)
        const totalTime = count * 5 / 3600 // Estimation: 5 secondes par point de données

        // Calculer les statistiques des boîtes à moustaches
        const boxplotStats = calculateBoxplotStats(zonePaces)

        return {
          ...zone,
          count: activitiesWithStreams.length, // Nombre d'activités analysées
          avgPace: avgPaceMinutes / 60, // Convertir en heures pour cohérence avec formatPace
          totalDistance,
          totalTime,
          totalDataPoints: count,
          boxplotStats
        }
      })

      // Préparer les données pour le graphique en boîtes à moustaches
      const boxplotChartData = zones.map(zone => {
        const zonePaces = zoneData[zone.name].paces
        const stats = calculateBoxplotStats(zonePaces)
        
        if (!stats || stats.count === 0) {
          return {
            zone: zone.name,
            fcRange: `${zone.min}-${zone.max}`,
            count: 0,
            q1: 0,
            median: 0,
            mean: 0,
            q3: 0,
            min: 0,
            max: 0,
            lowerWhisker: 0,
            upperWhisker: 0
          }
        }

        return {
          zone: zone.name,
          fcRange: `${zone.min}-${zone.max}`,
          count: stats.count,
          q1: stats.q1,
          median: stats.median,
          mean: stats.mean,
          q3: stats.q3,
          min: stats.min,
          max: stats.max,
          lowerWhisker: stats.lowerWhisker,
          upperWhisker: stats.upperWhisker
        }
      })

      console.log('Analyse des streams terminée:', zoneAnalysis)
      console.log('Données boxplot:', boxplotChartData)
      
      setDetailedZoneAnalysis({ zones: zoneAnalysis, hasData: true })
      setBoxplotData(boxplotChartData)
      return { zones: zoneAnalysis, hasData: true }

    } catch (error) {
      console.error('Erreur analyse streams:', error)
      return { zones: [], hasData: false }
    } finally {
      setIsAnalyzingStreams(false)
    }
  }

  // Effectuer l'analyse des streams au chargement
  useEffect(() => {
    if (runningActivities.length > 0) {
      analyzeDetailedStreams()
    }
  }, [runningActivities])


  const performPrediction = (targetDistance: number, targetElevation: number): RacePrediction => {
    if (runningActivities.length === 0) {
      return {
        distance: targetDistance,
        elevation: targetElevation,
        predictedTime: 0,
        pace: 0,
        confidence: 0,
        similarActivities: 0,
        difficulty: 'Moderate'
      }
    }

    // Déterminer le type de course basé sur le dénivelé
    const targetElevationPerKm = targetElevation / targetDistance
    const isTrailRace = targetElevationPerKm > 50 // Plus de 50m de dénivelé par km = trail
    
    // Choisir les activités de référence selon le type de course
    const referenceActivities = isTrailRace ? trailRunningActivities : roadRunningActivities
    
    // Si pas assez d'activités du bon type, utiliser toutes les activités avec un ajustement
    const activitiesToUse = referenceActivities.length >= 3 ? referenceActivities : runningActivities

    // Calculer les performances moyennes
    const avgPace = activitiesToUse.reduce((sum, act) => sum + act.pace_per_km, 0) / activitiesToUse.length
    const avgElevationPerKm = activitiesToUse.reduce((sum, act) => sum + act.elevation_per_km, 0) / activitiesToUse.length

    // Ajustement spécial si on utilise des activités de l'autre type
    let typeAdjustment = 1.0
    if (isTrailRace && referenceActivities.length < 3 && roadRunningActivities.length > 0) {
      // Course trail mais peu d'activités trail : ralentir de 20-30%
      typeAdjustment = 1.25
    } else if (!isTrailRace && referenceActivities.length < 3 && trailRunningActivities.length > 0) {
      // Course route mais peu d'activités route : accélérer de 15-20%
      typeAdjustment = 0.85
    }

    // Ajuster le rythme selon le dénivelé
    const elevationAdjustment = calculateElevationAdjustment(targetElevationPerKm, avgElevationPerKm)
    
    // Ajuster selon la distance
    const distanceAdjustment = calculateDistanceAdjustment(targetDistance)
    
    // Calculer le rythme prédit
    const predictedPace = avgPace * elevationAdjustment * distanceAdjustment * typeAdjustment
    const predictedTime = predictedPace * targetDistance

    // Calculer la confiance basée sur le nombre d'activités similaires
    const similarActivities = activitiesToUse.filter(act => 
      Math.abs(act.distance_km - targetDistance) <= targetDistance * 0.3 &&
      Math.abs(act.elevation_per_km - targetElevationPerKm) <= targetElevationPerKm * 0.5
    ).length

    // Réduire la confiance si on utilise des activités d'un autre type
    let confidence = Math.min(95, 50 + (similarActivities * 5))
    if (referenceActivities.length < 3) {
      confidence = Math.max(30, confidence - 20) // Réduire la confiance de 20 points
    }

    // Déterminer la difficulté
    const difficulty = determineDifficulty(targetDistance, targetElevation)

    return {
      distance: targetDistance,
      elevation: targetElevation,
      predictedTime,
      pace: predictedPace,
      confidence,
      similarActivities,
      difficulty
    }
  }

  const calculateElevationAdjustment = (targetElevationPerKm: number, avgElevationPerKm: number): number => {
    const elevationRatio = targetElevationPerKm / Math.max(avgElevationPerKm, 10) // Éviter division par 0
    return 1 + (elevationRatio - 1) * 0.3 // Ajustement modéré
  }

  const calculateDistanceAdjustment = (distance: number): number => {
    // Plus la distance est longue, plus le rythme ralentit
    if (distance <= 5) return 1.0
    if (distance <= 10) return 1.05
    if (distance <= 21.1) return 1.15
    if (distance <= 42.2) return 1.30
    return 1.45
  }

  const determineDifficulty = (distance: number, elevation: number): 'Easy' | 'Moderate' | 'Hard' | 'Very Hard' => {
    const elevationPerKm = elevation / distance
    const difficultyScore = (distance / 10) + (elevationPerKm / 50)
    
    if (difficultyScore <= 1.5) return 'Easy'
    if (difficultyScore <= 2.5) return 'Moderate'
    if (difficultyScore <= 4) return 'Hard'
    return 'Very Hard'
  }

  const formatTime = (hours: number): string => {
    const h = Math.floor(hours)
    const m = Math.floor((hours - h) * 60)
    const s = Math.floor(((hours - h) * 60 - m) * 60)
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }

  const formatTimeFromMinutes = (minutes: number): string => {
    const hours = Math.floor(minutes / 60)
    const mins = Math.floor(minutes % 60)
    return `${hours}h${mins.toString().padStart(2, '0')}`
  }

  const addCustomRavito = () => {
    if (newRavitoKm > 0 && newRavitoName.trim()) {
      setCustomRavitos([...customRavitos, { km: newRavitoKm, name: newRavitoName.trim() }])
      setNewRavitoKm(0)
      setNewRavitoName('')
    }
  }

  const removeCustomRavito = (index: number) => {
    setCustomRavitos(customRavitos.filter((_, i) => i !== index))
  }

  const getRavitoPassageTime = (km: number): string => {
    if (!gpxPrediction?.segments) return 'N/A'
    
    let cumulativeDistance = 0
    let cumulativeTime = 0
    
    for (const segment of gpxPrediction.segments) {
      cumulativeDistance += segment.distance_km
      cumulativeTime = segment.cumulative_time_min
      
      if (cumulativeDistance >= km) {
        return formatTimeFromMinutes(cumulativeTime)
      }
    }
    
    return 'N/A'
  }

  const calculateSegmentMetrics = (startKm: number, endKm: number) => {
    if (!gpxPrediction?.elevation_points) return null
    
    const points = gpxPrediction.elevation_points.filter((point: any) => 
      point.distance_km >= startKm && point.distance_km <= endKm
    )
    
    if (points.length < 2) return null
    
    let elevationGain = 0
    let elevationLoss = 0
    
    for (let i = 1; i < points.length; i++) {
      const elevDiff = points[i].elevation_m - points[i-1].elevation_m
      if (elevDiff > 0) {
        elevationGain += elevDiff
      } else {
        elevationLoss += Math.abs(elevDiff)
      }
    }
    
    const distance = endKm - startKm
    const netElevation = elevationGain - elevationLoss
    const avgGrade = distance > 0 ? (netElevation / distance / 10) : 0 // Convertir en %
    
    return {
      elevationGain: Math.round(elevationGain),
      elevationLoss: Math.round(elevationLoss),
      netElevation: Math.round(netElevation),
      avgGrade: Math.round(avgGrade * 10) / 10,
      distance: Math.round(distance * 100) / 100
    }
  }

  const handleChartClick = (data: any) => {
    if (!segmentMode) return
    
    if (!isSelecting) {
      // Premier clic : début de sélection
      setSelectedSegment({ start: data.distance_km, end: data.distance_km })
      setIsSelecting(true)
    } else {
      // Deuxième clic : fin de sélection
      if (selectedSegment) {
        const start = Math.min(selectedSegment.start, data.distance_km)
        const end = Math.max(selectedSegment.start, data.distance_km)
        setSelectedSegment({ start, end })
        setIsSelecting(false)
      }
    }
  }


  const createChart = (elevationPoints: any[]) => {
    // Vérifier si Chart.js est déjà chargé
    if (!(window as any).Chart) {
      // Charger Chart.js depuis CDN
      const script = document.createElement('script')
      script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.js'
      script.onload = () => {
        createChart(elevationPoints)
      }
      document.head.appendChild(script)
      return
    }

    const ctx = document.getElementById('elevation-chart') as HTMLCanvasElement
    if (!ctx) return

    // Nettoyer le conteneur
    ctx.innerHTML = ''
    
    const canvas = document.createElement('canvas')
    canvas.width = ctx.offsetWidth
    canvas.height = 350
    ctx.appendChild(canvas)

    // Préparer les données pour les ravitos
    const ravitoPoints = gpxPrediction?.ravito_points || []
    console.log('Ravito points:', ravitoPoints)
    
    const ravitoData = ravitoPoints.map((ravito: any) => ({
      x: ravito.distance_km,
      y: elevationPoints.find((p: any) => Math.abs(p.distance_km - ravito.distance_km) < 0.1)?.elevation_m || 0,
      ravitoName: ravito.name || `Ravito ${ravito.distance_km}km`,
      ravitoTime: formatTimeFromMinutes(ravito.predicted_time_min || ravito.cumulative_time_min)
    }))

    console.log('Ravito data:', ravitoData)

    // Calculer les limites de la trace
    const maxDistance = Math.max(...elevationPoints.map((p: any) => p.distance_km))
    const minElevation = Math.min(...elevationPoints.map((p: any) => p.elevation_m))
    const maxElevation = Math.max(...elevationPoints.map((p: any) => p.elevation_m))

    const chart = new (window as any).Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        labels: elevationPoints.map((point: any) => point.distance_km.toFixed(1) + 'km'),
        datasets: [
          {
            label: 'Altitude',
            data: elevationPoints.map((point: any) => ({
              x: point.distance_km,
              y: point.elevation_m
            })),
            borderColor: '#2563eb',
            backgroundColor: '#3b82f6',
            fill: true,
            tension: 0.1,
            pointRadius: 0,
            pointHoverRadius: 4
          },
          {
            label: 'Ravitos',
            data: ravitoData,
            type: 'scatter',
            borderColor: '#dc2626',
            backgroundColor: '#dc2626',
            pointRadius: 8,
            pointHoverRadius: 10,
            showLine: false,
            pointStyle: 'triangle',
            pointBackgroundColor: '#dc2626',
            pointBorderColor: '#ffffff',
            pointBorderWidth: 2
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: {
          padding: {
            left: 10,
            right: 10,
            top: 10,
            bottom: 10
          }
        },
        interaction: {
          intersect: false,
          mode: 'index'
        },
        plugins: {
          tooltip: {
            enabled: true,
            callbacks: {
              title: (context: any) => {
                const distance = context[0].parsed.x
                const point = context[0].raw
                
                if (point.ravitoName) {
                  return `🥤 ${point.ravitoName}`
                }
                return `Km ${distance.toFixed(1)}`
              },
              label: (context: any) => {
                const point = context[0].raw
                
                if (point.ravitoName) {
                  return [
                    `Altitude: ${context.parsed.y}m`,
                    `Temps passage: ${point.ravitoTime}`
                  ]
                } else {
                  return `Altitude: ${context.parsed.y}m`
                }
              },
              afterBody: (context: any) => {
                const distance = context[0].parsed.x
                const point = context[0].raw
                
                if (!point.ravitoName) {
                  // Trouver le segment le plus proche
                  const segment = gpxPrediction?.segments?.reduce((closest: any, current: any) => {
                    const closestDistance = Math.abs(closest.distance_km - distance)
                    const currentDistance = Math.abs(current.distance_km - distance)
                    return currentDistance < closestDistance ? current : closest
                  })
                  
                  if (segment) {
                    const distanceRatio = distance / segment.distance_km
                    const estimatedTime = segment.cumulative_time_min * distanceRatio
                    return [`Temps passage: ${formatTimeFromMinutes(estimatedTime)}`]
                  }
                }
                
                return []
              }
            }
          },
          legend: {
            display: true,
            position: 'top',
            labels: {
              usePointStyle: true,
              padding: 20
            }
          }
        },
        scales: {
          x: {
            type: 'linear',
            min: 0,
            max: maxDistance,
            title: {
              display: true,
              text: 'Distance (km)'
            },
            ticks: {
              callback: function(value: any) {
                return Number(value) % 1 === 0 ? `${value}km` : `${Number(value).toFixed(1)}km`
              }
            }
          },
          y: {
            min: minElevation - 50,
            max: maxElevation + 50,
            title: {
              display: true,
              text: 'Altitude (m)'
            }
          }
        }
      }
    })

    console.log('Graphique Chart.js créé avec succès')
  }

  const handleGpxUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    console.log('handleGpxUpload appelé', event.target.files)
    const file = event.target.files?.[0]
    if (!file) {
      console.log('Aucun fichier sélectionné')
      return
    }

    console.log('Fichier sélectionné:', file.name, file.size, file.type)

    if (!file.name.toLowerCase().endsWith('.gpx')) {
      alert('Veuillez sélectionner un fichier GPX')
      return
    }

    setIsUploadingGpx(true)
    setGpxPrediction(null)

    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('custom_ravitos', JSON.stringify(customRavitos))

      console.log('Envoi de la requête vers l\'API...')
      const response = await fetch('http://localhost:4100/api/v1/prediction/gpx-pace-prediction', {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        throw new Error('Erreur lors de la prédiction')
      }

      const prediction = await response.json()
      setGpxPrediction(prediction)
      
      // Créer le graphique Chart.js après réception des données
      if (prediction.elevation_points) {
        setTimeout(() => createChart(prediction.elevation_points), 100)
      }
    } catch (error) {
      console.error('Erreur upload GPX:', error)
      alert('Erreur lors de l\'upload du fichier GPX')
    } finally {
      setIsUploadingGpx(false)
    }
  }

  const handleFileButtonClick = () => {
    console.log('Bouton cliqué, tentative d\'ouverture du sélecteur de fichier')
    if (fileInputRef.current) {
      console.log('fileInputRef.current existe:', fileInputRef.current)
      fileInputRef.current.click()
    } else {
      console.error('fileInputRef.current est null')
    }
  }

  const formatPace = (paceHours: number): string => {
    const minutes = Math.floor(paceHours * 60)
    const seconds = Math.floor((paceHours * 60 - minutes) * 60)
    return `${minutes}:${seconds.toString().padStart(2, '0')}`
  }


  return (
    <div className={`space-y-6 ${className}`}>
      {/* En-tête */}
      <div className="text-center">
        <div className="flex items-center justify-center mb-2">
          <Activity className="h-6 w-6 text-blue-600 mr-2" />
          <h3 className="text-xl font-bold text-gray-900">Analyse de Performance</h3>
          <div className="text-xs text-purple-600 bg-purple-100 px-2 py-1 rounded ml-2">
            🤖 IA entraînée
          </div>
        </div>
        <p className="text-gray-600">
          Basé sur vos performances des 6 derniers mois ({roadRunningActivities.length} courses route, {trailRunningActivities.length} trails)
        </p>
        <div className="mt-2 text-xs text-blue-600 bg-blue-50 p-2 rounded">
          <p><strong>🔧 Filtres appliqués :</strong> Distance ≥1km, Temps ≥5min, Rythme 2-15min/km, FC 60-200BPM, Dénivelé ≤200m/km</p>
        </div>
      </div>


      {/* Statistiques des 6 derniers mois */}
      {runningActivities.length > 0 && (
        <div className="bg-gray-50 p-4 rounded-lg">
          <div className="flex items-center justify-between mb-3">
            <h5 className="font-medium text-gray-900">📊 Vos performances récentes (6 mois)</h5>
            <div className="text-xs text-green-600 bg-green-50 px-2 py-1 rounded">
              ✓ Données filtrées
            </div>
          </div>
          
          {/* Statistiques générales */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mb-4">
            <div className="text-center">
              <div className="text-lg font-bold text-gray-900">{runningActivities.length}</div>
              <div className="text-gray-600">Total sorties</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-gray-900">
                {(runningActivities.reduce((sum, act) => sum + act.distance_km, 0) / runningActivities.length).toFixed(1)}
              </div>
              <div className="text-gray-600">Distance moy. (km)</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-gray-900">
                {formatPace(runningActivities.reduce((sum, act) => sum + act.pace_per_km, 0) / runningActivities.length)}
              </div>
              <div className="text-gray-600">Rythme moy. global</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-gray-900">
                {Math.round(runningActivities.reduce((sum, act) => sum + act.elevation_per_km, 0) / runningActivities.length)}
              </div>
              <div className="text-gray-600">Dénivelé moy. (m/km)</div>
            </div>
          </div>

          {/* Statistiques séparées par type */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Route */}
            {roadRunningActivities.length > 0 && (
              <div className="bg-white p-3 rounded border">
                <h6 className="font-medium text-blue-700 mb-2">🏃‍♂️ Course Route ({roadRunningActivities.length} sorties)</h6>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <span className="text-gray-600">Rythme moy.:</span>
                    <span className="font-medium ml-1">
                      {formatPace(roadRunningActivities.reduce((sum, act) => sum + act.pace_per_km, 0) / roadRunningActivities.length)}
              </span>
            </div>
                  <div>
                    <span className="text-gray-600">Distance moy.:</span>
                    <span className="font-medium ml-1">
                      {(roadRunningActivities.reduce((sum, act) => sum + act.distance_km, 0) / roadRunningActivities.length).toFixed(1)}km
                    </span>
          </div>
          </div>
        </div>
      )}

            {/* Trail */}
            {trailRunningActivities.length > 0 && (
              <div className="bg-white p-3 rounded border">
                <h6 className="font-medium text-green-700 mb-2">🥾 Trail ({trailRunningActivities.length} sorties)</h6>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <span className="text-gray-600">Rythme moy.:</span>
                    <span className="font-medium ml-1">
                      {formatPace(trailRunningActivities.reduce((sum, act) => sum + act.pace_per_km, 0) / trailRunningActivities.length)}
                    </span>
            </div>
                  <div>
                    <span className="text-gray-600">Distance moy.:</span>
                    <span className="font-medium ml-1">
                      {(trailRunningActivities.reduce((sum, act) => sum + act.distance_km, 0) / trailRunningActivities.length).toFixed(1)}km
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Analyse des zones de rythme cardiaque */}
      {(heartRateZoneAnalysis.hasData || detailedZoneAnalysis?.hasData) && (
        <div className="bg-gray-50 p-4 rounded-lg">
          <div className="flex items-center justify-between mb-3">
            <h5 className="font-medium text-gray-900">❤️ Analyse par Zones de Rythme Cardiaque</h5>
            <div className="flex items-center gap-3">
              <div className="text-xs text-green-600 bg-green-50 px-2 py-1 rounded">
                ✓ Données filtrées
              </div>
              {!detailedZoneAnalysis && (
                <button
                  onClick={analyzeDetailedStreams}
                  disabled={isAnalyzingStreams}
                  className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400"
                >
                  Analyser les données détaillées
                </button>
              )}
              {isAnalyzingStreams && (
                <div className="flex items-center text-sm text-blue-600">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div>
                  Analyse des données détaillées...
                </div>
              )}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-2 px-3 font-medium text-gray-700">Zone</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-700">Fréquence (BPM)</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-700">Points de Données</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-700">Rythme Moy.</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-700">Distance Parcourue</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-700">Temps Total</th>
                </tr>
              </thead>
              <tbody>
                {(detailedZoneAnalysis?.zones || heartRateZoneAnalysis.zones).map((zone: any, index: number) => (
                  <tr key={index} className={`border-b border-gray-100 ${zone.color}`}>
                    <td className="py-2 px-3 font-medium text-gray-800">{zone.name}</td>
                    <td className="py-2 px-3 text-gray-600">{zone.min}-{zone.max} BPM</td>
                    <td className="py-2 px-3 text-gray-600">{zone.totalDataPoints || 0}</td>
                    <td className="py-2 px-3 text-gray-600">
                      {zone.avgPace ? formatPace(zone.avgPace) : '-'}
                    </td>
                    <td className="py-2 px-3 text-gray-600">
                      {zone.totalDistance ? `${zone.totalDistance.toFixed(1)} km` : '-'}
                    </td>
                    <td className="py-2 px-3 text-gray-600">
                      {zone.totalTime > 0 ? formatTime(zone.totalTime) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            
          {/* Résumé des zones les plus utilisées */}
          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
            {(() => {
              const zonesToUse = detailedZoneAnalysis?.zones || heartRateZoneAnalysis.zones
                const topZones = zonesToUse
                  .filter((zone: any) => (zone.totalDataPoints || zone.count) > 0)
                  .sort((a: any, b: any) => (b.totalDataPoints || b.count) - (a.totalDataPoints || a.count))
                  .slice(0, 3)

                return topZones.map((zone: any, index: number) => (
                <div key={index} className="bg-white p-3 rounded border">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium text-sm text-gray-800">{zone.name}</span>
                    <span className="text-xs text-gray-500">{zone.totalDataPoints || zone.count} pts</span>
            </div>
                  <div className="text-sm text-gray-600 space-y-1">
                    <div>Rythme: {zone.avgPace ? formatPace(zone.avgPace) : 'N/A'}</div>
                    {zone.totalDistance && (
                      <div>Distance: {zone.totalDistance.toFixed(1)} km</div>
                    )}
          </div>
                </div>
              ))
            })()}
          </div>
        </div>
      )}

      {/* Graphique en boîtes à moustaches */}
      {boxplotData.length > 0 && boxplotData.some(d => d.count > 0) && (
        <div className="bg-gray-50 p-4 rounded-lg">
          <div className="flex items-center justify-between mb-3">
            <h5 className="font-medium text-gray-900">📊 Distribution des Rythmes par Zone de FC (Boîtes à Moustaches - 6 mois)</h5>
            <div className="text-xs text-green-600 bg-green-50 px-2 py-1 rounded">
              ✓ Données filtrées
                </div>
                </div>
          
          <div className="h-96 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={boxplotData.filter(d => d.count > 0)}
                margin={{
                  top: 20,
                  right: 30,
                  left: 60,
                  bottom: 20,
                }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  dataKey="fcRange"
                  name="Zone FC"
                  label={{ value: 'Zone de Fréquence Cardiaque (BPM)', position: 'insideBottom', offset: -10 }}
                />
                <YAxis 
                  domain={[2.5, 10]}
                  name="Rythme"
                  unit=" min/km"
                  label={{ value: 'Rythme (min/km)', angle: -90, position: 'insideLeft' }}
                />
                <Tooltip 
                  formatter={(value, name) => {
                    const formatValue = (val: number) => `${val.toFixed(2)} min/km`
                    switch (name) {
                      case 'q1': return [formatValue(value as number), 'Q1 (25%)']
                      case 'median': return [formatValue(value as number), 'Médiane (50%)']
                      case 'q3': return [formatValue(value as number), 'Q3 (75%)']
                      case 'mean': return [formatValue(value as number), 'Moyenne']
                      case 'min': return [formatValue(value as number), 'Minimum']
                      case 'max': return [formatValue(value as number), 'Maximum']
                      case 'count': return [`${value} points`, 'Nombre de données']
                      default: return [value, name]
                    }
                  }}
                  labelFormatter={(label, payload) => {
                    if (payload && payload[0]) {
                      const data = payload[0].payload
                      return `Zone ${data.fcRange} BPM (${data.count} points)`
                    }
                    return label
                  }}
                />
                
                {/* Barres pour la boîte (Q1 à Q3) */}
                <Bar 
                  dataKey="q3" 
                  fill="rgba(59, 130, 246, 0.3)" 
                  stroke="#3b82f6" 
                  strokeWidth={1}
                  name="Q3"
                />
                <Bar 
                  dataKey="q1" 
                  fill="rgba(255, 255, 255, 0.8)" 
                  stroke="#3b82f6" 
                  strokeWidth={1}
                  name="Q1"
                />
                
                {/* Lignes pour la médiane, moyenne, et extrêmes */}
                <Line 
                  type="monotone" 
                  dataKey="median" 
                  stroke="#1e40af" 
                  strokeWidth={3}
                  dot={{ fill: '#1e40af', r: 4 }}
                  name="Médiane"
                />
                <Line 
                  type="monotone" 
                  dataKey="mean" 
                  stroke="#dc2626" 
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  dot={{ fill: '#dc2626', r: 3 }}
                  name="Moyenne"
                />
                <Line 
                  type="monotone" 
                  dataKey="upperWhisker" 
                  stroke="#6b7280" 
                  strokeWidth={1}
                  dot={{ fill: '#6b7280', r: 2 }}
                  name="Extrême haut"
                />
                <Line 
                  type="monotone" 
                  dataKey="lowerWhisker" 
                  stroke="#6b7280" 
                  strokeWidth={1}
                  dot={{ fill: '#6b7280', r: 2 }}
                  name="Extrême bas"
                />
                
                {/* Lignes de référence pour les zones importantes */}
                <ReferenceLine y={3.5} stroke="#10b981" strokeDasharray="5 5" label={{ value: "Seuil rapide", position: "top" }} />
                <ReferenceLine y={5.0} stroke="#f59e0b" strokeDasharray="5 5" label={{ value: "Seuil moyen", position: "top" }} />
                <ReferenceLine y={6.5} stroke="#ef4444" strokeDasharray="5 5" label={{ value: "Seuil lent", position: "top" }} />
              </ComposedChart>
            </ResponsiveContainer>
                </div>

          {/* Légende et interprétation */}
          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
            <div className="bg-blue-50 p-3 rounded border border-blue-200">
              <h6 className="font-medium text-blue-900 mb-2">📦 Éléments du graphique</h6>
              <div className="text-blue-800 space-y-1">
                <p>• <strong>Barres bleues</strong> : Q1 (25%) à Q3 (75%)</p>
                <p>• <strong>Ligne bleue</strong> : Médiane (50%)</p>
                <p>• <strong>Ligne rouge</strong> : Moyenne (pointillés)</p>
                <p>• <strong>Lignes grises</strong> : Extrêmes</p>
              </div>
                </div>
            
            <div className="bg-green-50 p-3 rounded border border-green-200">
              <h6 className="font-medium text-green-900 mb-2">💡 Interprétation</h6>
              <div className="text-green-800 space-y-1">
                <p>• <strong>Barres étroites</strong> : Rythme constant dans la zone</p>
                <p>• <strong>Barres larges</strong> : Grande variabilité</p>
                <p>• <strong>Écart médiane/moyenne</strong> : Distribution asymétrique</p>
                <p>• <strong>Lignes de référence</strong> : Seuils de performance</p>
                </div>
              </div>
            
            <div className="bg-orange-50 p-3 rounded border border-orange-200">
              <h6 className="font-medium text-orange-900 mb-2">🎯 Zones analysées</h6>
              <div className="text-orange-800 space-y-1">
                {boxplotData.filter(d => d.count > 0).map((data, index) => (
                  <p key={index}>
                    <strong>{data.fcRange} BPM</strong>: {data.count} points
                  </p>
                ))}
            </div>
          </div>
          </div>
        </div>
      )}

      {/* Graphique Impact du Dénivelé sur le Rythme */}
      {elevationPaceData.length > 0 && (
        <div className="bg-gray-50 p-4 rounded-lg">
          <div className="flex items-center justify-between mb-3">
            <h5 className="font-medium text-gray-900">🏔️ Impact du Dénivelé sur le Rythme de Course (6 derniers mois)</h5>
            <div className="text-xs text-green-600 bg-green-50 px-2 py-1 rounded">
              ✓ Données filtrées
            </div>
          </div>
          
          <div className="h-96 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart
                data={elevationPaceData}
                margin={{
                  top: 20,
                  right: 30,
                  left: 60,
                  bottom: 20,
                }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  type="number" 
                  dataKey="elevationPerKm" 
                  name="Dénivelé"
                  unit=" m/km"
                  domain={[0, 'dataMax + 10']}
                  label={{ value: 'Dénivelé par km (m/km)', position: 'insideBottom', offset: -10 }}
                />
                <YAxis 
                  type="number" 
                  dataKey="pacePerKm" 
                  name="Rythme"
                  unit=" min/km"
                  domain={['dataMin - 0.5', 'dataMax + 0.5']}
                  label={{ value: 'Rythme (min/km)', angle: -90, position: 'insideLeft' }}
                />
                <Tooltip 
                  formatter={(value, name) => {
                    if (name === 'elevationPerKm') return [`${Number(value).toFixed(1)} m/km`, 'Dénivelé/km']
                    if (name === 'pacePerKm') return [`${Number(value).toFixed(2)} min/km`, 'Rythme']
                    if (name === 'distance') return [`${Number(value).toFixed(1)} km`, 'Distance']
                    if (name === 'totalElevation') return [`${Number(value).toFixed(0)} m`, 'Dénivelé total']
                    if (name === 'avgHeartRate') return [`${Number(value).toFixed(0)} BPM`, 'FC moyenne']
                    return [value, name]
                  }}
                  labelFormatter={(label, payload) => {
                    if (payload && payload[0]) {
                      const data = payload[0].payload
                      const date = new Date(data.date).toLocaleDateString('fr-FR')
                      return `${data.activityName} (${data.activityType}) - ${date}`
                    }
                    return label
                  }}
                />
                <Scatter 
                  name="Activités" 
                  dataKey="pacePerKm" 
                  fill="#3b82f6"
                  fillOpacity={0.7}
                />
              </ScatterChart>
            </ResponsiveContainer>
          </div>

          {/* Statistiques et analyse */}
          <div className="mt-4 grid grid-cols-1 md:grid-cols-4 gap-4 text-sm">
            <div className="bg-blue-50 p-3 rounded border border-blue-200">
              <div className="font-medium text-blue-900 mb-1">📊 Activités analysées</div>
              <div className="text-blue-800">{elevationPaceData.length} sorties</div>
              <div className="text-xs text-blue-600 mt-1">
                {elevationPaceData.filter(d => d.activityType === 'Run').length} route, {' '}
                {elevationPaceData.filter(d => d.activityType === 'TrailRun').length} trail
              </div>
            </div>
            
            <div className="bg-green-50 p-3 rounded border border-green-200">
              <div className="font-medium text-green-900 mb-1">🏔️ Dénivelé analysé</div>
              <div className="text-green-800">
                {Math.min(...elevationPaceData.map(d => d.elevationPerKm)).toFixed(1)} - {' '}
                {Math.max(...elevationPaceData.map(d => d.elevationPerKm)).toFixed(1)} m/km
              </div>
              <div className="text-xs text-green-600 mt-1">
                Moy: {(elevationPaceData.reduce((sum, d) => sum + d.elevationPerKm, 0) / elevationPaceData.length).toFixed(1)} m/km
              </div>
            </div>
            
            <div className="bg-orange-50 p-3 rounded border border-orange-200">
              <div className="font-medium text-orange-900 mb-1">⏱️ Rythme analysé</div>
              <div className="text-orange-800">
                {Math.min(...elevationPaceData.map(d => d.pacePerKm)).toFixed(1)} - {' '}
                {Math.max(...elevationPaceData.map(d => d.pacePerKm)).toFixed(1)} min/km
              </div>
              <div className="text-xs text-orange-600 mt-1">
                Moy: {(elevationPaceData.reduce((sum, d) => sum + d.pacePerKm, 0) / elevationPaceData.length).toFixed(1)} min/km
              </div>
            </div>
            
            <div className="bg-purple-50 p-3 rounded border border-purple-200">
              <div className="font-medium text-purple-900 mb-1">📈 Corrélation</div>
              <div className="text-purple-800">
                {(() => {
                  const n = elevationPaceData.length
                  const sumX = elevationPaceData.reduce((sum, d) => sum + d.elevationPerKm, 0)
                  const sumY = elevationPaceData.reduce((sum, d) => sum + d.pacePerKm, 0)
                  const sumXY = elevationPaceData.reduce((sum, d) => sum + d.elevationPerKm * d.pacePerKm, 0)
                  const sumX2 = elevationPaceData.reduce((sum, d) => sum + d.elevationPerKm * d.elevationPerKm, 0)
                  const sumY2 = elevationPaceData.reduce((sum, d) => sum + d.pacePerKm * d.pacePerKm, 0)
                  
                  const correlation = (n * sumXY - sumX * sumY) / 
                    Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY))
                  
                  return correlation.toFixed(3)
                })()}
              </div>
              <div className="text-xs text-purple-600 mt-1">
                +1 = parfait, 0 = aucune, -1 = inverse
              </div>
            </div>
          </div>

          {/* Interprétation */}
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-blue-50 p-3 rounded border border-blue-200">
              <h6 className="font-medium text-blue-900 mb-2">💡 Comment interpréter ce graphique</h6>
            <div className="text-sm text-blue-800 space-y-1">
                <p>• <strong>Axe X (Dénivelé)</strong> : Plus à droite = plus de montée</p>
                <p>• <strong>Axe Y (Rythme)</strong> : Plus haut = plus lent</p>
                <p>• <strong>Tendance ascendante</strong> : Le dénivelé ralentit</p>
                <p>• <strong>Points éparpillés</strong> : Autres facteurs (forme, météo, etc.)</p>
                <p>• <strong>Bleu</strong> : Course route | <strong>Orange</strong> : Trail</p>
              </div>
            </div>
            
            <div className="bg-green-50 p-3 rounded border border-green-200">
              <h6 className="font-medium text-green-900 mb-2">🎯 Applications pratiques</h6>
              <div className="text-sm text-green-800 space-y-1">
                <p>• <strong>Planification</strong> : Ajuster l'objectif selon le dénivelé</p>
                <p>• <strong>Entraînement</strong> : Cibler les zones de dénivelé faibles/fortes</p>
                <p>• <strong>Progression</strong> : Voir l'évolution de votre adaptation</p>
                <p>• <strong>Comparaison</strong> : Route vs Trail sur même dénivelé</p>
              </div>
            </div>
          </div>
        </div>
      )}


      {/* Message si pas de données de rythme cardiaque */}
      {runningActivities.length > 0 && !heartRateZoneAnalysis.hasData && (
        <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
          <div className="text-center">
            <div className="text-2xl mb-2">❤️</div>
            <p className="text-blue-800 font-medium">Pas de données de rythme cardiaque</p>
            <p className="text-sm text-blue-700 mt-1">
              Connectez une montre ou un capteur cardiaque pour voir l'analyse par zones
            </p>
          </div>
        </div>
      )}

      {/* Upload GPX et Prédiction Avancée */}
      <div className="bg-gradient-to-r from-purple-50 to-blue-50 p-6 rounded-lg border border-purple-200">
        <div className="flex items-center justify-between mb-4">
          <h4 className="font-semibold text-gray-900 flex items-center gap-2">
            <Upload className="w-5 h-5 text-purple-600" />
            Prédiction de Course avec GPX
          </h4>
          <div className="text-xs text-purple-600 bg-purple-100 px-2 py-1 rounded">
            🤖 IA entraînée
          </div>
        </div>
        
        <p className="text-gray-600 mb-4">
          Uploadez un fichier GPX de votre course pour obtenir une prédiction précise segment par segment. 
          <br />
          <span className="text-blue-600 font-medium">🧠 La FC est automatiquement calculée basée sur vos données historiques !</span>
        </p>


         {/* Configuration Points de Ravito */}
         <div className="mb-4">
           <label className="block text-sm font-medium text-gray-700 mb-2">
             🥤 Points de Ravito Personnalisés
           </label>
           
           {/* Liste des ravitos configurés */}
           {customRavitos.length > 0 && (
             <div className="mb-3">
               {customRavitos.map((ravito, index) => (
                 <div key={index} className="flex items-center justify-between bg-blue-50 p-2 rounded border mb-2">
                   <div className="flex items-center gap-3">
                     <span className="font-medium text-blue-800">{ravito.name}</span>
                     <span className="text-sm text-blue-600">km {ravito.km.toFixed(2)}</span>
                     {gpxPrediction && (
                       <span className="text-sm text-green-600 font-medium">
                         Passage: {getRavitoPassageTime(ravito.km)}
                       </span>
              )}
            </div>
                   <button
                     onClick={() => removeCustomRavito(index)}
                     className="text-red-500 hover:text-red-700 text-sm"
                   >
                     ✕
                   </button>
          </div>
               ))}
        </div>
      )}

           {/* Formulaire d'ajout de ravito */}
           <div className="flex gap-2">
             <input
               type="number"
               min="0.1"
               step="0.1"
               value={newRavitoKm || ''}
               onChange={(e) => setNewRavitoKm(parseFloat(e.target.value) || 0)}
               placeholder="km"
               className="w-20 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
             />
             <input
               type="text"
               value={newRavitoName}
               onChange={(e) => setNewRavitoName(e.target.value)}
               placeholder="Nom du ravito"
               className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
             />
             <button
               onClick={addCustomRavito}
               disabled={!newRavitoKm || !newRavitoName.trim()}
               className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
             >
               Ajouter
             </button>
            </div>
              </div>

        {/* Upload GPX */}
        <div className="mb-4">
          <input
            ref={fileInputRef}
            type="file"
            accept=".gpx"
            onChange={handleGpxUpload}
            className="hidden"
          />
          <button
            onClick={handleFileButtonClick}
            disabled={isUploadingGpx}
            className="w-full bg-purple-600 text-white px-4 py-3 rounded-lg hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isUploadingGpx ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                Analyse en cours...
              </>
            ) : (
              <>
                <FileText className="w-4 h-4" />
                Choisir un fichier GPX
              </>
            )}
          </button>
            </div>

        {/* Résultats de prédiction GPX */}
        {gpxPrediction && (
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <h5 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
              <Target className="w-4 h-4 text-green-600" />
              Prédiction pour {gpxPrediction.filename}
            </h5>
            
            {/* Résumé global */}
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-4">
               <div className="bg-blue-50 p-3 rounded border">
                 <div className="text-sm text-blue-600 font-medium">Distance</div>
                 <div className="text-lg font-bold text-blue-800">{gpxPrediction.total_distance_km.toFixed(2)} km</div>
              </div>
               <div className="bg-red-50 p-3 rounded border">
                 <div className="text-sm text-red-600 font-medium">D+</div>
                 <div className="text-lg font-bold text-red-800">+{gpxPrediction.total_elevation_gain_m} m</div>
            </div>
               <div className="bg-cyan-50 p-3 rounded border">
                 <div className="text-sm text-cyan-600 font-medium">D-</div>
                 <div className="text-lg font-bold text-cyan-800">-{gpxPrediction.total_elevation_loss_m} m</div>
              </div>
              <div className="bg-green-50 p-3 rounded border">
                <div className="text-sm text-green-600 font-medium">Temps estimé</div>
                <div className="text-lg font-bold text-green-800">{gpxPrediction.total_time_formatted}</div>
            </div>
              <div className="bg-orange-50 p-3 rounded border">
                <div className="text-sm text-orange-600 font-medium">Rythme moyen</div>
                <div className="text-lg font-bold text-orange-800">{gpxPrediction.avg_pace} min/km</div>
              </div>
            </div>

            {/* Segments détaillés */}
            <div className="mb-4">
              <h6 className="font-medium text-gray-800 mb-2">📊 Segments détaillés</h6>
              <div className="max-h-48 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-1">Segment</th>
                      <th className="text-left py-1">Distance</th>
                      <th className="text-left py-1">D+</th>
                      <th className="text-left py-1">D-</th>
                      <th className="text-left py-1">Pente</th>
                      <th className="text-left py-1">Rythme</th>
                      <th className="text-left py-1">Temps</th>
                      <th className="text-left py-1">Cumulé</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gpxPrediction.segments.map((segment: any, index: number) => (
                       <tr key={index} className="border-b border-gray-100">
                         <td className="py-1 font-medium">{segment.segment_id}</td>
                         <td className="py-1">{segment.distance_km.toFixed(2)} km</td>
                         <td className="py-1 text-red-600">+{segment.elevation_gain_m}m</td>
                         <td className="py-1 text-cyan-600">-{segment.elevation_loss_m}m</td>
                         <td className="py-1">{segment.avg_grade_percent > 0 ? '+' : ''}{segment.avg_grade_percent}%</td>
                         <td className="py-1">{segment.predicted_pace} min/km</td>
                         <td className="py-1">{formatTimeFromMinutes(segment.predicted_time_min)}</td>
                         <td className="py-1">{formatTimeFromMinutes(segment.cumulative_time_min)}</td>
                       </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Graphique profil dénivelé avec Chart.js */}
            <div className="mb-4">
              <h6 className="font-medium text-gray-800 mb-2">📈 Profil Dénivelé de la Course (Interactif)</h6>
              <div className="bg-white p-4 rounded-lg border border-gray-200">
                <div 
                  id="elevation-chart"
                  className="w-full"
                  style={{ height: '400px' }}
                />
                <div className="flex justify-center gap-4 mt-2 text-xs text-gray-600">
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-3 bg-blue-500 rounded"></div>
                    <span>Altitude réelle (points GPX)</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-3 bg-red-500 transform rotate-45"></div>
                    <span>Ravitos</span>
                  </div>
                </div>
                <div className="mt-2 text-center">
                  <p className="text-sm text-blue-600">
                    🖱️ Survolez pour voir les détails • 🥤 Triangles rouges = Ravitos
                  </p>
                </div>
              </div>
            </div>

             {/* Points de ravito personnalisés */}
             {customRavitos.length > 0 && (
               <div>
                 <h6 className="font-medium text-gray-800 mb-2">🥤 Points de ravito personnalisés</h6>
                 <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                   {customRavitos.map((ravito, index) => (
                     <div key={index} className="bg-yellow-50 p-2 rounded border border-yellow-200">
                       <div className="text-sm">
                         <span className="font-medium">{ravito.name}:</span> km {ravito.km.toFixed(2)}
                       </div>
                       <div className="text-xs text-yellow-700">
                         Passage prévu: {getRavitoPassageTime(ravito.km)}
                       </div>
                     </div>
                   ))}
          </div>
        </div>
      )}

             {/* Points de ravito automatiques (si aucun ravito personnalisé) */}
             {customRavitos.length === 0 && gpxPrediction.ravito_points?.length > 0 && (
               <div>
                 <h6 className="font-medium text-gray-800 mb-2">🥤 Points de ravito automatiques</h6>
                 <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                   {gpxPrediction.ravito_points.map((ravito: any, index: number) => (
                     <div key={index} className="bg-yellow-50 p-2 rounded border border-yellow-200">
                       <div className="text-sm">
                         <span className="font-medium">Ravito {index + 1}:</span> {ravito.distance_km.toFixed(2)} km
                       </div>
                       <div className="text-xs text-yellow-700">
                         Passage prévu: {ravito.time_formatted}
                       </div>
                     </div>
                   ))}
                 </div>
               </div>
             )}
          </div>
        )}
      </div>

      {runningActivities.length === 0 && (
        <div className="bg-yellow-50 p-4 rounded-lg border border-yellow-200">
          <div className="text-center">
            <div className="text-4xl mb-2">🏃‍♂️</div>
            <p className="text-yellow-800 font-medium">Pas assez de données</p>
            <p className="text-sm text-yellow-700 mt-1">
              Effectuez quelques sorties de course pour activer le prédicteur
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
