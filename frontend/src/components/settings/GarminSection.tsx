import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle,
  AlertCircle,
  RefreshCw,
  LogOut,
  Heart,
  Moon,
  Activity,
  Loader2,
  Shield,
  Download,
  Zap,
} from 'lucide-react'
import { useToast } from '../../contexts/ToastContext'
import { garminService } from '../../services/garminService'
import type { ApiError } from '../../services/activityService'
import { formatDateShort } from '../../lib/format'

export default function GarminSection() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [daysBack, setDaysBack] = useState(30)
  const queryClient = useQueryClient()
  const toast = useToast()

  // Vider le mot de passe au unmount pour éviter qu'il reste en mémoire
  useEffect(() => {
    return () => { setPassword('') }
  }, [])

  // --- Queries ---

  const { data: garminStatus, isLoading } = useQuery({
    queryKey: ['garmin-status'],
    queryFn: garminService.getGarminStatus,
    staleTime: 30_000,
  })

  const isConnected = garminStatus?.connected ?? false

  const { data: dailyData, isLoading: dailyLoading } = useQuery({
    queryKey: ['garmin-daily-preview'],
    queryFn: () => {
      const to = new Date()
      const from = new Date()
      from.setDate(from.getDate() - 6)
      return garminService.getGarminDaily(
        from.toISOString().split('T')[0],
        to.toISOString().split('T')[0],
      )
    },
    enabled: isConnected,
    staleTime: 60_000,
  })

  // --- Mutations ---

  const loginMutation = useMutation({
    mutationFn: () => garminService.loginGarmin(email, password),
    onSuccess: () => {
      toast.success('Connexion Garmin reussie !')
      setEmail('')
      setPassword('')
      queryClient.invalidateQueries({ queryKey: ['garmin-status'] })
      queryClient.invalidateQueries({ queryKey: ['garmin-daily-preview'] })
    },
    onError: (error: ApiError) => {
      const msg = error.response?.data?.detail || 'Echec de la connexion Garmin'
      toast.error(msg)
    },
  })

  const syncMutation = useMutation({
    mutationFn: () => garminService.syncGarminDaily(daysBack),
    onSuccess: (data) => {
      toast.success(data.message || `Sync Garmin terminee (${daysBack} jours)`)
      queryClient.invalidateQueries({ queryKey: ['garmin-daily-preview'] })
    },
    onError: (error: ApiError) => {
      toast.error(error.response?.data?.detail || 'Echec de la synchronisation Garmin')
    },
  })

  const syncActivitiesMutation = useMutation({
    mutationFn: () => garminService.syncGarminActivities(daysBack),
    onSuccess: (data) => {
      toast.success(
        `Activites : ${data.created} creees, ${data.linked} liees, ${data.skipped} deja syncees`,
      )
    },
    onError: (error: ApiError) => {
      toast.error(
        error.response?.data?.detail || 'Echec de la synchronisation des activites',
      )
    },
  })

  const batchEnrichMutation = useMutation({
    mutationFn: () => garminService.batchEnrichGarminFit(10),
    onSuccess: (data) => {
      toast.success(`FIT : ${data.enriched}/${data.total} activites enrichies`)
    },
    onError: (error: ApiError) => {
      toast.error(error.response?.data?.detail || "Echec de l'enrichissement FIT")
    },
  })

  const disconnectMutation = useMutation({
    mutationFn: garminService.disconnectGarmin,
    onSuccess: () => {
      toast.success('Garmin deconnecte')
      queryClient.invalidateQueries({ queryKey: ['garmin-status'] })
      queryClient.invalidateQueries({ queryKey: ['garmin-daily-preview'] })
    },
    onError: (error: ApiError) => {
      toast.error(error.response?.data?.detail || 'Echec de la deconnexion')
    },
  })

  // --- Handlers ---

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault()
    if (!email || !password) return
    loginMutation.mutate()
  }

  // --- Render ---

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Status Card */}
      <div className="card">
        <div className="flex items-center">
          {isConnected ? (
            <CheckCircle className="h-8 w-8 text-green-500 flex-shrink-0" />
          ) : (
            <AlertCircle className="h-8 w-8 text-gray-400 flex-shrink-0" />
          )}
          <div className="ml-4">
            <h3 className="text-lg font-medium text-gray-900">
              {isConnected ? 'Garmin connecte' : 'Garmin non connecte'}
            </h3>
            <p className="text-sm text-gray-500">
              {isConnected
                ? `${garminStatus?.display_name || 'Compte connecte'} — Derniere sync : ${garminStatus?.last_sync_at ? formatDateShort(garminStatus.last_sync_at) : 'jamais'}`
                : 'Connectez votre compte Garmin pour synchroniser vos donnees'}
            </p>
          </div>
        </div>
      </div>

      {/* --- Non connecte : formulaire login --- */}
      {!isConnected && (
        <div className="card">
          <h3 className="text-lg font-medium text-gray-900 mb-4">
            Se connecter a Garmin
          </h3>

          <div className="bg-blue-50 border border-blue-200 rounded p-3 mb-4">
            <div className="flex items-start">
              <Shield className="h-4 w-4 text-blue-500 mt-0.5 mr-2 flex-shrink-0" />
              <p className="text-sm text-blue-800">
                <strong>Vos identifiants ne sont pas stockes.</strong> Ils sont utilises
                une seule fois pour generer un token d'acces securise (chiffre). Votre
                email et mot de passe ne transitent que lors de cette connexion.
              </p>
            </div>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label
                htmlFor="garmin-email"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Email Garmin
              </label>
              <input
                id="garmin-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                placeholder="votre@email.com"
                autoComplete="email"
              />
            </div>
            <div>
              <label
                htmlFor="garmin-password"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Mot de passe Garmin
              </label>
              <input
                id="garmin-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                placeholder="••••••••"
                autoComplete="current-password"
              />
            </div>
            <button
              type="submit"
              disabled={loginMutation.isPending || !email || !password}
              className="w-full btn-primary"
            >
              {loginMutation.isPending ? (
                <div className="flex items-center justify-center">
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Connexion en cours...
                </div>
              ) : (
                'Connecter Garmin'
              )}
            </button>
          </form>
        </div>
      )}

      {/* --- Connecte : sync + apercu + deconnexion --- */}
      {isConnected && (
        <>
          {/* Sync daily */}
          <div className="card">
            <h3 className="text-lg font-medium text-gray-900 mb-4">
              Synchronisation des donnees
            </h3>
            <div className="space-y-3">
              <div>
                <label
                  htmlFor="days-back"
                  className="block text-sm font-medium text-gray-600 mb-1"
                >
                  Periode de synchronisation
                </label>
                <select
                  id="days-back"
                  value={daysBack}
                  onChange={(e) => setDaysBack(Number(e.target.value))}
                  className="w-full text-sm border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                >
                  <option value={7}>7 derniers jours</option>
                  <option value={14}>14 derniers jours</option>
                  <option value={30}>30 derniers jours (recommande)</option>
                  <option value={60}>2 derniers mois</option>
                  <option value={90}>3 derniers mois</option>
                </select>
              </div>
              <button
                onClick={() => syncMutation.mutate()}
                disabled={syncMutation.isPending}
                className="w-full btn-primary"
              >
                {syncMutation.isPending ? (
                  <div className="flex items-center justify-center">
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    Synchronisation en cours...
                  </div>
                ) : (
                  <>
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Synchroniser ({daysBack} jours)
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Activites Garmin */}
          <div className="card">
            <h3 className="text-lg font-medium text-gray-900 mb-4">
              Activites Garmin
            </h3>
            <p className="text-sm text-gray-500 mb-4">
              Synchronisez vos activites Garmin et enrichissez-les avec les fichiers FIT
              (Running Dynamics, puissance, Training Effect).
            </p>
            <div className="space-y-3">
              <button
                onClick={() => syncActivitiesMutation.mutate()}
                disabled={syncActivitiesMutation.isPending}
                className="w-full btn-primary"
              >
                {syncActivitiesMutation.isPending ? (
                  <div className="flex items-center justify-center">
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    Synchronisation des activites...
                  </div>
                ) : (
                  <>
                    <Download className="h-4 w-4 mr-2" />
                    Synchroniser les activites ({daysBack} jours)
                  </>
                )}
              </button>
              <button
                onClick={() => batchEnrichMutation.mutate()}
                disabled={batchEnrichMutation.isPending}
                className="w-full px-4 py-2 text-sm bg-purple-600 text-white rounded-md hover:bg-purple-700 transition-colors disabled:opacity-50 flex items-center justify-center"
              >
                {batchEnrichMutation.isPending ? (
                  <div className="flex items-center justify-center">
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    Enrichissement FIT en cours...
                  </div>
                ) : (
                  <>
                    <Zap className="h-4 w-4 mr-2" />
                    Enrichir les fichiers FIT (max 10)
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Apercu 7 derniers jours */}
          <div className="card">
            <h3 className="text-lg font-medium text-gray-900 mb-4">
              Apercu — 7 derniers jours
            </h3>
            {dailyLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
                <span className="ml-2 text-gray-500">Chargement...</span>
              </div>
            ) : dailyData && dailyData.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-2 pr-3 text-gray-500 font-medium">
                        Date
                      </th>
                      <th className="text-center py-2 px-2 text-gray-500 font-medium">
                        <div
                          className="flex items-center justify-center"
                          title="HRV (RMSSD)"
                        >
                          <Heart className="h-3.5 w-3.5 mr-1 text-red-400" />
                          HRV
                        </div>
                      </th>
                      <th className="text-center py-2 px-2 text-gray-500 font-medium">
                        <div
                          className="flex items-center justify-center"
                          title="Training Readiness"
                        >
                          <Activity className="h-3.5 w-3.5 mr-1 text-green-500" />
                          Readiness
                        </div>
                      </th>
                      <th className="text-center py-2 px-2 text-gray-500 font-medium">
                        <div
                          className="flex items-center justify-center"
                          title="Sleep Score"
                        >
                          <Moon className="h-3.5 w-3.5 mr-1 text-indigo-400" />
                          Sommeil
                        </div>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {dailyData.map((day) => (
                      <tr
                        key={day.date}
                        className="border-b border-gray-100 last:border-0"
                      >
                        <td className="py-2 pr-3 text-gray-700">
                          {new Date(day.date).toLocaleDateString('fr-FR', {
                            weekday: 'short',
                            day: 'numeric',
                            month: 'short',
                          })}
                        </td>
                        <td className="text-center py-2 px-2">
                          {day.hrv_rmssd != null ? (
                            <span className="font-medium text-gray-900">
                              {Math.round(day.hrv_rmssd)}
                            </span>
                          ) : (
                            <span className="text-gray-300">—</span>
                          )}
                        </td>
                        <td className="text-center py-2 px-2">
                          {day.training_readiness != null ? (
                            <span
                              className={`font-medium ${
                                day.training_readiness >= 70
                                  ? 'text-green-600'
                                  : day.training_readiness >= 40
                                    ? 'text-yellow-600'
                                    : 'text-red-600'
                              }`}
                            >
                              {Math.round(day.training_readiness)}
                            </span>
                          ) : (
                            <span className="text-gray-300">—</span>
                          )}
                        </td>
                        <td className="text-center py-2 px-2">
                          {day.sleep_score != null ? (
                            <span
                              className={`font-medium ${
                                day.sleep_score >= 70
                                  ? 'text-indigo-600'
                                  : day.sleep_score >= 40
                                    ? 'text-yellow-600'
                                    : 'text-red-600'
                              }`}
                            >
                              {Math.round(day.sleep_score)}
                            </span>
                          ) : (
                            <span className="text-gray-300">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500">
                <Activity className="h-10 w-10 mx-auto mb-3 text-gray-300" />
                <p className="text-sm">
                  Aucune donnee disponible. Lancez une synchronisation.
                </p>
              </div>
            )}
          </div>

          {/* Deconnexion */}
          <div className="card">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-gray-900">
                  Deconnecter Garmin
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                  Supprime le token d'acces. Vos donnees deja synchronisees sont
                  conservees.
                </p>
              </div>
              <button
                onClick={() => disconnectMutation.mutate()}
                disabled={disconnectMutation.isPending}
                className="px-3 py-1.5 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors disabled:opacity-50"
              >
                {disconnectMutation.isPending ? (
                  <div className="flex items-center">
                    <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                    Deconnexion...
                  </div>
                ) : (
                  <div className="flex items-center">
                    <LogOut className="h-3.5 w-3.5 mr-1" />
                    Deconnecter
                  </div>
                )}
              </button>
            </div>
          </div>
        </>
      )}

      {/* Info securite */}
      <div className="card">
        <h3 className="text-lg font-medium text-gray-900 mb-3">
          A propos de la connexion Garmin
        </h3>
        <div className="space-y-2 text-sm text-gray-600">
          <div className="flex items-start">
            <Shield className="h-4 w-4 text-green-500 mt-0.5 mr-3 flex-shrink-0" />
            <p>
              <strong>Securite :</strong> Votre email et mot de passe Garmin ne sont
              jamais stockes. Seul un token d'acces chiffre (AES-256) est conserve.
            </p>
          </div>
          <div className="flex items-start">
            <RefreshCw className="h-4 w-4 text-blue-500 mt-0.5 mr-3 flex-shrink-0" />
            <p>
              <strong>Donnees synchronisees :</strong> HRV, Training Readiness, sommeil,
              stress, frequence cardiaque au repos, SpO2, Body Battery.
            </p>
          </div>
          <div className="flex items-start">
            <div className="w-2 h-2 bg-primary-500 rounded-full mt-2 mr-3 flex-shrink-0"></div>
            <p>
              <strong>Frequence :</strong> Synchronisez apres chaque nuit pour avoir les
              dernieres donnees de recuperation.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
