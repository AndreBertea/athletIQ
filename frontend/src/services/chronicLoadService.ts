import { dataService } from './dataService'
import type { TrainingLoadEntry } from './dataService'

interface ChronicLoadData {
  date: string
  chronicLoad: number
  acuteLoad: number
  trainingStressBalance: number
}

interface ChronicLoadResult {
  data: ChronicLoadData[]
  lastRhrDelta7d: number | undefined
}

class ChronicLoadService {
  /**
   * Obtient les données de charge chronique pour une période donnée
   * via l'API backend (EWMA 42j CTL, 7j ATL)
   */
  async getChronicLoadData(startDate: string, endDate: string): Promise<ChronicLoadData[]> {
    const result = await this.getChronicLoadDataWithRhr(startDate, endDate)
    return result.data
  }

  /**
   * Obtient les données de charge chronique + rhr_delta_7d du dernier jour
   */
  async getChronicLoadDataWithRhr(startDate: string, endDate: string): Promise<ChronicLoadResult> {
    try {
      const entries = await dataService.getTrainingLoad(startDate, endDate)

      if (entries.length === 0) {
        return { data: [], lastRhrDelta7d: undefined }
      }

      const data: ChronicLoadData[] = entries.map((entry: TrainingLoadEntry) => ({
        date: entry.date,
        chronicLoad: entry.ctl_42d ?? 0,
        acuteLoad: entry.atl_7d ?? 0,
        trainingStressBalance: entry.tsb ?? 0,
      }))

      const lastEntry = entries[entries.length - 1]
      const lastRhrDelta7d = lastEntry.rhr_delta_7d ?? undefined

      return { data, lastRhrDelta7d }
    } catch (error) {
      console.error('Erreur lors de la récupération de la charge chronique:', error)
      return { data: [], lastRhrDelta7d: undefined }
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
    startDate.setDate(startDate.getDate() - 49) // 49 jours pour avoir l'historique EWMA 42j

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
