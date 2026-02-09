import { vi, describe, test, expect, beforeEach } from 'vitest'

// Mock dataService utilise par chronicLoadService
vi.mock('../services/dataService', () => ({
  dataService: {
    getTrainingLoad: vi.fn(),
  },
}))

import { dataService } from '../services/dataService'
import { chronicLoadService } from '../services/chronicLoadService'

// Helper pour creer une entree TrainingLoad mock
function makeTrainingLoadEntry(overrides: Record<string, any> = {}) {
  return {
    id: '1',
    user_id: 'user-1',
    date: '2024-06-15',
    ctl_42d: 50,
    atl_7d: 60,
    tsb: -10,
    rhr_delta_7d: 2.5,
    created_at: '2024-06-15T00:00:00Z',
    updated_at: '2024-06-15T00:00:00Z',
    ...overrides,
  }
}

describe('ChronicLoadService', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('getChronicLoadData', () => {
    test('mappe ctl_42d vers chronicLoad, atl_7d vers acuteLoad, tsb vers trainingStressBalance', async () => {
      vi.mocked(dataService.getTrainingLoad).mockResolvedValue([
        makeTrainingLoadEntry({ date: '2024-06-15', ctl_42d: 45.2, atl_7d: 62.1, tsb: -16.9 }),
      ])

      const result = await chronicLoadService.getChronicLoadData('2024-06-15', '2024-06-15')

      expect(result).toHaveLength(1)
      expect(result[0].date).toBe('2024-06-15')
      expect(result[0].chronicLoad).toBe(45.2)
      expect(result[0].acuteLoad).toBe(62.1)
      expect(result[0].trainingStressBalance).toBe(-16.9)
    })

    test('retourne un tableau vide quand pas de donnees', async () => {
      vi.mocked(dataService.getTrainingLoad).mockResolvedValue([])

      const result = await chronicLoadService.getChronicLoadData('2024-06-15', '2024-06-15')

      expect(result).toEqual([])
    })

    test('gere les valeurs null en les remplacant par 0', async () => {
      vi.mocked(dataService.getTrainingLoad).mockResolvedValue([
        makeTrainingLoadEntry({ ctl_42d: null, atl_7d: null, tsb: null }),
      ])

      const result = await chronicLoadService.getChronicLoadData('2024-06-15', '2024-06-15')

      expect(result[0].chronicLoad).toBe(0)
      expect(result[0].acuteLoad).toBe(0)
      expect(result[0].trainingStressBalance).toBe(0)
    })

    test('retourne un tableau vide en cas d erreur', async () => {
      vi.mocked(dataService.getTrainingLoad).mockRejectedValue(new Error('Network error'))

      const result = await chronicLoadService.getChronicLoadData('2024-06-01', '2024-06-30')

      expect(result).toEqual([])
    })
  })

  describe('getChronicLoadDataWithRhr', () => {
    test('retourne les donnees et le rhr_delta_7d du dernier jour', async () => {
      vi.mocked(dataService.getTrainingLoad).mockResolvedValue([
        makeTrainingLoadEntry({ date: '2024-06-14', rhr_delta_7d: 1.0 }),
        makeTrainingLoadEntry({ date: '2024-06-15', rhr_delta_7d: 3.5 }),
      ])

      const result = await chronicLoadService.getChronicLoadDataWithRhr('2024-06-14', '2024-06-15')

      expect(result.data).toHaveLength(2)
      expect(result.lastRhrDelta7d).toBe(3.5)
    })

    test('retourne undefined pour rhr quand le dernier jour a null', async () => {
      vi.mocked(dataService.getTrainingLoad).mockResolvedValue([
        makeTrainingLoadEntry({ rhr_delta_7d: null }),
      ])

      const result = await chronicLoadService.getChronicLoadDataWithRhr('2024-06-15', '2024-06-15')

      expect(result.lastRhrDelta7d).toBeUndefined()
    })

    test('retourne un resultat vide quand pas de donnees', async () => {
      vi.mocked(dataService.getTrainingLoad).mockResolvedValue([])

      const result = await chronicLoadService.getChronicLoadDataWithRhr('2024-06-15', '2024-06-15')

      expect(result.data).toEqual([])
      expect(result.lastRhrDelta7d).toBeUndefined()
    })
  })

  describe('getChronicLoadStats', () => {
    test('retourne les stats avec trend stable quand pas de donnees', async () => {
      vi.mocked(dataService.getTrainingLoad).mockResolvedValue([])

      const stats = await chronicLoadService.getChronicLoadStats()

      expect(stats.currentChronicLoad).toBe(0)
      expect(stats.currentAcuteLoad).toBe(0)
      expect(stats.currentTSB).toBe(0)
      expect(stats.trend).toBe('stable')
    })

    test('detecte trend up quand la charge augmente', async () => {
      vi.mocked(dataService.getTrainingLoad).mockResolvedValue([
        makeTrainingLoadEntry({ date: '2024-06-14', ctl_42d: 40, atl_7d: 50, tsb: -10 }),
        makeTrainingLoadEntry({ date: '2024-06-15', ctl_42d: 45, atl_7d: 55, tsb: -10 }),
      ])

      const stats = await chronicLoadService.getChronicLoadStats()

      expect(stats.currentChronicLoad).toBe(45)
      expect(stats.trend).toBe('up')
    })

    test('detecte trend down quand la charge diminue', async () => {
      vi.mocked(dataService.getTrainingLoad).mockResolvedValue([
        makeTrainingLoadEntry({ date: '2024-06-14', ctl_42d: 50, atl_7d: 55, tsb: -5 }),
        makeTrainingLoadEntry({ date: '2024-06-15', ctl_42d: 40, atl_7d: 45, tsb: -5 }),
      ])

      const stats = await chronicLoadService.getChronicLoadStats()

      expect(stats.currentChronicLoad).toBe(40)
      expect(stats.trend).toBe('down')
    })
  })
})
