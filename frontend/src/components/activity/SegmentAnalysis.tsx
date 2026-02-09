import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { BarChart3, Loader2, AlertCircle } from 'lucide-react'
import { segmentService } from '../../services/segmentService'
import SegmentCharts from './SegmentCharts'

interface SegmentAnalysisProps {
  activityId: string | number
}

export default function SegmentAnalysis({ activityId }: SegmentAnalysisProps) {
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['segments', activityId],
    queryFn: () => segmentService.getSegments(String(activityId)),
    staleTime: 10 * 60 * 1000,
    enabled: !!activityId,
  })

  const processMutation = useMutation({
    mutationFn: () => segmentService.processSegments(String(activityId)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['segments', activityId] })
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <Loader2 className="h-6 w-6 animate-spin text-primary-500" />
        <span className="ml-2 text-sm text-gray-500">Chargement des segments...</span>
      </div>
    )
  }

  if (error) {
    const is404 = (error as any)?.response?.status === 404
    if (is404) {
      return (
        <div className="text-center py-8">
          <AlertCircle className="h-8 w-8 text-gray-400 mx-auto mb-3" />
          <p className="text-sm text-gray-600 mb-4">Analyse par segment non disponible pour cette activité.</p>
          <button
            onClick={() => processMutation.mutate()}
            disabled={processMutation.isPending}
            className="inline-flex items-center px-4 py-2 bg-primary-600 text-white text-sm rounded-md hover:bg-primary-700 transition-colors disabled:opacity-50"
          >
            {processMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Segmentation en cours...
              </>
            ) : (
              <>
                <BarChart3 className="h-4 w-4 mr-2" />
                Lancer la segmentation
              </>
            )}
          </button>
          {processMutation.isError && (
            <p className="mt-2 text-xs text-red-500">Erreur lors de la segmentation. Réessayez plus tard.</p>
          )}
        </div>
      )
    }

    return (
      <div className="text-center py-8">
        <AlertCircle className="h-8 w-8 text-red-400 mx-auto mb-3" />
        <p className="text-sm text-red-600">Erreur lors du chargement des segments.</p>
      </div>
    )
  }

  if (!data || data.segment_count === 0) {
    return (
      <div className="text-center py-8">
        <AlertCircle className="h-8 w-8 text-gray-400 mx-auto mb-3" />
        <p className="text-sm text-gray-600 mb-4">Aucun segment trouvé pour cette activité.</p>
        <button
          onClick={() => processMutation.mutate()}
          disabled={processMutation.isPending}
          className="inline-flex items-center px-4 py-2 bg-primary-600 text-white text-sm rounded-md hover:bg-primary-700 transition-colors disabled:opacity-50"
        >
          {processMutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Segmentation en cours...
            </>
          ) : (
            <>
              <BarChart3 className="h-4 w-4 mr-2" />
              Lancer la segmentation
            </>
          )}
        </button>
      </div>
    )
  }

  // Résumé des segments
  const totalDistance = data.segments.reduce((acc, s) => acc + s.segment.distance_m, 0)
  const lastFeatures = data.segments[data.segments.length - 1]?.features
  const cardiacDrift = lastFeatures?.cardiac_drift
  const cadenceDecay = lastFeatures?.cadence_decay

  return (
    <div className="space-y-4">
      {/* Résumé */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-blue-50 p-3 rounded-lg text-center">
          <div className="text-xs text-blue-600">Segments</div>
          <div className="text-sm font-bold text-blue-800">{data.segment_count}</div>
        </div>
        <div className="bg-green-50 p-3 rounded-lg text-center">
          <div className="text-xs text-green-600">Distance totale</div>
          <div className="text-sm font-bold text-green-800">{(totalDistance / 1000).toFixed(2)} km</div>
        </div>
        {cardiacDrift !== null && cardiacDrift !== undefined && (
          <div className="bg-red-50 p-3 rounded-lg text-center">
            <div className="text-xs text-red-600">Cardiac Drift</div>
            <div className="text-sm font-bold text-red-800">{(cardiacDrift * 100).toFixed(1)}%</div>
          </div>
        )}
        {cadenceDecay !== null && cadenceDecay !== undefined && (
          <div className="bg-purple-50 p-3 rounded-lg text-center">
            <div className="text-xs text-purple-600">Cadence Decay</div>
            <div className="text-sm font-bold text-purple-800">{(cadenceDecay * 100).toFixed(1)}%</div>
          </div>
        )}
      </div>

      {/* Graphiques */}
      <SegmentCharts segments={data.segments} />
    </div>
  )
}
