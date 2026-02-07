import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Calendar, CheckCircle, XCircle, AlertCircle, Loader2 } from 'lucide-react'

import { googleCalendarService, type GoogleAuthStatus } from '../services/googleCalendarService'
import { useToast } from '../contexts/ToastContext'

export default function GoogleConnect() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [isConnecting, setIsConnecting] = useState(false)
  const toast = useToast()

  // Récupérer les paramètres de l'URL
  const success = searchParams.get('success')
  const error = searchParams.get('error')
  const message = searchParams.get('message')
  const googleUserId = searchParams.get('google_user_id')

  // Vérifier le statut de la connexion Google
  const { data: googleStatus, isLoading: isLoadingStatus } = useQuery({
    queryKey: ['google-status'],
    queryFn: googleCalendarService.getGoogleStatus,
    retry: false
  })

  // Gérer la connexion Google
  const handleGoogleConnect = async () => {
    setIsConnecting(true)
    try {
      console.log('Début de la connexion Google...')
      const { authorization_url } = await googleCalendarService.initiateGoogleLogin()
      console.log('URL d\'autorisation reçue:', authorization_url)
      
      if (!authorization_url) {
        throw new Error('URL d\'autorisation manquante')
      }
      
      // Rediriger vers l'URL d'autorisation Google
      window.location.href = authorization_url
    } catch (error: any) {
      console.error('Erreur lors de l\'initiation de la connexion Google:', error)
      toast.error(`Erreur de connexion Google: ${error.message || 'Erreur inconnue'}`)
      setIsConnecting(false)
    }
  }

  // Rediriger vers la page précédente après connexion réussie
  useEffect(() => {
    if (success === 'true' && googleUserId) {
      const timer = setTimeout(() => {
        // Récupérer l'URL de retour sauvegardée ou aller aux plans d'entraînement par défaut
        const returnUrl = sessionStorage.getItem('googleCalendarReturnUrl') || '/workout-plans'
        sessionStorage.removeItem('googleCalendarReturnUrl') // Nettoyer
        navigate(returnUrl)
      }, 3000)
      return () => clearTimeout(timer)
    }
  }, [success, googleUserId, navigate])

  // Afficher les messages d'erreur
  const renderError = () => {
    if (!error) return null

    const errorMessages: Record<string, string> = {
      oauth_error: 'Erreur lors de l\'authentification Google',
      no_code: 'Code d\'autorisation manquant',
      no_state: 'Paramètre d\'état manquant',
      invalid_state: 'Identifiant d\'état invalide',
      user_not_found: 'Utilisateur non trouvé',
      callback_error: 'Erreur lors du traitement de l\'authentification'
    }

    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
        <div className="flex items-center">
          <XCircle className="h-5 w-5 text-red-500 mr-2" />
          <h3 className="text-red-800 font-medium">Erreur de connexion</h3>
        </div>
        <p className="text-red-700 mt-1">
          {errorMessages[error] || message || 'Une erreur inconnue s\'est produite'}
        </p>
      </div>
    )
  }

  // Afficher le message de succès
  const renderSuccess = () => {
    if (success !== 'true') return null

    return (
      <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
        <div className="flex items-center">
          <CheckCircle className="h-5 w-5 text-green-500 mr-2" />
          <h3 className="text-green-800 font-medium">Connexion réussie !</h3>
        </div>
        <p className="text-green-700 mt-1">
          Votre compte Google Calendar a été connecté avec succès.
          {googleUserId && (
            <span className="block mt-1">
              ID utilisateur Google : {googleUserId}
            </span>
          )}
        </p>
        <p className="text-green-600 text-sm mt-2">
          Redirection vers la page précédente dans quelques secondes...
        </p>
      </div>
    )
  }

  // Afficher le statut actuel
  const renderCurrentStatus = () => {
    if (isLoadingStatus) {
      return (
        <div className="flex items-center justify-center p-8">
          <Loader2 className="h-6 w-6 animate-spin text-gray-500" />
          <span className="ml-2 text-gray-600">Vérification du statut...</span>
        </div>
      )
    }

    if (googleStatus?.connected) {
      return (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
          <div className="flex items-center">
            <CheckCircle className="h-5 w-5 text-blue-500 mr-2" />
            <h3 className="text-blue-800 font-medium">Déjà connecté</h3>
          </div>
          <p className="text-blue-700 mt-1">
            Votre compte Google Calendar est déjà connecté.
            {googleStatus.google_user_id && (
              <span className="block mt-1">
                ID utilisateur Google : {googleStatus.google_user_id}
              </span>
            )}
          </p>
          <div className="mt-4">
            <button
              onClick={() => {
                const returnUrl = sessionStorage.getItem('googleCalendarReturnUrl') || '/workout-plans'
                sessionStorage.removeItem('googleCalendarReturnUrl')
                navigate(returnUrl)
              }}
              className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors"
            >
              Retourner à la page précédente
            </button>
          </div>
        </div>
      )
    }

    return null
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
          <Calendar className="h-12 w-12 text-blue-600" />
        </div>
        <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
          Connexion Google Calendar
        </h2>
        <p className="mt-2 text-center text-sm text-gray-600">
          Connectez votre compte Google Calendar pour synchroniser vos plans d'entraînement
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10">
          {/* Messages d'erreur et de succès */}
          {renderError()}
          {renderSuccess()}
          {renderCurrentStatus()}

          {/* Formulaire de connexion */}
          {!googleStatus?.connected && !success && (
            <div className="space-y-6">
              <div className="text-center">
                <AlertCircle className="mx-auto h-12 w-12 text-gray-400" />
                <h3 className="mt-2 text-sm font-medium text-gray-900">
                  Connexion requise
                </h3>
                <p className="mt-1 text-sm text-gray-500">
                  Pour utiliser les fonctionnalités Google Calendar, vous devez d'abord connecter votre compte.
                </p>
              </div>

              <div className="space-y-4">
                <div className="bg-gray-50 p-4 rounded-lg">
                  <h4 className="text-sm font-medium text-gray-900 mb-2">
                    Permissions demandées :
                  </h4>
                  <ul className="text-sm text-gray-600 space-y-1">
                    <li>• Lire vos calendriers Google</li>
                    <li>• Créer et modifier des événements</li>
                    <li>• Accéder à vos informations de profil de base</li>
                  </ul>
                </div>

                <button
                  onClick={handleGoogleConnect}
                  disabled={isConnecting}
                  className="w-full flex justify-center items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isConnecting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin mr-2" />
                      Connexion en cours...
                    </>
                  ) : (
                    <>
                      <svg className="h-4 w-4 mr-2" viewBox="0 0 24 24">
                        <path
                          fill="currentColor"
                          d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                        />
                        <path
                          fill="currentColor"
                          d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                        />
                        <path
                          fill="currentColor"
                          d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                        />
                        <path
                          fill="currentColor"
                          d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                        />
                      </svg>
                      Se connecter avec Google
                    </>
                  )}
                </button>

                <div className="text-center">
                  <button
                    onClick={() => {
                      const returnUrl = sessionStorage.getItem('googleCalendarReturnUrl') || '/workout-plans'
                      sessionStorage.removeItem('googleCalendarReturnUrl')
                      navigate(returnUrl)
                    }}
                    className="text-sm text-gray-500 hover:text-gray-700"
                  >
                    Retourner à la page précédente
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
} 