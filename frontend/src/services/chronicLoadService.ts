import { activityService } from './activityService'

interface Activity {
  id: string
  activity_type: string
  start_date: string
  moving_time: number
  average_heart_rate?: number
  max_heart_rate?: number
  distance?: number
  average_pace?: number
}

interface ChronicLoadData {
  date: string
  chronicLoad: number
  acuteLoad: number
  trainingStressBalance: number
}

class ChronicLoadService {
  /**
   * Calcule le TRIMP (Training Impulse) pour une activité
   * TRIMP = durée × HRavg × 0.64 × e^(1.92 × HRavg/HRmax)
   */
  private calculateTRIMP(activity: Activity): number {
    const duration = activity.moving_time / 3600 // Convertir en heures
    const avgHR = activity.average_heart_rate
    const maxHR = activity.max_heart_rate || 220 - 35 // Estimation si pas de max HR (35 ans par défaut)
    
    if (!avgHR || !maxHR) {
      // Fallback : utiliser la distance et le temps pour estimer l'intensité
      return this.estimateTRIMPFromDistance(activity)
    }

    const hrRatio = avgHR / maxHR
    const trimp = duration * avgHR * 0.64 * Math.exp(1.92 * hrRatio)
    
    return trimp
  }

  /**
   * Estimation du TRIMP basée sur la distance et le temps (fallback)
   */
  private estimateTRIMPFromDistance(activity: Activity): number {
    const duration = activity.moving_time / 3600 // Heures
    const distance = activity.distance || 0 // mètres
    const pace = activity.average_pace || 0 // secondes par mètre
    
    // Estimation basée sur la durée et l'intensité estimée
    let intensity = 0.5 // Intensité par défaut (modérée)
    
    if (pace > 0) {
      // Estimer l'intensité basée sur le rythme
      const paceMinPerKm = pace * 1000 / 60 // minutes par km
      if (paceMinPerKm < 4) intensity = 0.9 // Très intense
      else if (paceMinPerKm < 5) intensity = 0.8 // Intense
      else if (paceMinPerKm < 6) intensity = 0.7 // Modérément intense
      else if (paceMinPerKm < 7) intensity = 0.6 // Modéré
      else intensity = 0.5 // Léger
    }
    
    // TRIMP estimé = durée × intensité × 100
    return duration * intensity * 100
  }

  /**
   * Calcule la charge chronique (moyenne sur 28 jours)
   */
  private calculateChronicLoad(trimpData: { date: string; trimp: number }[], targetDate: string): number {
    const target = new Date(targetDate)
    const cutoff = new Date(target)
    cutoff.setDate(cutoff.getDate() - 28)
    
    const relevantData = trimpData.filter(d => {
      const dataDate = new Date(d.date)
      return dataDate >= cutoff && dataDate <= target
    })
    
    if (relevantData.length === 0) return 0
    
    const totalTRIMP = relevantData.reduce((sum, d) => sum + d.trimp, 0)
    return totalTRIMP / 28 // Moyenne sur 28 jours
  }

  /**
   * Calcule la charge aiguë (moyenne sur 7 jours)
   */
  private calculateAcuteLoad(trimpData: { date: string; trimp: number }[], targetDate: string): number {
    const target = new Date(targetDate)
    const cutoff = new Date(target)
    cutoff.setDate(cutoff.getDate() - 7)
    
    const relevantData = trimpData.filter(d => {
      const dataDate = new Date(d.date)
      return dataDate >= cutoff && dataDate <= target
    })
    
    if (relevantData.length === 0) return 0
    
    const totalTRIMP = relevantData.reduce((sum, d) => sum + d.trimp, 0)
    return totalTRIMP / 7 // Moyenne sur 7 jours
  }

  /**
   * Calcule la Training Stress Balance (TSB = Acute - Chronic)
   */
  private calculateTSB(acuteLoad: number, chronicLoad: number): number {
    return acuteLoad - chronicLoad
  }

  /**
   * Obtient les données de charge chronique pour une période donnée
   */
  async getChronicLoadData(startDate: string, endDate: string): Promise<ChronicLoadData[]> {
    try {
      // Récupérer toutes les activités (augmenter la limite pour 6 mois)
      const activities = await activityService.getActivities({ limit: 1000 })
      
      // Filtrer les activités de course à pied et trail
      const runningActivities = activities.filter(activity => 
        ['Run', 'TrailRun', 'VirtualRun'].includes(activity.activity_type)
      )

      if (runningActivities.length === 0) {
        return []
      }

      // Calculer le TRIMP pour chaque activité
      const trimpData = runningActivities.map(activity => ({
        date: activity.start_date.split('T')[0], // Format YYYY-MM-DD
        trimp: this.calculateTRIMP(activity)
      }))

      // Grouper par date et sommer le TRIMP quotidien
      const dailyTRIMP = trimpData.reduce((acc, data) => {
        const date = data.date
        acc[date] = (acc[date] || 0) + data.trimp
        return acc
      }, {} as Record<string, number>)

      // Générer les dates pour la période demandée
      const start = new Date(startDate)
      const end = new Date(endDate)
      const result: ChronicLoadData[] = []

      for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
        const dateStr = d.toISOString().split('T')[0]
        
        // Calculer les charges pour cette date
        const chronicLoad = this.calculateChronicLoad(
          Object.entries(dailyTRIMP).map(([date, trimp]) => ({ date, trimp })),
          dateStr
        )
        
        const acuteLoad = this.calculateAcuteLoad(
          Object.entries(dailyTRIMP).map(([date, trimp]) => ({ date, trimp })),
          dateStr
        )
        
        const trainingStressBalance = this.calculateTSB(acuteLoad, chronicLoad)

        result.push({
          date: dateStr,
          chronicLoad,
          acuteLoad,
          trainingStressBalance
        })
      }

      return result
    } catch (error) {
      console.error('Erreur lors du calcul de la charge chronique:', error)
      return []
    }
  }

  /**
   * Obtient les statistiques de charge chronique
   */
  async getChronicLoadStats(): Promise<{
    currentChronicLoad: number
    currentAcuteLoad: number
    currentTSB: number
    trend: 'up' | 'down' | 'stable'
  }> {
    const endDate = new Date().toISOString().split('T')[0]
    const startDate = new Date()
    startDate.setDate(startDate.getDate() - 35) // 35 jours pour avoir des données historiques
    
    const data = await this.getChronicLoadData(startDate.toISOString().split('T')[0], endDate)
    
    if (data.length === 0) {
      return {
        currentChronicLoad: 0,
        currentAcuteLoad: 0,
        currentTSB: 0,
        trend: 'stable'
      }
    }

    const latest = data[data.length - 1]
    const previous = data.length > 1 ? data[data.length - 2] : latest
    
    let trend: 'up' | 'down' | 'stable' = 'stable'
    if (latest.chronicLoad > previous.chronicLoad + 1) trend = 'up'
    else if (latest.chronicLoad < previous.chronicLoad - 1) trend = 'down'

    return {
      currentChronicLoad: latest.chronicLoad,
      currentAcuteLoad: latest.acuteLoad,
      currentTSB: latest.trainingStressBalance,
      trend
    }
  }
}

export const chronicLoadService = new ChronicLoadService()
