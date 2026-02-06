import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Database, Clock, AlertCircle, CheckCircle, Play } from 'lucide-react'
import { activityService } from '../services/activityService'

export default function DetailedData() {
  const [isEnriching, setIsEnriching] = useState(false)
  const [batchSize, setBatchSize] = useState(10)
  const queryClient = useQueryClient()

  // Query pour le statut d'enrichissement
  const { data: enrichmentStatus, isLoading: statusLoading, refetch: refetchStatus } = useQuery({
    queryKey: ['enrichment-status'],
    queryFn: () => activityService.getEnrichmentStatus(),
    staleTime: 30000 // Plus de rafraîchissement automatique
  })

  // Query pour le statut des quotas
  const { data: quotaStatus, refetch: refetchQuota } = useQuery({
    queryKey: ['strava-quota'],
    queryFn: () => activityService.getStravaQuotaStatus(),
    staleTime: 60000 // Plus de rafraîchissement automatique
  })

  // Mutation pour l'enrichissement par lot
  const enrichMutation = useMutation({
    mutationFn: (maxActivities: number) => activityService.enrichBatchActivities(maxActivities),
    onMutate: () => {
      setIsEnriching(true)
    },
    onSuccess: (data) => {
      // Rafraîchir les données
      refetchStatus()
      refetchQuota()
      queryClient.invalidateQueries({ queryKey: ['activities'] })
      
      // Message de succès
      alert(`✅ ${data.message}`)
    },
    onError: (error: any) => {
      alert(`❌ Erreur: ${error.response?.data?.detail || 'Échec de l\'enrichissement'}`)
    },
    onSettled: () => {
      setIsEnriching(false)
    }
  })

  const handleEnrichBatch = () => {
    if (!enrichmentStatus?.can_enrich_more) {
      alert('⚠️ Quota atteint ou aucune activité à enrichir')
      return
    }
    
    const confirmed = confirm(
      `Êtes-vous sûr de vouloir enrichir ${Math.min(batchSize, enrichmentStatus.pending_activities)} activités?\n\n` +
      `Cela utilisera ${Math.min(batchSize, enrichmentStatus.pending_activities) * 3} requêtes API Strava (streams + laps + segments).`
    )
    
    if (confirmed) {
      enrichMutation.mutate(batchSize)
    }
  }

  const formatDateTime = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('fr-FR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const getQuotaColor = (used: number, limit: number) => {
    const percentage = (used / limit) * 100
    if (percentage >= 90) return 'text-red-600 bg-red-50'
    if (percentage >= 70) return 'text-orange-600 bg-orange-50'
    return 'text-green-600 bg-green-50'
  }

  if (statusLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500"></div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Données Détaillées</h1>
          <p className="mt-2 text-gray-600">
            Gérez l'enrichissement de vos activités avec les données complètes Strava
          </p>
        </div>
      </div>

      {/* Statut d'enrichissement */}
      <div className="card">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-medium text-gray-900 flex items-center">
            <Database className="h-5 w-5 mr-2" />
            Statut d'enrichissement
          </h3>
        </div>

        {enrichmentStatus && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-600">
                {enrichmentStatus.total_activities}
              </div>
              <div className="text-sm text-gray-500">Total activités</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">
                {enrichmentStatus.strava_activities}
              </div>
              <div className="text-sm text-gray-500">Activités Strava</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-purple-600">
                {enrichmentStatus.enriched_activities}
              </div>
              <div className="text-sm text-gray-500">Enrichies</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-orange-600">
                {enrichmentStatus.pending_activities}
              </div>
              <div className="text-sm text-gray-500">En attente</div>
            </div>
          </div>
        )}

        {/* Barre de progression */}
        {enrichmentStatus && enrichmentStatus.strava_activities > 0 && (
          <div className="mb-6">
            <div className="flex justify-between text-sm text-gray-600 mb-2">
              <span>Progression de l'enrichissement</span>
              <span>{enrichmentStatus.enrichment_percentage}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div 
                className="bg-primary-600 h-2 rounded-full transition-all duration-300" 
                style={{ width: `${enrichmentStatus.enrichment_percentage}%` }}
              ></div>
            </div>
          </div>
        )}

        {/* Actions d'enrichissement */}
        <div className="border-t pt-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h4 className="font-medium text-gray-900">Enrichissement par lot</h4>
              <p className="text-sm text-gray-500">
                Enrichit vos activités avec les données détaillées (GPS, fréquence cardiaque, segments, etc.)
              </p>
            </div>
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <label className="text-sm font-medium text-gray-700">Taille du lot :</label>
                <select 
                  value={batchSize} 
                  onChange={(e) => setBatchSize(Number(e.target.value))}
                  className="text-sm border border-gray-300 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary-500"
                  disabled={isEnriching}
                >
                  <option value={5}>5 activités</option>
                  <option value={10}>10 activités</option>
                  <option value={15}>15 activités</option>
                  <option value={20}>20 activités</option>
                </select>
              </div>
              <button
                onClick={handleEnrichBatch}
                disabled={isEnriching || !enrichmentStatus?.can_enrich_more}
                className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  isEnriching || !enrichmentStatus?.can_enrich_more
                    ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                    : 'bg-primary-600 text-white hover:bg-primary-700'
                }`}
              >
                {isEnriching ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    Enrichissement...
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4 mr-2" />
                    Enrichir {Math.min(batchSize, enrichmentStatus?.pending_activities || 0)} activités
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Alerte si pas d'activités à enrichir */}
          {enrichmentStatus && enrichmentStatus.pending_activities === 0 && (
            <div className="flex items-center p-3 text-green-800 bg-green-50 rounded-md">
              <CheckCircle className="h-5 w-5 mr-2" />
              <span className="text-sm">Toutes vos activités Strava sont déjà enrichies !</span>
            </div>
          )}

          {/* Alerte si quota atteint */}
          {enrichmentStatus && !enrichmentStatus.can_enrich_more && enrichmentStatus.pending_activities > 0 && (
            <div className="flex items-center p-3 text-orange-800 bg-orange-50 rounded-md">
              <AlertCircle className="h-5 w-5 mr-2" />
              <span className="text-sm">Quota API atteint. Veuillez attendre la prochaine fenêtre de 15 minutes.</span>
            </div>
          )}
        </div>
      </div>

      {/* Quotas API Strava */}
      <div className="card">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-medium text-gray-900 flex items-center">
            <Clock className="h-5 w-5 mr-2" />
            Quotas API Strava
          </h3>
        </div>

        {quotaStatus && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Quota journalier */}
            <div className="border rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <h4 className="font-medium text-gray-900">Quota journalier</h4>
                <span className={`text-sm px-2 py-1 rounded ${getQuotaColor(quotaStatus.daily_used, quotaStatus.daily_limit)}`}>
                  {quotaStatus.daily_used} / {quotaStatus.daily_limit}
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2 mb-2">
                <div 
                  className={`h-2 rounded-full transition-all duration-300 ${
                    (quotaStatus.daily_used / quotaStatus.daily_limit) >= 0.9 ? 'bg-red-500' :
                    (quotaStatus.daily_used / quotaStatus.daily_limit) >= 0.7 ? 'bg-orange-500' : 'bg-green-500'
                  }`}
                  style={{ width: `${Math.min(100, (quotaStatus.daily_used / quotaStatus.daily_limit) * 100)}%` }}
                ></div>
              </div>
              <p className="text-xs text-gray-500">
                Renouvellement : {formatDateTime(quotaStatus.daily_reset)}
              </p>
            </div>

            {/* Quota 15 minutes */}
            <div className="border rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <h4 className="font-medium text-gray-900">Quota 15 minutes</h4>
                <span className={`text-sm px-2 py-1 rounded ${getQuotaColor(quotaStatus.per_15min_used, quotaStatus.per_15min_limit)}`}>
                  {quotaStatus.per_15min_used} / {quotaStatus.per_15min_limit}
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2 mb-2">
                <div 
                  className={`h-2 rounded-full transition-all duration-300 ${
                    (quotaStatus.per_15min_used / quotaStatus.per_15min_limit) >= 0.9 ? 'bg-red-500' :
                    (quotaStatus.per_15min_used / quotaStatus.per_15min_limit) >= 0.7 ? 'bg-orange-500' : 'bg-green-500'
                  }`}
                  style={{ width: `${Math.min(100, (quotaStatus.per_15min_used / quotaStatus.per_15min_limit) * 100)}%` }}
                ></div>
              </div>
              <p className="text-xs text-gray-500">
                Prochain renouvellement : {formatDateTime(quotaStatus.next_15min_reset)}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Informations sur les données détaillées */}
      <div className="card">
        <h3 className="text-lg font-medium text-gray-900 mb-4">À propos des données détaillées</h3>
        <div className="prose prose-sm text-gray-600">
          <p>
            L'enrichissement des activités récupère les données complètes depuis l'API Strava :
          </p>
          <ul className="list-disc list-inside mt-2 space-y-1">
            <li><strong>Streams GPS</strong> : Coordonnées précises, altitude, vitesse par seconde</li>
            <li><strong>Données physiologiques</strong> : Fréquence cardiaque, cadence, puissance détaillées</li>
            <li><strong>Segments et tours</strong> : Performance sur segments Strava, tours automatiques</li>
            <li><strong>Conditions</strong> : Température, conditions météorologiques</li>
          </ul>
          <p className="mt-4">
            <strong>Note :</strong> Chaque activité nécessite 3 requêtes API (streams + laps + segments). 
            Les quotas Strava limitent à 100 requêtes par tranche de 15 minutes et 1000 par jour.
          </p>
        </div>
      </div>
    </div>
  )
} 