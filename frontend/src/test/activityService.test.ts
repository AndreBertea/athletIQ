import { vi, describe, test, expect, beforeEach } from 'vitest'

vi.mock('axios', async () => {
  const mockInterceptors = {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  }
  const mockAxiosInstance = {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    interceptors: mockInterceptors,
  }
  return {
    default: {
      create: vi.fn(() => mockAxiosInstance),
    },
  }
})

import axios from 'axios'

describe('ActivityService', () => {
  let activityService: any
  let mockApi: any

  beforeEach(async () => {
    vi.clearAllMocks()
    vi.resetModules()

    const axiosModule = await import('axios')
    mockApi = axiosModule.default.create()

    const module = await import('../services/activityService')
    activityService = module.activityService
  })

  describe('getActivities', () => {
    test('retourne les activites paginées', async () => {
      const mockData = {
        items: [{ id: '1', name: 'Run', activity_type: 'Run', start_date: '2024-01-01', distance: 10000, moving_time: 3600 }],
        total: 1, page: 1, per_page: 30, pages: 1,
      }
      mockApi.get.mockResolvedValue({ data: mockData })

      const result = await activityService.getActivities({ page: 1, per_page: 30 })

      expect(mockApi.get).toHaveBeenCalledWith('/activities', { params: { page: 1, per_page: 30 } })
      expect(result).toEqual(mockData)
    })

    test('fonctionne sans parametres', async () => {
      mockApi.get.mockResolvedValue({ data: { items: [], total: 0, page: 1, per_page: 30, pages: 0 } })

      await activityService.getActivities()

      expect(mockApi.get).toHaveBeenCalledWith('/activities', { params: {} })
    })
  })

  describe('getAllActivities', () => {
    test('recupere toutes les pages', async () => {
      const page1 = { items: [{ id: '1', name: 'Run 1' }], total: 3, page: 1, per_page: 200, pages: 2 }
      const page2 = { items: [{ id: '2', name: 'Run 2' }, { id: '3', name: 'Run 3' }], total: 3, page: 2, per_page: 200, pages: 2 }

      mockApi.get.mockResolvedValueOnce({ data: page1 }).mockResolvedValueOnce({ data: page2 })

      const result = await activityService.getAllActivities()

      expect(mockApi.get).toHaveBeenCalledTimes(2)
      expect(result).toHaveLength(3)
      expect(result[0].id).toBe('1')
      expect(result[2].id).toBe('3')
    })

    test('passe le filtre activity_type', async () => {
      mockApi.get.mockResolvedValue({ data: { items: [], total: 0, page: 1, per_page: 200, pages: 1 } })

      await activityService.getAllActivities('Run')

      expect(mockApi.get).toHaveBeenCalledWith('/activities', {
        params: expect.objectContaining({ activity_type: 'Run' }),
      })
    })

    test('passe le filtre dateFrom', async () => {
      mockApi.get.mockResolvedValue({ data: { items: [], total: 0, page: 1, per_page: 200, pages: 1 } })

      await activityService.getAllActivities(undefined, '2024-01-01')

      expect(mockApi.get).toHaveBeenCalledWith('/activities', {
        params: expect.objectContaining({ date_from: '2024-01-01' }),
      })
    })
  })

  describe('getActivity', () => {
    test('retourne une activite par id', async () => {
      const mockActivity = { id: '42', name: 'Run', activity_type: 'Run' }
      mockApi.get.mockResolvedValue({ data: mockActivity })

      const result = await activityService.getActivity('42')

      expect(mockApi.get).toHaveBeenCalledWith('/activities/42')
      expect(result).toEqual(mockActivity)
    })
  })

  describe('getActivityStats', () => {
    test('passe period_days en parametre', async () => {
      mockApi.get.mockResolvedValue({ data: {} })

      await activityService.getActivityStats(90)

      expect(mockApi.get).toHaveBeenCalledWith('/activities/stats', { params: { period_days: 90 } })
    })

    test('utilise 30 jours par defaut', async () => {
      mockApi.get.mockResolvedValue({ data: {} })

      await activityService.getActivityStats()

      expect(mockApi.get).toHaveBeenCalledWith('/activities/stats', { params: { period_days: 30 } })
    })
  })

  describe('syncStravaActivities', () => {
    test('envoie un POST avec days_back', async () => {
      const mockResult = { message: 'ok', total_activities_fetched: 10, new_activities_saved: 5, athlete_id: 123, period: '30 days' }
      mockApi.post.mockResolvedValue({ data: mockResult })

      const result = await activityService.syncStravaActivities(60)

      expect(mockApi.post).toHaveBeenCalledWith('/sync/strava', null, { params: { days_back: 60 } })
      expect(result).toEqual(mockResult)
    })
  })

  describe('enrichissement', () => {
    test('getStravaQuotaStatus', async () => {
      const mockQuota = { daily_used: 10, daily_limit: 1000 }
      mockApi.get.mockResolvedValue({ data: mockQuota })

      const result = await activityService.getStravaQuotaStatus()

      expect(mockApi.get).toHaveBeenCalledWith('/strava/quota')
      expect(result).toEqual(mockQuota)
    })

    test('enrichSingleActivity', async () => {
      mockApi.post.mockResolvedValue({ data: { message: 'enriched' } })

      await activityService.enrichSingleActivity('abc-123')

      expect(mockApi.post).toHaveBeenCalledWith('/activities/abc-123/enrich')
    })

    test('enrichBatchActivities', async () => {
      mockApi.post.mockResolvedValue({ data: { message: 'batch done' } })

      await activityService.enrichBatchActivities(5)

      expect(mockApi.post).toHaveBeenCalledWith('/activities/enrich-batch', null, { params: { max_activities: 5 } })
    })

    test('getActivityStreams', async () => {
      const mockStreams = { activity_id: 'x', streams_data: {}, laps_data: [] }
      mockApi.get.mockResolvedValue({ data: mockStreams })

      const result = await activityService.getActivityStreams('x')

      expect(mockApi.get).toHaveBeenCalledWith('/activities/x/streams')
      expect(result).toEqual(mockStreams)
    })

    test('prioritizeActivity', async () => {
      mockApi.post.mockResolvedValue({ data: { message: 'prioritized', activity_id: 'abc' } })

      const result = await activityService.prioritizeActivity('abc')

      expect(mockApi.post).toHaveBeenCalledWith('/activities/abc/prioritize')
      expect(result.activity_id).toBe('abc')
    })
  })

  describe('donnees enrichies', () => {
    test('getEnrichedActivities', async () => {
      const mockData = { items: [], total: 0, page: 1, per_page: 30, pages: 0 }
      mockApi.get.mockResolvedValue({ data: mockData })

      await activityService.getEnrichedActivities({ page: 2 })

      expect(mockApi.get).toHaveBeenCalledWith('/activities/enriched', { params: { page: 2 } })
    })

    test('getAllEnrichedActivities pagine correctement', async () => {
      const page1 = { items: [{ activity_id: 1 }], total: 2, page: 1, per_page: 200, pages: 2 }
      const page2 = { items: [{ activity_id: 2 }], total: 2, page: 2, per_page: 200, pages: 2 }

      mockApi.get.mockResolvedValueOnce({ data: page1 }).mockResolvedValueOnce({ data: page2 })

      const result = await activityService.getAllEnrichedActivities()

      expect(result).toHaveLength(2)
    })

    test('getAllEnrichedActivities passe sportType et dateFrom', async () => {
      mockApi.get.mockResolvedValue({ data: { items: [], total: 0, page: 1, per_page: 200, pages: 1 } })

      await activityService.getAllEnrichedActivities('Run', '2024-06-01')

      expect(mockApi.get).toHaveBeenCalledWith('/activities/enriched', {
        params: expect.objectContaining({ sport_type: 'Run', date_from: '2024-06-01' }),
      })
    })

    test('getEnrichedActivityStreams', async () => {
      const mockStreams = { activity_id: 42, streams: { heartrate: [120, 130] } }
      mockApi.get.mockResolvedValue({ data: mockStreams })

      const result = await activityService.getEnrichedActivityStreams(42)

      expect(mockApi.get).toHaveBeenCalledWith('/activities/enriched/42/streams')
      expect(result.streams.heartrate).toEqual([120, 130])
    })
  })
})
