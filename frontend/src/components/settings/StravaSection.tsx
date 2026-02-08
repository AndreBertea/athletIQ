import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link2, CheckCircle, AlertCircle, RefreshCw, Download, Database } from 'lucide-react'
import { Link } from 'react-router-dom'
import { authService } from '../../services/authService'
import { activityService } from '../../services/activityService'
import type { ApiError } from '../../services/activityService'
import { useToast } from '../../contexts/ToastContext'

export default function StravaSection() {
  const [syncStatus, setSyncStatus] = useState('')
  const [selectedDays, setSelectedDays] = useState(30)
  const [isEnriching, setIsEnriching] = useState(false)
  const queryClient = useQueryClient()
  const toast = useToast()

  // --- Queries ---

  const { data: stravaStatus, isLoading, refetch } = useQuery({
    queryKey: ['strava-status'],
    queryFn: () => authService.getStravaStatus(),
    staleTime: 30_000,
  })

  const {
    data: enrichmentStatus,
    refetch: refetchEnrichment,
    isLoading: enrichmentLoading,
    error: enrichmentError,
  } = useQuery({
    queryKey: ['enrichment-status'],
    queryFn: () => activityService.getEnrichmentStatus(),
    enabled: !!stravaStatus?.connected,
    staleTime: 60_000,
    refetchInterval: 10_000,
    refetchIntervalInBackground: true,
  })

  // --- Mutations ---

  const connectMutation = useMutation({
    mutationFn: () => authService.initiateStravaLogin(),
    onSuccess: (data) => {
      window.location.href = data.authorization_url
    },
    onError: () => {
      toast.error('Erreur lors de la connexion Strava')
    },
  })

  const syncMutation = useMutation({
    mutationFn: (daysBack: number) => activityService.syncStravaActivities(daysBack),
    onSuccess: (data) => {
      const periodText = data.period === 'all' ? 'toutes vos activites' : `${selectedDays} derniers jours`
      const newCount = data.new_activities_saved
      const totalCount = data.total_activities_fetched

      if (newCount === 0) {
        setSyncStatus(`Import termine - Aucune nouvelle activite trouvee (${totalCount} activites verifiees)`)
      } else if (newCount === totalCount) {
        setSyncStatus(`Import termine ! ${newCount} activites importees (${periodText})`)
      } else {
        setSyncStatus(`Import termine ! ${newCount} nouvelles activites importees sur ${totalCount} trouvees (${periodText})`)
      }

      queryClient.invalidateQueries({ queryKey: ['activities'] })
      queryClient.invalidateQueries({ queryKey: ['activity-stats'] })
    },
    onError: (error: ApiError) => {
      const msg = error.response?.data?.detail || 'Echec de la synchronisation'
      setSyncStatus(`Erreur: ${msg}`)
      toast.error(msg)
    },
  })

  const enrichBatchMutation = useMutation({
    mutationFn: (maxActivities: number) => activityService.enrichBatchActivities(maxActivities),
    onSuccess: (data) => {
      toast.success(data.message)
      setTimeout(() => refetchEnrichment(), 2000)
    },
    onError: (error: ApiError) => {
      toast.error(error.response?.data?.detail || 'Echec de l\'enrichissement')
    },
  })

  // --- Handlers ---

  const handleConnect = () => connectMutation.mutate()

  const handleSync = () => {
    const daysText = selectedDays === 9999 ? 'toutes vos activites' : `les ${selectedDays} derniers jours`
    setSyncStatus(`Import en cours de ${daysText}...`)
    syncMutation.mutate(selectedDays)
  }

  const handleRefreshStatus = () => {
    setSyncStatus('Verification du statut de connexion...')
    refetch()
      .then(() => {
        setSyncStatus('Statut de connexion mis a jour')
        setTimeout(() => setSyncStatus(''), 3000)
      })
      .catch(() => {
        setSyncStatus('Erreur lors de la verification du statut')
        setTimeout(() => setSyncStatus(''), 3000)
      })
  }

  const handleStartEnrichment = async () => {
    if (!enrichmentStatus) return
    setIsEnriching(true)
    try {
      const maxActivities = Math.min(enrichmentStatus.pending_activities, 10)
      await enrichBatchMutation.mutateAsync(maxActivities)
    } finally {
      setIsEnriching(false)
    }
  }

  // --- OAuth callback params ---

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search)
    const success = urlParams.get('success')
    const error = urlParams.get('error')
    const message = urlParams.get('message')
    const athleteId = urlParams.get('athlete_id')

    if (success === 'true') {
      setSyncStatus(`Connexion Strava reussie ! Athlete ID: ${athleteId}`)
      setTimeout(() => {
        refetch()
        window.history.replaceState({}, document.title, window.location.pathname)
      }, 2000)
    } else if (error) {
      let errorMessage = 'Erreur de connexion inconnue'
      if (message) {
        errorMessage = decodeURIComponent(message.replace(/\+/g, ' '))
      }
      switch (error) {
        case 'oauth_error':
          errorMessage = `Erreur OAuth Strava: ${errorMessage}`
          break
        case 'no_code':
          errorMessage = 'Code d\'autorisation manquant. Veuillez reessayer la connexion.'
          break
        case 'no_state':
          errorMessage = 'Session expiree. Veuillez vous reconnecter et reessayer.'
          break
        case 'invalid_state':
          errorMessage = 'Erreur de securite. Veuillez vous reconnecter.'
          break
        case 'user_not_found':
          errorMessage = 'Utilisateur non trouve. Veuillez vous reconnecter.'
          break
        case 'callback_error':
          errorMessage = `Erreur technique: ${errorMessage}`
          break
        default:
          errorMessage = `Erreur de connexion: ${errorMessage || error}`
      }
      setSyncStatus(errorMessage)
      setTimeout(() => {
        window.history.replaceState({}, document.title, window.location.pathname)
      }, 5000)
    }
  }, [refetch])

  // --- Render ---

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500"></div>
      </div>
    )
  }

  const isConnected = stravaStatus?.connected
  const isExpired = stravaStatus?.is_expired

  return (
    <div className="space-y-6">
      {/* Status Card */}
      <div className="card">
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            {isConnected ? (
              <CheckCircle className="h-8 w-8 text-green-500" />
            ) : (
              <AlertCircle className="h-8 w-8 text-gray-400" />
            )}
            <div className="ml-4">
              <h3 className="text-lg font-medium text-gray-900">
                {isConnected ? 'Compte Strava connecte' : 'Compte Strava non connecte'}
              </h3>
              <p className="text-sm text-gray-500">
                {isConnected
                  ? `Athlete ID: ${stravaStatus.athlete_id} — Permissions: ${stravaStatus.scope}`
                  : 'Connectez votre compte pour synchroniser vos activites'}
              </p>
              {isExpired && (
                <p className="text-sm text-red-600 mt-1">
                  Token expire - reconnectez-vous pour continuer la synchronisation
                </p>
              )}
            </div>
          </div>

          {/* Connect / Reconnect button */}
          {(!isConnected || isExpired) && (
            <button
              onClick={handleConnect}
              disabled={connectMutation.isPending}
              className="btn-primary"
            >
              {connectMutation.isPending ? (
                <div className="flex items-center">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  Connexion...
                </div>
              ) : (
                <>
                  <Link2 className="h-4 w-4 mr-2" />
                  {isExpired ? 'Reconnecter' : 'Connecter Strava'}
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Import & Refresh — only when connected */}
      {isConnected && !isExpired && (
        <div className="card">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Import des activites</h3>

          <div className="space-y-4">
            {/* Refresh status */}
            <button
              onClick={handleRefreshStatus}
              className="btn-secondary text-sm px-3 py-2 w-full"
            >
              <RefreshCw className="h-4 w-4 mr-1" />
              Verifier statut de connexion
            </button>

            {/* Period selector */}
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-2">
                Choisir la periode d'import
              </label>
              <select
                value={selectedDays}
                onChange={(e) => setSelectedDays(Number(e.target.value))}
                className="w-full text-sm border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value={7}>7 derniers jours</option>
                <option value={14}>14 derniers jours</option>
                <option value={30}>30 derniers jours (recommande)</option>
                <option value={60}>2 derniers mois</option>
                <option value={90}>3 derniers mois</option>
                <option value={180}>6 derniers mois</option>
                <option value={365}>Cette annee (365 jours)</option>
                <option value={730}>2 dernieres annees</option>
                <option value={9999}>Toutes mes activites (historique complet)</option>
              </select>
            </div>

            {selectedDays === 9999 && (
              <div className="text-xs text-amber-600 bg-amber-50 p-2 rounded border border-amber-200">
                <strong>Import complet :</strong> Cela peut prendre plusieurs minutes selon votre historique Strava.
              </div>
            )}

            {/* Sync button */}
            <button
              onClick={handleSync}
              disabled={syncMutation.isPending}
              className="btn-primary text-sm px-4 py-2 w-full"
            >
              {syncMutation.isPending ? (
                <div className="flex items-center justify-center">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  Import en cours...
                </div>
              ) : (
                <>
                  <Download className="h-4 w-4 mr-2" />
                  {selectedDays === 9999
                    ? 'Importer toutes les activites'
                    : `Importer les ${selectedDays} derniers jours`}
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Sync Status */}
      {syncStatus && (
        <div
          className={`rounded-md p-4 ${
            syncStatus.includes('Erreur')
              ? 'bg-red-50 text-red-800 border border-red-200'
              : 'bg-green-50 text-green-800 border border-green-200'
          }`}
        >
          <div className="flex">
            {syncStatus.includes('Erreur') ? (
              <AlertCircle className="h-5 w-5 text-red-400" />
            ) : (
              <CheckCircle className="h-5 w-5 text-green-400" />
            )}
            <p className="ml-3 text-sm font-medium">{syncStatus}</p>
          </div>
        </div>
      )}

      {/* Enrichissement batch */}
      {isConnected && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-medium text-gray-900 flex items-center">
              <Database className="h-5 w-5 mr-2" />
              Donnees detaillees Strava
            </h3>
            <Link
              to="/strava-connect/donnees-detaillees"
              className="text-sm text-primary-600 hover:text-primary-700 font-medium"
            >
              Vue complete →
            </Link>
          </div>

          <div className="space-y-4">
            {enrichmentError ? (
              <div className="bg-red-50 border border-red-200 rounded p-4">
                <div className="flex items-center text-red-800">
                  <AlertCircle className="h-5 w-5 mr-2" />
                  <span className="font-medium">Erreur de chargement des donnees d'enrichissement</span>
                </div>
                <p className="text-sm text-red-600 mt-2">
                  {(enrichmentError as ApiError)?.message ||
                    (enrichmentError as ApiError)?.response?.data?.detail ||
                    'Impossible de recuperer le statut'}
                </p>
                <button
                  onClick={() => refetchEnrichment()}
                  className="mt-2 text-sm bg-red-100 hover:bg-red-200 px-3 py-1 rounded"
                >
                  Reessayer
                </button>
              </div>
            ) : enrichmentLoading ? (
              <div className="flex items-center justify-center py-8 bg-blue-50 rounded">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500 mr-3"></div>
                <span className="text-blue-700">Chargement du statut d'enrichissement...</span>
              </div>
            ) : enrichmentStatus ? (
              <>
                {/* Stats grid */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="text-center p-3 bg-blue-50 rounded">
                    <div className="text-xl font-bold text-blue-600">
                      {enrichmentStatus.strava_activities}
                    </div>
                    <div className="text-xs text-blue-700">Activites Strava</div>
                  </div>
                  <div className="text-center p-3 bg-green-50 rounded">
                    <div className="text-xl font-bold text-green-600">
                      {enrichmentStatus.enriched_activities}
                    </div>
                    <div className="text-xs text-green-700">Enrichies</div>
                  </div>
                  <div className="text-center p-3 bg-orange-50 rounded">
                    <div className="text-xl font-bold text-orange-600">
                      {enrichmentStatus.pending_activities}
                    </div>
                    <div className="text-xs text-orange-700">En attente</div>
                  </div>
                  <div className="text-center p-3 bg-purple-50 rounded">
                    <div className="text-xl font-bold text-purple-600">
                      {enrichmentStatus.enrichment_percentage}%
                    </div>
                    <div className="text-xs text-purple-700">Progression</div>
                  </div>
                </div>

                {/* Progress bar */}
                <div className="space-y-2">
                  <div className="flex justify-between text-sm text-gray-600">
                    <span>Progression de l'enrichissement</span>
                    <span>{enrichmentStatus.enrichment_percentage}% complete</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-3">
                    <div
                      className="bg-gradient-to-r from-purple-500 to-blue-500 h-3 rounded-full transition-all duration-500 ease-out"
                      style={{ width: `${enrichmentStatus.enrichment_percentage}%` }}
                    ></div>
                  </div>
                </div>

                {/* Info */}
                <div className="bg-blue-50 border border-blue-200 rounded p-4">
                  <div className="flex items-start">
                    <div className="w-2 h-2 bg-blue-500 rounded-full mt-2 mr-3 flex-shrink-0"></div>
                    <div className="text-sm text-blue-800">
                      <strong>Donnees detaillees :</strong> GPS precis, frequence cardiaque par seconde,
                      segments, tours automatiques. L'enrichissement se fait selon les quotas API Strava.
                    </div>
                  </div>
                </div>

                {/* Enrich action */}
                <div className="flex items-center justify-between text-sm border-t pt-4">
                  <div className="flex items-center space-x-2">
                    {enrichmentStatus.pending_activities > 0 ? (
                      <button
                        onClick={handleStartEnrichment}
                        disabled={isEnriching || enrichBatchMutation.isPending}
                        className="px-3 py-1.5 bg-green-100 hover:bg-green-200 text-green-800 rounded text-sm font-medium disabled:opacity-50"
                      >
                        {isEnriching || enrichBatchMutation.isPending ? (
                          <div className="flex items-center">
                            <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-green-600 mr-1"></div>
                            Enrichissement en cours...
                          </div>
                        ) : (
                          <>
                            <Database className="h-3 w-3 mr-1" />
                            Enrichir {Math.min(enrichmentStatus.pending_activities, 10)} activite(s)
                          </>
                        )}
                      </button>
                    ) : (
                      <div className="flex items-center text-green-600">
                        <CheckCircle className="h-4 w-4 mr-1" />
                        <span className="text-sm font-medium">Toutes les activites enrichies</span>
                      </div>
                    )}

                    <button
                      onClick={() => refetchEnrichment()}
                      className="px-2 py-1 bg-gray-100 hover:bg-gray-200 rounded text-gray-700 text-xs"
                    >
                      <RefreshCw className="h-3 w-3 mr-1" />
                      Actualiser
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="text-center py-8 text-gray-500">
                <Database className="h-12 w-12 mx-auto mb-4 text-gray-300" />
                <p className="text-sm">Aucune donnee d'enrichissement disponible</p>
                <button
                  onClick={() => refetchEnrichment()}
                  className="mt-2 text-sm bg-gray-100 hover:bg-gray-200 px-3 py-1 rounded"
                >
                  Charger les donnees
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
