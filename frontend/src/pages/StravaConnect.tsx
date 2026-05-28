// Il n'est pas nécessaire d'importer "react" en jaune (avertissement ESLint) si vous utilisez React 17+ et le nouveau JSX transform.
// Remplacez simplement par :
import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link2, CheckCircle, AlertCircle, RefreshCw, Download, Shield, FileDown, Trash2, Database } from 'lucide-react'
import { authService } from '../services/authService'
import { activityService } from '../services/activityService'
import ConfirmationModal from '../components/ConfirmationModal'
import { Link } from 'react-router-dom'
import { useToast } from '../contexts/ToastContext'

export default function StravaConnect() {
  const [syncStatus, setSyncStatus] = useState<string>('')
  const [rgpdStatus, setRgpdStatus] = useState<string>('')
  const [selectedDays, setSelectedDays] = useState<number>(30)
  const [confirmationModal, setConfirmationModal] = useState<{
    isOpen: boolean
    type: 'delete-strava' | 'delete-all' | 'delete-account' | 'export' | null
  }>({ isOpen: false, type: null })
  const queryClient = useQueryClient()
  const toast = useToast()

  const { data: stravaStatus, isLoading, refetch } = useQuery({
    queryKey: ['strava-status'],
    queryFn: () => authService.getStravaStatus(),
    staleTime: 30 * 1000 // 30 secondes
  })

  // Query pour le statut d'enrichissement (données détaillées)
  const { data: enrichmentStatus, refetch: refetchEnrichment, isLoading: enrichmentLoading, error: enrichmentError } = useQuery({
    queryKey: ['enrichment-status'],
    queryFn: () => {
      console.log('🔍 Récupération du statut d\'enrichissement...')
      return activityService.getEnrichmentStatus()
    },
    enabled: !!stravaStatus?.connected, // Seulement si Strava connecté
    staleTime: 60 * 1000, // 1 minute
    refetchInterval: 10000, // Polling toutes les 10s
    refetchIntervalInBackground: true // Continue le polling même si l'onglet n'est pas actif
  })

  // Log des changements d'état
  useEffect(() => {
    if (enrichmentStatus) {
      console.log('✅ Statut enrichissement récupéré:', enrichmentStatus)
    }
    if (enrichmentError) {
      console.error('❌ Erreur statut enrichissement:', enrichmentError)
    }
  }, [enrichmentStatus, enrichmentError])

  // Mutation pour démarrer l'enrichissement avec le script Python
  const enrichBatchMutation = useMutation({
    mutationFn: (maxActivities: number) => activityService.enrichBatchActivities(maxActivities),
    onSuccess: (data) => {
      toast.success(data.message)
      setTimeout(() => {
        refetchEnrichment()
      }, 2000)
    },
    onError: (error: any) => {
      console.error('Erreur enrichissement:', error)
      toast.error(error.response?.data?.detail || 'Échec de l\'enrichissement')
    }
  })

  // État local pour le spinner d'enrichissement
  const [isEnriching, setIsEnriching] = useState(false)

  // Fonction pour démarrer l'enrichissement avec spinner
  const handleStartEnrichment = async () => {
    if (!enrichmentStatus) return
    
    setIsEnriching(true)
    try {
      // Utiliser le nombre d'activités en attente ou 10 par défaut
      const maxActivities = Math.min(enrichmentStatus.pending_activities, 10)
      await enrichBatchMutation.mutateAsync(maxActivities)
    } finally {
      setIsEnriching(false)
    }
  }

  const connectMutation = useMutation({
    mutationFn: () => authService.initiateStravaLogin(),
    onSuccess: (data) => {
      // Rediriger vers l'URL d'autorisation Strava
      window.location.href = data.authorization_url
    },
    onError: (error) => {
      console.error('Erreur lors de la connexion Strava:', error)
      toast.error('Erreur lors de la connexion Strava')
    }
  })

  const syncMutation = useMutation({
    mutationFn: (daysBack: number) => activityService.syncStravaActivities(daysBack),
    onSuccess: (data) => {
      const periodText = data.period === 'all' ? 'toutes vos activités' : `${selectedDays} derniers jours`
      const newCount = data.new_activities_saved
      const totalCount = data.total_activities_fetched
      
      if (newCount === 0) {
        setSyncStatus(`✅ Import terminé - Aucune nouvelle activité trouvée (${totalCount} activités vérifiées)`)
      } else if (newCount === totalCount) {
        setSyncStatus(`🎉 Import terminé ! ${newCount} activités importées (${periodText})`)
      } else {
        setSyncStatus(`✅ Import terminé ! ${newCount} nouvelles activités importées sur ${totalCount} trouvées (${periodText})`)
      }
      
      // Invalider les caches des activités
      queryClient.invalidateQueries({ queryKey: ['activities'] })
      queryClient.invalidateQueries({ queryKey: ['activity-stats'] })
    },
    onError: (error: any) => {
      const msg = error.response?.data?.detail || 'Échec de la synchronisation'
      setSyncStatus(`Erreur: ${msg}`)
      toast.error(msg)
    }
  })

  // Mutations RGPD
  const deleteStravaMutation = useMutation({
    mutationFn: () => authService.deleteStravaData(),
    onSuccess: (data) => {
      const msg = `Données Strava supprimées: ${data.deleted_activities} activités supprimées`
      setRgpdStatus(msg)
      toast.success(msg)
      queryClient.invalidateQueries({ queryKey: ['strava-status'] })
      queryClient.invalidateQueries({ queryKey: ['activities'] })
      setConfirmationModal({ isOpen: false, type: null })
    },
    onError: (error: any) => {
      const msg = error.response?.data?.detail || 'Échec de la suppression'
      setRgpdStatus(`Erreur: ${msg}`)
      toast.error(msg)
    }
  })

  const deleteAllDataMutation = useMutation({
    mutationFn: () => authService.deleteAllUserData(),
    onSuccess: (data) => {
      const msg = `Toutes les données supprimées: ${data.deleted_activities} activités, ${data.deleted_workout_plans} plans d'entraînement`
      setRgpdStatus(msg)
      toast.success(msg)
      queryClient.invalidateQueries({ queryKey: ['strava-status'] })
      queryClient.invalidateQueries({ queryKey: ['activities'] })
      queryClient.invalidateQueries({ queryKey: ['workout-plans'] })
      setConfirmationModal({ isOpen: false, type: null })
    },
    onError: (error: any) => {
      const msg = error.response?.data?.detail || 'Échec de la suppression'
      setRgpdStatus(`Erreur: ${msg}`)
      toast.error(msg)
    }
  })

  const deleteAccountMutation = useMutation({
    mutationFn: () => authService.deleteAccount(),
    onSuccess: async () => {
      // Les cookies sont supprimés côté serveur via l'endpoint logout
      try { await authService.logout() } catch { /* ignore */ }
      window.location.href = '/'
    },
    onError: (error: any) => {
      setRgpdStatus(`Erreur: ${error.response?.data?.detail || 'Échec de la suppression du compte'}`)
    }
  })

  const exportDataMutation = useMutation({
    mutationFn: () => authService.exportUserData(),
    onSuccess: (blob) => {
      // Créer un lien de téléchargement
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `agon-export-${new Date().toISOString().split('T')[0]}.json`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      setRgpdStatus('Export des données téléchargé avec succès')
      setConfirmationModal({ isOpen: false, type: null })
    },
    onError: (error: any) => {
      setRgpdStatus(`Erreur: ${error.response?.data?.detail || 'Échec de l\'export'}`)
    }
  })

  const handleConnect = () => {
    connectMutation.mutate()
  }

  const handleSync = () => {
    const daysText = selectedDays === 9999 ? 'toutes vos activités' : `les ${selectedDays} derniers jours`
    setSyncStatus(`Import en cours de ${daysText}...`)
    syncMutation.mutate(selectedDays)
  }

  const handleRefreshStatus = () => {
    setSyncStatus('Vérification du statut de connexion...')
    refetch().then(() => {
      setSyncStatus('Statut de connexion mis à jour ✓')
      setTimeout(() => setSyncStatus(''), 3000)
    }).catch(() => {
      setSyncStatus('Erreur lors de la vérification du statut')
      setTimeout(() => setSyncStatus(''), 3000)
    })
  }

  // Gestionnaires RGPD
  const openConfirmationModal = (type: 'delete-strava' | 'delete-all' | 'delete-account' | 'export') => {
    setConfirmationModal({ isOpen: true, type })
    setRgpdStatus('') // Effacer les anciens messages
  }

  const closeConfirmationModal = () => {
    setConfirmationModal({ isOpen: false, type: null })
  }

  const handleConfirmAction = () => {
    switch (confirmationModal.type) {
      case 'delete-strava':
        deleteStravaMutation.mutate()
        break
      case 'delete-all':
        deleteAllDataMutation.mutate()
        break
      case 'delete-account':
        deleteAccountMutation.mutate()
        break
      case 'export':
        exportDataMutation.mutate()
        break
    }
  }

  const getModalProps = () => {
    switch (confirmationModal.type) {
      case 'delete-strava':
        return {
          title: 'Supprimer les données Strava',
          message: 'Cette action supprimera toutes vos données importées de Strava (activités et authentification). Vous pourrez vous reconnecter à Strava plus tard si vous le souhaitez.',
          confirmText: 'Supprimer les données Strava',
          dangerLevel: 'medium' as const,
          isLoading: deleteStravaMutation.isPending
        }
      case 'delete-all':
        return {
          title: 'Supprimer toutes mes données',
          message: 'Cette action supprimera TOUTES vos données (activités, plans d\'entraînement, connexion Strava) mais conservera votre compte. Vous pourrez créer de nouvelles données après.',
          confirmText: 'Supprimer toutes les données',
          confirmationPhrase: 'SUPPRIMER',
          dangerLevel: 'high' as const,
          isLoading: deleteAllDataMutation.isPending
        }
      case 'delete-account':
        return {
          title: 'Supprimer mon compte',
          message: 'Cette action supprimera définitivement votre compte et TOUTES vos données associées. Vous serez déconnecté et ne pourrez plus accéder à AGON avec ce compte.',
          confirmText: 'Supprimer le compte',
          confirmationPhrase: 'SUPPRIMER MON COMPTE',
          dangerLevel: 'high' as const,
          isLoading: deleteAccountMutation.isPending
        }
      case 'export':
        return {
          title: 'Exporter mes données',
          message: 'Cette action téléchargera toutes vos données personnelles au format JSON. Le fichier contiendra vos informations de profil, activités et plans d\'entraînement.',
          confirmText: 'Télécharger mes données',
          dangerLevel: 'low' as const,
          isLoading: exportDataMutation.isPending
        }
      default:
        return {
          title: '',
          message: '',
          confirmText: '',
          dangerLevel: 'low' as const,
          isLoading: false
        }
    }
  }

  // Vérifier les paramètres URL pour les callbacks OAuth
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search)
    const success = urlParams.get('success')
    const error = urlParams.get('error')
    const message = urlParams.get('message')
    const athleteId = urlParams.get('athlete_id')

    if (success === 'true') {
      // Succès OAuth
      setSyncStatus(`Connexion Strava réussie ! Athlète ID: ${athleteId}`)
      setTimeout(() => {
        refetch()
        // Nettoyer l'URL
        window.history.replaceState({}, document.title, window.location.pathname)
      }, 2000)
    } else if (error) {
      // Erreur OAuth - décodage du message
      let errorMessage = 'Erreur de connexion inconnue'
      
      if (message) {
        // Décoder l'URL encoding
        errorMessage = decodeURIComponent(message.replace(/\+/g, ' '))
      }
      
      // Messages d'erreur personnalisés selon le type
      switch (error) {
        case 'oauth_error':
          errorMessage = `Erreur OAuth Strava: ${errorMessage}`
          break
        case 'no_code':
          errorMessage = 'Code d\'autorisation manquant. Veuillez réessayer la connexion.'
          break
        case 'no_state':
          errorMessage = 'Session expirée. Veuillez vous reconnecter et réessayer.'
          break
        case 'invalid_state':
          errorMessage = 'Erreur de sécurité. Veuillez vous reconnecter.'
          break
        case 'user_not_found':
          errorMessage = 'Utilisateur non trouvé. Veuillez vous reconnecter.'
          break
        case 'callback_error':
          errorMessage = `Erreur technique: ${errorMessage}`
          break
        default:
          errorMessage = `Erreur de connexion: ${errorMessage || error}`
      }
      
      setSyncStatus(errorMessage)
      console.error('Erreur OAuth Strava:', { error, message: errorMessage, originalMessage: message })
      
      // Nettoyer l'URL après 5 secondes
      setTimeout(() => {
        window.history.replaceState({}, document.title, window.location.pathname)
      }, 5000)
    }
  }, [refetch])

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
    <div className="max-w-2xl mx-auto space-y-8">
      {/* Header */}
      <div className="text-center">
        <div className="mx-auto h-16 w-16 bg-orange-100 rounded-full flex items-center justify-center">
          <Link2 className="h-8 w-8 text-orange-600" />
        </div>
        <h1 className="mt-4 text-3xl font-bold text-gray-900">
          Connexion Strava
        </h1>
        <p className="mt-2 text-gray-600">
          Synchronisez vos activités Strava pour suivre vos performances
        </p>
      </div>

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
                {isConnected ? 'Compte Strava connecté' : 'Compte Strava non connecté'}
              </h3>
              <p className="text-sm text-gray-500">
                {isConnected 
                  ? `Athlète ID: ${stravaStatus.athlete_id} • Permissions: ${stravaStatus.scope}`
                  : 'Connectez votre compte pour synchroniser vos activités'
                }
              </p>
              {isExpired && (
                <p className="text-sm text-red-600 mt-1">
                  ⚠️ Token expiré - reconnectez-vous pour continuer la synchronisation
                </p>
              )}
            </div>
          </div>
          
          {/* Action Button */}
          <div>
            {!isConnected || isExpired ? (
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
            ) : (
              <div className="flex flex-col space-y-3">
                {/* Bouton Vérifier statut */}
                <button
                  onClick={handleRefreshStatus}
                  className="btn-secondary text-sm px-3 py-2 w-full"
                  title="Vérifie le statut de connexion (token expiré, permissions, etc.)"
                >
                  <RefreshCw className="h-4 w-4 mr-1" />
                  Vérifier statut de connexion
                </button>

                {/* Section Import d'activités */}
                <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                  <h4 className="text-sm font-medium text-gray-700 mb-3">Import des activités</h4>
                  
                  <div className="space-y-3">
                    <div>
                      <label className="block text-sm font-medium text-gray-600 mb-2">
                        Choisir la période d'import
                      </label>
                      <select
                        value={selectedDays}
                        onChange={(e) => setSelectedDays(Number(e.target.value))}
                        className="w-full text-sm border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      >
                        <option value={7}>7 derniers jours</option>
                        <option value={14}>14 derniers jours</option>
                        <option value={30}>30 derniers jours (recommandé)</option>
                        <option value={60}>2 derniers mois</option>
                        <option value={90}>3 derniers mois</option>
                        <option value={180}>6 derniers mois</option>
                        <option value={365}>Cette année (365 jours)</option>
                        <option value={730}>2 dernières années</option>
                        <option value={9999}>🌟 Toutes mes activités (historique complet)</option>
                      </select>
                    </div>

                    {selectedDays === 9999 && (
                      <div className="text-xs text-amber-600 bg-amber-50 p-2 rounded border border-amber-200">
                        <strong>⚠️ Import complet :</strong> Cela peut prendre plusieurs minutes selon votre historique Strava.
                      </div>
                    )}

                    {/* Bouton d'import */}
                    <button
                      onClick={handleSync}
                      disabled={syncMutation.isPending}
                      className="btn-primary text-sm px-4 py-2 w-full"
                      title={`Importe ${selectedDays === 9999 ? 'toutes vos activités' : `les activités des ${selectedDays} derniers jours`} depuis Strava`}
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
                            ? 'Importer toutes les activités' 
                            : `Importer les ${selectedDays} derniers jours`
                          }
                        </>
                      )}
                    </button>
                  </div>
                </div>

                <div className="text-xs text-gray-500 bg-blue-50 p-2 rounded">
                  <strong>💡 Conseil :</strong> Pour une première utilisation, commencez par "30 derniers jours" pour tester, puis utilisez "Toutes mes activités" pour l'historique complet.
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Sync Status */}
      {syncStatus && (
        <div className={`rounded-md p-4 ${
          syncStatus.includes('Erreur') 
            ? 'bg-red-50 text-red-800 border border-red-200' 
            : 'bg-green-50 text-green-800 border border-green-200'
        }`}>
          <div className="flex">
            {syncStatus.includes('Erreur') ? (
              <AlertCircle className="h-5 w-5 text-red-400" />
            ) : (
              <CheckCircle className="h-5 w-5 text-green-400" />
            )}
            <div className="ml-3">
              <p className="text-sm font-medium">{syncStatus}</p>
            </div>
          </div>
        </div>
      )}

      {/* Information */}
      <div className="card">
        <h3 className="text-lg font-medium text-gray-900 mb-4">
          À propos de la synchronisation Strava
        </h3>
        <div className="space-y-3 text-sm text-gray-600">
          <div className="flex items-start">
            <RefreshCw className="h-4 w-4 text-blue-500 mt-1 mr-3 flex-shrink-0" />
            <p>
              <strong>Vérifier statut :</strong> Contrôle l'état de votre connexion Strava (token valide, permissions, etc.) sans importer de données
            </p>
          </div>
          <div className="flex items-start">
            <Download className="h-4 w-4 text-orange-500 mt-1 mr-3 flex-shrink-0" />
            <p>
              <strong>Importer activités :</strong> Récupère vos activités depuis Strava avec tous les détails (distance, temps, dénivelé, fréquence cardiaque, etc.). Choisissez la période selon vos besoins : derniers jours, année complète ou historique complet.
            </p>
          </div>
          <div className="flex items-start">
            <div className="w-2 h-2 bg-primary-500 rounded-full mt-2 mr-3 flex-shrink-0"></div>
            <p>
              <strong>Fréquence recommandée :</strong> Importez vos activités après chaque session d'entraînement ou périodiquement
            </p>
          </div>
          <div className="flex items-start">
            <div className="w-2 h-2 bg-primary-500 rounded-full mt-2 mr-3 flex-shrink-0"></div>
            <p>
              <strong>Sécurité :</strong> Vos tokens d'accès sont chiffrés et stockés de manière sécurisée. AGON n'accède qu'aux données d'activité en lecture seule
            </p>
          </div>
        </div>
      </div>

      {/* Enrichissement des données détaillées */}
      {stravaStatus?.connected && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-medium text-gray-900 flex items-center">
              <Database className="h-5 w-5 mr-2" />
              Données détaillées Strava
            </h3>
            <Link 
              to="/strava-connect/donnees-detaillees"
              className="text-sm text-primary-600 hover:text-primary-700 font-medium"
            >
              Vue complète →
            </Link>
          </div>
          
          {/* États d'affichage selon les conditions */}
          <div className="space-y-4">
            {enrichmentError ? (
              /* Affichage d'erreur */
              <div className="bg-red-50 border border-red-200 rounded p-4">
                <div className="flex items-center text-red-800">
                  <AlertCircle className="h-5 w-5 mr-2" />
                  <span className="font-medium">Erreur de chargement des données d'enrichissement</span>
                </div>
                <p className="text-sm text-red-600 mt-2">
                  {(enrichmentError as any)?.message || (enrichmentError as any)?.response?.data?.detail || 'Impossible de récupérer le statut'}
                </p>
                <button
                  onClick={() => refetchEnrichment()}
                  className="mt-2 text-sm bg-red-100 hover:bg-red-200 px-3 py-1 rounded"
                >
                  Réessayer
                </button>
              </div>
            ) : enrichmentLoading ? (
              /* État de chargement avec animation */
              <div className="flex items-center justify-center py-8 bg-blue-50 rounded">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500 mr-3"></div>
                <span className="text-blue-700">Chargement du statut d'enrichissement...</span>
              </div>
            ) : enrichmentStatus ? (
              <>
                {/* Statut compact avec données réelles */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="text-center p-3 bg-blue-50 rounded">
                    <div className="text-xl font-bold text-blue-600">
                      {enrichmentStatus.strava_activities}
                    </div>
                    <div className="text-xs text-blue-700">Activités Strava</div>
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

                {/* Barre de progression améliorée */}
                <div className="space-y-2">
                  <div className="flex justify-between text-sm text-gray-600">
                    <span>Progression de l'enrichissement</span>
                    <span>{enrichmentStatus.enrichment_percentage}% complété</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-3">
                    <div 
                      className="bg-gradient-to-r from-purple-500 to-blue-500 h-3 rounded-full transition-all duration-500 ease-out" 
                      style={{ width: `${enrichmentStatus.enrichment_percentage}%` }}
                    ></div>
                  </div>
                </div>

                {/* Informations détaillées */}
                <div className="bg-blue-50 border border-blue-200 rounded p-4">
                  <div className="flex items-start">
                    <div className="w-2 h-2 bg-blue-500 rounded-full mt-2 mr-3 flex-shrink-0"></div>
                    <div className="text-sm text-blue-800">
                      <strong>Données détaillées :</strong> GPS précis, fréquence cardiaque par seconde, segments, tours automatiques. 
                      L'enrichissement se fait automatiquement en arrière-plan selon les quotas API Strava.
                    </div>
                  </div>
                </div>

                {/* Actions avec plus de feedback */}
                <div className="flex items-center justify-between text-sm border-t pt-4">
                  <div className="flex items-center space-x-2">
                    {/* Bouton d'enrichissement avec état détaillé */}
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
                            Enrichir {Math.min(enrichmentStatus.pending_activities, 10)} activité(s)
                          </>
                        )}
                      </button>
                    ) : (
                      <div className="flex items-center text-green-600">
                        <CheckCircle className="h-4 w-4 mr-1" />
                        <span className="text-sm font-medium">Toutes les activités enrichies</span>
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
              /* État vide */
              <div className="text-center py-8 text-gray-500">
                <Database className="h-12 w-12 mx-auto mb-4 text-gray-300" />
                <p className="text-sm">Aucune donnée d'enrichissement disponible</p>
                <button
                  onClick={() => refetchEnrichment()}
                  className="mt-2 text-sm bg-gray-100 hover:bg-gray-200 px-3 py-1 rounded"
                >
                  Charger les données
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* RGPD Status */}
      {rgpdStatus && (
        <div className={`rounded-md p-4 ${
          rgpdStatus.includes('Erreur') 
            ? 'bg-red-50 text-red-800 border border-red-200' 
            : 'bg-green-50 text-green-800 border border-green-200'
        }`}>
          <div className="flex">
            {rgpdStatus.includes('Erreur') ? (
              <AlertCircle className="h-5 w-5 text-red-400" />
            ) : (
              <CheckCircle className="h-5 w-5 text-green-400" />
            )}
            <div className="ml-3">
              <p className="text-sm font-medium">{rgpdStatus}</p>
            </div>
          </div>
        </div>
      )}

      {/* RGPD - Gestion des données personnelles */}
      <div className="card">
        <div className="flex items-center mb-4">
          <div className="p-2 bg-blue-100 rounded-full">
            <Shield className="h-6 w-6 text-blue-600" />
          </div>
          <h3 className="ml-3 text-lg font-medium text-gray-900">
            Gestion de vos données personnelles (RGPD)
          </h3>
        </div>
        
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            Conformément au Règlement Général sur la Protection des Données (RGPD), vous avez le contrôle total sur vos données personnelles stockées dans AGON.
          </p>
          
          {/* Export des données */}
          <div className="border border-gray-200 rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-start">
                <FileDown className="h-5 w-5 text-blue-500 mt-1" />
                <div className="ml-3">
                  <h4 className="text-sm font-medium text-gray-900">
                    Exporter mes données
                  </h4>
                  <p className="text-sm text-gray-600 mt-1">
                    Téléchargez toutes vos données personnelles au format JSON
                  </p>
                </div>
              </div>
              <button
                onClick={() => openConfirmationModal('export')}
                className="btn-secondary text-sm"
                disabled={exportDataMutation.isPending}
              >
                {exportDataMutation.isPending ? (
                  <div className="flex items-center">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-600 mr-2"></div>
                    Export...
                  </div>
                ) : (
                  <>
                    <FileDown className="h-4 w-4 mr-2" />
                    Exporter
                  </>
                )}
              </button>
            </div>
          </div>
          
          {/* Suppression des données Strava */}
          {isConnected && (
            <div className="border border-orange-200 rounded-lg p-4 bg-orange-50">
              <div className="flex items-center justify-between">
                <div className="flex items-start">
                  <Database className="h-5 w-5 text-orange-500 mt-1" />
                  <div className="ml-3">
                    <h4 className="text-sm font-medium text-gray-900">
                      Supprimer les données Strava
                    </h4>
                    <p className="text-sm text-gray-600 mt-1">
                      Supprime uniquement vos données importées de Strava
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => openConfirmationModal('delete-strava')}
                  className="px-3 py-1.5 text-sm bg-orange-600 text-white rounded-md hover:bg-orange-700 transition-colors"
                  disabled={deleteStravaMutation.isPending}
                >
                  {deleteStravaMutation.isPending ? (
                    <div className="flex items-center">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                      Suppression...
                    </div>
                  ) : (
                    'Supprimer'
                  )}
                </button>
              </div>
            </div>
          )}
          
          {/* Suppression de toutes les données */}
          <div className="border border-red-200 rounded-lg p-4 bg-red-50">
            <div className="flex items-center justify-between">
              <div className="flex items-start">
                <Trash2 className="h-5 w-5 text-red-500 mt-1" />
                <div className="ml-3">
                  <h4 className="text-sm font-medium text-gray-900">
                    Supprimer toutes mes données
                  </h4>
                  <p className="text-sm text-gray-600 mt-1">
                    Supprime toutes vos données mais conserve votre compte
                  </p>
                </div>
              </div>
              <button
                onClick={() => openConfirmationModal('delete-all')}
                className="px-3 py-1.5 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors"
                disabled={deleteAllDataMutation.isPending}
              >
                {deleteAllDataMutation.isPending ? (
                  <div className="flex items-center">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    Suppression...
                  </div>
                ) : (
                  'Supprimer'
                )}
              </button>
            </div>
          </div>
          
          {/* Suppression du compte */}
          <div className="border border-red-300 rounded-lg p-4 bg-red-100">
            <div className="flex items-center justify-between">
              <div className="flex items-start">
                <Trash2 className="h-5 w-5 text-red-600 mt-1" />
                <div className="ml-3">
                  <h4 className="text-sm font-medium text-gray-900">
                    Supprimer mon compte
                  </h4>
                  <p className="text-sm text-gray-600 mt-1">
                    Supprime définitivement votre compte et toutes vos données
                  </p>
                </div>
              </div>
              <button
                onClick={() => openConfirmationModal('delete-account')}
                className="px-3 py-1.5 text-sm bg-red-700 text-white rounded-md hover:bg-red-800 transition-colors"
                disabled={deleteAccountMutation.isPending}
              >
                {deleteAccountMutation.isPending ? (
                  <div className="flex items-center">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    Suppression...
                  </div>
                ) : (
                  'Supprimer'
                )}
              </button>
            </div>
          </div>
          
          <div className="text-xs text-gray-500 bg-gray-50 p-3 rounded-md">
            <p>
              <strong>Important :</strong> Ces actions sont conformes au RGPD (Règlement Général sur la Protection des Données). 
              La suppression des données est irréversible. Nous vous recommandons d'exporter vos données avant toute suppression.
            </p>
          </div>
        </div>
      </div>

      {/* Help */}
      <div className="text-center space-y-2">
        <p className="text-sm text-gray-500">
          Problème de connexion ? Vérifiez que vous autorisez les permissions "Lecture d'activités" lors de la connexion Strava.
        </p>
        <div className="text-xs text-gray-400 bg-gray-50 rounded p-2 inline-block">
          💡 <strong>Astuce :</strong> Utilisez "Vérifier statut" si la connexion semble inactive, 
          puis "Importer activités" pour récupérer vos dernières séances
        </div>
      </div>

      {/* Modal de confirmation */}
      <ConfirmationModal
        isOpen={confirmationModal.isOpen}
        onClose={closeConfirmationModal}
        onConfirm={handleConfirmAction}
        {...getModalProps()}
      />
    </div>
  )
}
