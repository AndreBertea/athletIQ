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
        <span className="ml-2 text-sm text-gray-500 dark:text-gray-400">Chargement des segments...</span>
      </div>
    )
  }

  if (error) {
    const is404 = (error as any)?.response?.status === 404
    if (is404) {
      return (
        <div className="text-center py-8">
          <AlertCircle className="h-8 w-8 text-gray-400 mx-auto mb-3" />
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">Analyse par segment non disponible pour cette activité.</p>
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
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">Aucun segment trouvé pour cette activité.</p>
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
        <div className="bg-blue-50 dark:bg-blue-900/20 p-3 rounded-lg text-center">
          <div className="text-xs text-blue-600 dark:text-blue-400">Segments</div>
          <div className="text-sm font-bold text-blue-800 dark:text-blue-200">{data.segment_count}</div>
        </div>
        <div className="bg-green-50 dark:bg-green-900/20 p-3 rounded-lg text-center">
          <div className="text-xs text-green-600 dark:text-green-400">Distance totale</div>
          <div className="text-sm font-bold text-green-800 dark:text-green-200">{(totalDistance / 1000).toFixed(2)} km</div>
        </div>
        {cardiacDrift !== null && cardiacDrift !== undefined && (
          <div className="bg-red-50 dark:bg-red-900/20 p-3 rounded-lg text-center">
            <div className="text-xs text-red-600 dark:text-red-400">Cardiac Drift</div>
            <div className="text-sm font-bold text-red-800 dark:text-red-200">{(cardiacDrift * 100).toFixed(1)}%</div>
          </div>
        )}
        {cadenceDecay !== null && cadenceDecay !== undefined && (
          <div className="bg-purple-50 dark:bg-purple-900/20 p-3 rounded-lg text-center">
            <div className="text-xs text-purple-600 dark:text-purple-400">Cadence Decay</div>
            <div className="text-sm font-bold text-purple-800 dark:text-purple-200">{(cadenceDecay * 100).toFixed(1)}%</div>
          </div>
        )}
      </div>

      {/* Tableau des segments */}
      <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              {['#', 'Dist.', 'Temps', 'Allure', 'Pente', 'D+', 'D-', 'Alt.', 'FC', 'Cadence', 'EF'].map(h => (
                <th key={h} className="px-2 py-2 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
            {data.segments.map((s, i) => (
              <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                <td className="px-2 py-1.5 text-xs text-gray-700 dark:text-gray-300 font-medium whitespace-nowrap">{i + 1}</td>
                <td className="px-2 py-1.5 text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">{(s.segment.distance_m / 1000).toFixed(2)} km</td>
                <td className="px-2 py-1.5 text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">{Math.floor(s.segment.elapsed_time_s / 60)}:{String(Math.round(s.segment.elapsed_time_s % 60)).padStart(2, '0')}</td>
                <td className="px-2 py-1.5 text-xs text-gray-700 dark:text-gray-300 font-medium whitespace-nowrap">{s.segment.pace_min_per_km != null ? `${Math.floor(s.segment.pace_min_per_km)}:${String(Math.round((s.segment.pace_min_per_km % 1) * 60)).padStart(2, '0')}` : '—'}</td>
                <td className="px-2 py-1.5 text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">{s.segment.avg_grade_percent != null ? `${s.segment.avg_grade_percent.toFixed(1)}%` : '—'}</td>
                <td className="px-2 py-1.5 text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">{s.segment.elevation_gain_m != null ? `${s.segment.elevation_gain_m.toFixed(0)}m` : '—'}</td>
                <td className="px-2 py-1.5 text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">{s.segment.elevation_loss_m != null ? `${s.segment.elevation_loss_m.toFixed(0)}m` : '—'}</td>
                <td className="px-2 py-1.5 text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">{s.segment.altitude_m != null ? `${Math.round(s.segment.altitude_m)}m` : '—'}</td>
                <td className="px-2 py-1.5 text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">{s.segment.avg_hr != null ? Math.round(s.segment.avg_hr) : '—'}</td>
                <td className="px-2 py-1.5 text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">{s.segment.avg_cadence != null ? Math.round(s.segment.avg_cadence * 2) : '—'}</td>
                <td className="px-2 py-1.5 text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">{s.features?.efficiency_factor != null ? s.features.efficiency_factor.toFixed(4) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Graphiques */}
      <SegmentCharts segments={data.segments} />
    </div>
  )
}
