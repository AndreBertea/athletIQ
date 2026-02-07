import { vi, describe, test, expect, beforeEach } from 'vitest'

// Mock activityService utilise par chronicLoadService
vi.mock('../services/activityService', () => ({
  activityService: {
    getAllActivities: vi.fn(),
  },
}))

import { activityService } from '../services/activityService'
import { chronicLoadService } from '../services/chronicLoadService'

// Helper pour creer une activite mock
function makeActivity(overrides: Record<string, any> = {}) {
  return {
    id: '1',
    activity_type: 'Run',
    start_date: '2024-06-15T08:00:00Z',
    moving_time: 3600, // 1 heure
    distance: 10000,
    average_heart_rate: 150,
    max_heart_rate: 190,
    average_pace: 0.006, // 6 min/km
    ...overrides,
  }
}

describe('ChronicLoadService', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('calculateTRIMP (via getChronicLoadData)', () => {
    test('calcule le TRIMP avec HR quand disponible', async () => {
      const activity = makeActivity({
        start_date: '2024-06-15T08:00:00Z',
        moving_time: 3600,
        average_heart_rate: 150,
        max_heart_rate: 190,
      })
      vi.mocked(activityService.getAllActivities).mockResolvedValue([activity])

      const result = await chronicLoadService.getChronicLoadData('2024-06-15', '2024-06-15')

      expect(result).toHaveLength(1)
      // Le TRIMP devrait etre > 0 pour une activite avec HR
      expect(result[0].acuteLoad).toBeGreaterThan(0)
    })

    test('utilise le fallback distance quand pas de HR', async () => {
      const activity = makeActivity({
        start_date: '2024-06-15T08:00:00Z',
        moving_time: 3600,
        average_heart_rate: undefined,
        max_heart_rate: undefined,
        distance: 10000,
        average_pace: 0.006, // ~6 min/km
      })
      vi.mocked(activityService.getAllActivities).mockResolvedValue([activity])

      const result = await chronicLoadService.getChronicLoadData('2024-06-15', '2024-06-15')

      expect(result).toHaveLength(1)
      expect(result[0].acuteLoad).toBeGreaterThan(0)
    })
  })

  describe('filtrage des activites', () => {
    test('ne prend que les activites de course (Run, TrailRun, VirtualRun)', async () => {
      const activities = [
        makeActivity({ id: '1', activity_type: 'Run', start_date: '2024-06-15T08:00:00Z' }),
        makeActivity({ id: '2', activity_type: 'Ride', start_date: '2024-06-15T10:00:00Z' }),
        makeActivity({ id: '3', activity_type: 'TrailRun', start_date: '2024-06-15T12:00:00Z' }),
        makeActivity({ id: '4', activity_type: 'Swim', start_date: '2024-06-15T14:00:00Z' }),
        makeActivity({ id: '5', activity_type: 'VirtualRun', start_date: '2024-06-15T16:00:00Z' }),
      ]
      vi.mocked(activityService.getAllActivities).mockResolvedValue(activities)

      const result = await chronicLoadService.getChronicLoadData('2024-06-15', '2024-06-15')

      // Devrait utiliser 3 activites (Run, TrailRun, VirtualRun) et ignorer Ride/Swim
      expect(result).toHaveLength(1)
      expect(result[0].acuteLoad).toBeGreaterThan(0)
    })

    test('retourne un tableau vide si aucune activite de course', async () => {
      vi.mocked(activityService.getAllActivities).mockResolvedValue([
        makeActivity({ activity_type: 'Ride' }),
        makeActivity({ activity_type: 'Swim' }),
      ])

      const result = await chronicLoadService.getChronicLoadData('2024-06-15', '2024-06-15')

      expect(result).toEqual([])
    })
  })

  describe('charge chronique et aigue', () => {
    test('la charge chronique est la moyenne TRIMP sur 28 jours', async () => {
      // Creer une activite par jour pendant 28 jours
      const activities = Array.from({ length: 28 }, (_, i) => {
        const date = new Date('2024-06-01')
        date.setDate(date.getDate() + i)
        return makeActivity({
          id: String(i),
          start_date: date.toISOString(),
          moving_time: 3600,
          average_heart_rate: 150,
          max_heart_rate: 190,
        })
      })
      vi.mocked(activityService.getAllActivities).mockResolvedValue(activities)

      const result = await chronicLoadService.getChronicLoadData('2024-06-28', '2024-06-28')

      expect(result).toHaveLength(1)
      expect(result[0].chronicLoad).toBeGreaterThan(0)
    })

    test('la charge aigue est la moyenne TRIMP sur 7 jours', async () => {
      // Une seule activite il y a 3 jours
      const activities = [
        makeActivity({
          start_date: '2024-06-25T08:00:00Z',
          moving_time: 3600,
          average_heart_rate: 160,
          max_heart_rate: 190,
        }),
      ]
      vi.mocked(activityService.getAllActivities).mockResolvedValue(activities)

      const result = await chronicLoadService.getChronicLoadData('2024-06-28', '2024-06-28')

      expect(result).toHaveLength(1)
      // Charge aigue devrait etre > charge chronique (1 activite sur 7j vs 28j)
      expect(result[0].acuteLoad).toBeGreaterThan(result[0].chronicLoad)
    })

    test('TSB = acuteLoad - chronicLoad', async () => {
      const activities = [
        makeActivity({ start_date: '2024-06-27T08:00:00Z' }),
      ]
      vi.mocked(activityService.getAllActivities).mockResolvedValue(activities)

      const result = await chronicLoadService.getChronicLoadData('2024-06-28', '2024-06-28')

      expect(result).toHaveLength(1)
      const expected = result[0].acuteLoad - result[0].chronicLoad
      expect(result[0].trainingStressBalance).toBeCloseTo(expected)
    })
  })

  describe('periode de donnees', () => {
    test('genere une entree par jour dans la periode demandee', async () => {
      vi.mocked(activityService.getAllActivities).mockResolvedValue([
        makeActivity({ start_date: '2024-06-10T08:00:00Z' }),
      ])

      const result = await chronicLoadService.getChronicLoadData('2024-06-10', '2024-06-14')

      expect(result).toHaveLength(5)
      expect(result[0].date).toBe('2024-06-10')
      expect(result[4].date).toBe('2024-06-14')
    })

    test('charge 28j de marge avant la date de debut pour le calcul chronique', async () => {
      vi.mocked(activityService.getAllActivities).mockResolvedValue([])

      await chronicLoadService.getChronicLoadData('2024-07-01', '2024-07-01')

      const callArgs = vi.mocked(activityService.getAllActivities).mock.calls[0]
      // Le dateFrom devrait etre 28 jours avant 2024-07-01 = 2024-06-03
      expect(callArgs[1]).toBe('2024-06-03')
    })
  })

  describe('gestion des erreurs', () => {
    test('retourne un tableau vide en cas d erreur', async () => {
      vi.mocked(activityService.getAllActivities).mockRejectedValue(new Error('Network error'))

      const result = await chronicLoadService.getChronicLoadData('2024-06-01', '2024-06-30')

      expect(result).toEqual([])
    })
  })

  describe('getChronicLoadStats', () => {
    test('retourne les stats avec trend stable quand pas de donnees', async () => {
      vi.mocked(activityService.getAllActivities).mockResolvedValue([])

      const stats = await chronicLoadService.getChronicLoadStats()

      expect(stats.currentChronicLoad).toBe(0)
      expect(stats.currentAcuteLoad).toBe(0)
      expect(stats.currentTSB).toBe(0)
      expect(stats.trend).toBe('stable')
    })
  })

  describe('estimateTRIMPFromDistance (intensite par rythme)', () => {
    test('rythme rapide (<4 min/km) donne une intensite elevee', async () => {
      // average_pace en s/m : paceMinPerKm = pace * 1000 / 60
      // 3.5 min/km = 210 s/km = 0.21 s/m
      const fastActivity = makeActivity({
        start_date: '2024-06-15T08:00:00Z',
        average_heart_rate: undefined,
        max_heart_rate: undefined,
        average_pace: 0.21, // 3.5 min/km → intensite 0.9
        moving_time: 3600,
      })
      // 8 min/km = 480 s/km = 0.48 s/m
      const slowActivity = makeActivity({
        id: '2',
        start_date: '2024-06-16T08:00:00Z',
        average_heart_rate: undefined,
        max_heart_rate: undefined,
        average_pace: 0.48, // 8 min/km → intensite 0.5
        moving_time: 3600,
      })

      vi.mocked(activityService.getAllActivities).mockResolvedValue([fastActivity])
      const fastResult = await chronicLoadService.getChronicLoadData('2024-06-15', '2024-06-15')

      vi.mocked(activityService.getAllActivities).mockResolvedValue([slowActivity])
      const slowResult = await chronicLoadService.getChronicLoadData('2024-06-16', '2024-06-16')

      // L'activite rapide devrait donner une charge aigue plus elevee
      expect(fastResult[0].acuteLoad).toBeGreaterThan(slowResult[0].acuteLoad)
    })
  })
})
