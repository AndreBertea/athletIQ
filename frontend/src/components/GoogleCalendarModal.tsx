import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { XCircle, Calendar, Upload, Download, Loader2, CheckCircle, AlertCircle, Link } from 'lucide-react'

import { googleCalendarService, type GoogleCalendar } from '../services/googleCalendarService'

interface GoogleCalendarModalProps {
  isOpen: boolean
  onClose: () => void
}

export default function GoogleCalendarModal({ isOpen, onClose }: GoogleCalendarModalProps) {
  const [selectedCalendar, setSelectedCalendar] = useState<string>('primary')
  const [startDate, setStartDate] = useState<string>('')
  const [endDate, setEndDate] = useState<string>('')
  const [operation, setOperation] = useState<'export' | 'import' | null>(null)

  const queryClient = useQueryClient()
  const navigate = useNavigate()

  // Récupérer la liste des calendriers avec refresh automatique
  const { data: calendars = [], isLoading: isLoadingCalendars, error: calendarsError, refetch: refetchCalendars } = useQuery({
    queryKey: ['google-calendars'],
    queryFn: async () => {
      try {
        return await googleCalendarService.getGoogleCalendars()
      } catch (error: any) {
        // Si l'erreur indique un token expiré, essayer de le rafraîchir
        if (error.response?.status === 401 && error.response?.data?.detail?.includes('expiré')) {
          console.log('Token expiré, tentative de refresh automatique...')
          try {
            await googleCalendarService.refreshGoogleToken()
            // Retenter la récupération des calendriers
            return await googleCalendarService.getGoogleCalendars()
          } catch (refreshError) {
            console.error('Erreur lors du refresh automatique:', refreshError)
            throw refreshError
          }
        }
        throw error
      }
    },
    enabled: isOpen,
    retry: 1
  })

  // Mutation pour l'export
  const exportMutation = useMutation({
    mutationFn: (calendarId: string) => googleCalendarService.exportWorkoutPlansToGoogle(calendarId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workout-plans'] })
      setOperation(null)
    }
  })

  // Mutation pour l'import
  const importMutation = useMutation({
    mutationFn: ({ calendarId, startDate, endDate }: { calendarId: string; startDate?: string; endDate?: string }) =>
      googleCalendarService.importGoogleCalendarAsWorkoutPlans(calendarId, startDate, endDate),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workout-plans'] })
      setOperation(null)
    }
  })

  // Gérer l'export
  const handleExport = () => {
    setOperation('export')
    exportMutation.mutate(selectedCalendar)
  }

  // Gérer l'import
  const handleImport = () => {
    setOperation('import')
    importMutation.mutate({
      calendarId: selectedCalendar,
      startDate: startDate || undefined,
      endDate: endDate || undefined
    })
  }

  // Fermer le modal
  const handleClose = () => {
    setOperation(null)
    setSelectedCalendar('primary')
    setStartDate('')
    setEndDate('')
    onClose()
  }

  // Rediriger vers la page de connexion Google
  const handleConnect = () => {
    // Sauvegarder la page actuelle pour y revenir après connexion
    sessionStorage.setItem('googleCalendarReturnUrl', window.location.pathname)
    navigate('/google-connect')
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center">
            <Calendar className="h-6 w-6 text-blue-600 mr-2" />
            <h2 className="text-xl font-semibold text-gray-900">
              Synchronisation Google Calendar
            </h2>
          </div>
          <div className="flex gap-2">
            <button
              onClick={async () => {
                try {
                  await googleCalendarService.refreshGoogleToken()
                  refetchCalendars()
                } catch (error) {
                  console.error('Erreur lors du refresh manuel:', error)
                }
              }}
              className="inline-flex items-center px-3 py-2 bg-green-600 text-white text-sm rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500"
            >
              <svg className="h-4 w-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Rafraîchir
            </button>
            <button
              onClick={handleConnect}
              className="inline-flex items-center px-3 py-2 bg-blue-600 text-white text-sm rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <Link className="h-4 w-4 mr-1" />
              Connexion
            </button>
          </div>
        </div>

        {/* Sélection du calendrier */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Calendrier Google
          </label>
          {isLoadingCalendars ? (
            <div className="flex items-center p-3 border border-gray-300 rounded-md">
              <Loader2 className="h-4 w-4 animate-spin text-gray-500 mr-2" />
              <span className="text-gray-600">Chargement des calendriers...</span>
            </div>
          ) : (
            <select
              value={selectedCalendar}
              onChange={(e) => setSelectedCalendar(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
            >
              {calendars.map((calendar) => (
                <option key={calendar.id} value={calendar.id}>
                  {calendar.summary} {calendar.primary ? '(Principal)' : ''}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Section Export */}
        <div className="mb-6 p-4 border border-gray-200 rounded-lg">
          <div className="flex items-center mb-3">
            <Download className="h-5 w-5 text-green-600 mr-2" />
            <h3 className="text-lg font-medium text-gray-900">Exporter vers Google Calendar</h3>
          </div>
          <p className="text-sm text-gray-600 mb-4">
            Exportez vos plans d'entraînement actuels vers votre calendrier Google sélectionné.
          </p>
          
          {exportMutation.isPending ? (
            <div className="flex items-center p-3 bg-blue-50 rounded-md">
              <Loader2 className="h-4 w-4 animate-spin text-blue-500 mr-2" />
              <span className="text-blue-700">Export en cours...</span>
            </div>
          ) : exportMutation.isSuccess ? (
            <div className="flex items-center p-3 bg-green-50 rounded-md">
              <CheckCircle className="h-4 w-4 text-green-500 mr-2" />
              <div>
                <p className="text-green-700 font-medium">Export réussi !</p>
                <p className="text-green-600 text-sm">
                  {exportMutation.data?.exported_count} plans exportés sur {exportMutation.data?.total_count}
                </p>
              </div>
            </div>
          ) : exportMutation.isError ? (
            <div className="flex items-center p-3 bg-red-50 rounded-md">
              <AlertCircle className="h-4 w-4 text-red-500 mr-2" />
              <span className="text-red-700">Erreur lors de l'export</span>
            </div>
          ) : (
            <button
              onClick={handleExport}
              className="w-full bg-green-600 text-white px-4 py-2 rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500"
            >
              Exporter les plans d'entraînement
            </button>
          )}
        </div>

        {/* Section Import */}
        <div className="mb-6 p-4 border border-gray-200 rounded-lg">
          <div className="flex items-center mb-3">
            <Upload className="h-5 w-5 text-blue-600 mr-2" />
            <h3 className="text-lg font-medium text-gray-900">Importer depuis Google Calendar</h3>
          </div>
          <p className="text-sm text-gray-600 mb-4">
            Importez les événements de votre calendrier Google comme nouveaux plans d'entraînement.
          </p>

          {/* Dates optionnelles */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Date de début (optionnel)
              </label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Date de fin (optionnel)
              </label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
          </div>

          {importMutation.isPending ? (
            <div className="flex items-center p-3 bg-blue-50 rounded-md">
              <Loader2 className="h-4 w-4 animate-spin text-blue-500 mr-2" />
              <span className="text-blue-700">Import en cours...</span>
            </div>
          ) : importMutation.isSuccess ? (
            <div className="flex items-center p-3 bg-green-50 rounded-md">
              <CheckCircle className="h-4 w-4 text-green-500 mr-2" />
              <div>
                <p className="text-green-700 font-medium">Import réussi !</p>
                <p className="text-green-600 text-sm">
                  {importMutation.data?.imported_count} plans importés sur {importMutation.data?.total_count} événements
                </p>
              </div>
            </div>
          ) : importMutation.isError ? (
            <div className="flex items-center p-3 bg-red-50 rounded-md">
              <AlertCircle className="h-4 w-4 text-red-500 mr-2" />
              <span className="text-red-700">Erreur lors de l'import</span>
            </div>
          ) : (
            <button
              onClick={handleImport}
              className="w-full bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              Importer depuis le calendrier
            </button>
          )}
        </div>

        {/* Informations */}
        <div className="bg-gray-50 p-4 rounded-lg">
          <h4 className="text-sm font-medium text-gray-900 mb-2">Informations</h4>
          <ul className="text-sm text-gray-600 space-y-1">
            <li>• L'export crée des événements dans votre calendrier Google</li>
            <li>• L'import détecte automatiquement les événements d'entraînement</li>
            <li>• Les événements existants ne seront pas dupliqués</li>
            <li>• Seuls les événements avec des mots-clés d'entraînement seront importés</li>
          </ul>
        </div>

        {/* Boutons de fermeture */}
        <div className="flex justify-end space-x-3 pt-6">
          <button
            onClick={handleClose}
            className="px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
          >
            Fermer
          </button>
        </div>
      </div>
    </div>
  )
} 