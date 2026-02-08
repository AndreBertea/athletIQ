import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { User, FileDown, Database, Trash2, Shield } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import { authService } from '../../services/authService'
import type { ApiError } from '../../services/activityService'
import { useToast } from '../../contexts/ToastContext'
import ConfirmationModal from '../ConfirmationModal'

type ModalType = 'export' | 'delete-strava' | 'delete-all' | 'delete-account' | null

export default function AccountSection() {
  const { user } = useAuth()
  const toast = useToast()
  const queryClient = useQueryClient()
  const [confirmationModal, setConfirmationModal] = useState<{
    isOpen: boolean
    type: ModalType
  }>({ isOpen: false, type: null })

  // --- Mutations ---

  const exportDataMutation = useMutation({
    mutationFn: () => authService.exportUserData(),
    onSuccess: (blob) => {
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `athletiq-export-${new Date().toISOString().split('T')[0]}.json`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      toast.success('Export des donnees telecharge avec succes')
      closeModal()
    },
    onError: (error: ApiError) => {
      toast.error(error.response?.data?.detail || 'Echec de l\'export')
    },
  })

  const deleteStravaMutation = useMutation({
    mutationFn: () => authService.deleteStravaData(),
    onSuccess: (data) => {
      toast.success(`Donnees Strava supprimees: ${data.deleted_activities} activites supprimees`)
      queryClient.invalidateQueries({ queryKey: ['strava-status'] })
      queryClient.invalidateQueries({ queryKey: ['activities'] })
      closeModal()
    },
    onError: (error: ApiError) => {
      toast.error(error.response?.data?.detail || 'Echec de la suppression')
    },
  })

  const deleteAllDataMutation = useMutation({
    mutationFn: () => authService.deleteAllUserData(),
    onSuccess: (data) => {
      toast.success(
        `Toutes les donnees supprimees: ${data.deleted_activities} activites, ${data.deleted_workout_plans} plans d'entrainement`
      )
      queryClient.invalidateQueries({ queryKey: ['strava-status'] })
      queryClient.invalidateQueries({ queryKey: ['activities'] })
      queryClient.invalidateQueries({ queryKey: ['workout-plans'] })
      closeModal()
    },
    onError: (error: ApiError) => {
      toast.error(error.response?.data?.detail || 'Echec de la suppression')
    },
  })

  const deleteAccountMutation = useMutation({
    mutationFn: () => authService.deleteAccount(),
    onSuccess: async () => {
      try {
        await authService.logout()
      } catch {
        /* ignore */
      }
      window.location.href = '/'
    },
    onError: (error: ApiError) => {
      toast.error(error.response?.data?.detail || 'Echec de la suppression du compte')
    },
  })

  // --- Handlers ---

  const openModal = (type: ModalType) => {
    setConfirmationModal({ isOpen: true, type })
  }

  const closeModal = () => {
    setConfirmationModal({ isOpen: false, type: null })
  }

  const handleConfirmAction = () => {
    switch (confirmationModal.type) {
      case 'export':
        exportDataMutation.mutate()
        break
      case 'delete-strava':
        deleteStravaMutation.mutate()
        break
      case 'delete-all':
        deleteAllDataMutation.mutate()
        break
      case 'delete-account':
        deleteAccountMutation.mutate()
        break
    }
  }

  const getModalProps = () => {
    switch (confirmationModal.type) {
      case 'export':
        return {
          title: 'Exporter mes donnees',
          message:
            'Cette action telechargera toutes vos donnees personnelles au format JSON. Le fichier contiendra vos informations de profil, activites et plans d\'entrainement.',
          confirmText: 'Telecharger mes donnees',
          dangerLevel: 'low' as const,
          isLoading: exportDataMutation.isPending,
        }
      case 'delete-strava':
        return {
          title: 'Supprimer les donnees Strava',
          message:
            'Cette action supprimera toutes vos donnees importees de Strava (activites et authentification). Vous pourrez vous reconnecter a Strava plus tard si vous le souhaitez.',
          confirmText: 'Supprimer les donnees Strava',
          dangerLevel: 'medium' as const,
          isLoading: deleteStravaMutation.isPending,
        }
      case 'delete-all':
        return {
          title: 'Supprimer toutes mes donnees',
          message:
            'Cette action supprimera TOUTES vos donnees (activites, plans d\'entrainement, connexion Strava) mais conservera votre compte. Vous pourrez creer de nouvelles donnees apres.',
          confirmText: 'Supprimer toutes les donnees',
          confirmationPhrase: 'SUPPRIMER',
          dangerLevel: 'high' as const,
          isLoading: deleteAllDataMutation.isPending,
        }
      case 'delete-account':
        return {
          title: 'Supprimer mon compte',
          message:
            'Cette action supprimera definitivement votre compte et TOUTES vos donnees associees. Vous serez deconnecte et ne pourrez plus acceder a athletIQ avec ce compte.',
          confirmText: 'Supprimer le compte',
          confirmationPhrase: 'SUPPRIMER MON COMPTE',
          dangerLevel: 'high' as const,
          isLoading: deleteAccountMutation.isPending,
        }
      default:
        return {
          title: '',
          message: '',
          confirmText: '',
          dangerLevel: 'low' as const,
          isLoading: false,
        }
    }
  }

  // --- Render ---

  return (
    <div className="space-y-6">
      {/* Informations utilisateur */}
      <div className="card">
        <div className="flex items-center mb-4">
          <div className="p-2 bg-blue-100 rounded-full">
            <User className="h-6 w-6 text-blue-600" />
          </div>
          <h3 className="ml-3 text-lg font-medium text-gray-900">Informations du compte</h3>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between py-2 border-b border-gray-100">
            <span className="text-sm text-gray-500">Nom</span>
            <span className="text-sm font-medium text-gray-900">{user?.full_name || '—'}</span>
          </div>
          <div className="flex items-center justify-between py-2 border-b border-gray-100">
            <span className="text-sm text-gray-500">Email</span>
            <span className="text-sm font-medium text-gray-900">{user?.email || '—'}</span>
          </div>
          <div className="flex items-center justify-between py-2">
            <span className="text-sm text-gray-500">Membre depuis</span>
            <span className="text-sm font-medium text-gray-900">
              {user?.created_at
                ? new Date(user.created_at).toLocaleDateString('fr-FR', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                  })
                : '—'}
            </span>
          </div>
        </div>
      </div>

      {/* Gestion des donnees (RGPD) */}
      <div className="card">
        <div className="flex items-center mb-4">
          <div className="p-2 bg-blue-100 rounded-full">
            <Shield className="h-6 w-6 text-blue-600" />
          </div>
          <h3 className="ml-3 text-lg font-medium text-gray-900">
            Gestion de vos donnees personnelles (RGPD)
          </h3>
        </div>

        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            Conformement au Reglement General sur la Protection des Donnees (RGPD), vous avez le
            controle total sur vos donnees personnelles stockees dans athletIQ.
          </p>

          {/* Export */}
          <div className="border border-gray-200 rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-start">
                <FileDown className="h-5 w-5 text-blue-500 mt-1" />
                <div className="ml-3">
                  <h4 className="text-sm font-medium text-gray-900">Exporter mes donnees</h4>
                  <p className="text-sm text-gray-600 mt-1">
                    Telechargez toutes vos donnees personnelles au format JSON
                  </p>
                </div>
              </div>
              <button
                onClick={() => openModal('export')}
                disabled={exportDataMutation.isPending}
                className="btn-secondary text-sm"
              >
                <FileDown className="h-4 w-4 mr-2" />
                Exporter
              </button>
            </div>
          </div>

          {/* Supprimer donnees Strava */}
          <div className="border border-orange-200 rounded-lg p-4 bg-orange-50">
            <div className="flex items-center justify-between">
              <div className="flex items-start">
                <Database className="h-5 w-5 text-orange-500 mt-1" />
                <div className="ml-3">
                  <h4 className="text-sm font-medium text-gray-900">
                    Supprimer les donnees Strava
                  </h4>
                  <p className="text-sm text-gray-600 mt-1">
                    Supprime uniquement vos donnees importees de Strava
                  </p>
                </div>
              </div>
              <button
                onClick={() => openModal('delete-strava')}
                disabled={deleteStravaMutation.isPending}
                className="px-3 py-1.5 text-sm bg-orange-600 text-white rounded-md hover:bg-orange-700 transition-colors"
              >
                Supprimer
              </button>
            </div>
          </div>

          {/* Supprimer toutes les donnees */}
          <div className="border border-red-200 rounded-lg p-4 bg-red-50">
            <div className="flex items-center justify-between">
              <div className="flex items-start">
                <Trash2 className="h-5 w-5 text-red-500 mt-1" />
                <div className="ml-3">
                  <h4 className="text-sm font-medium text-gray-900">
                    Supprimer toutes mes donnees
                  </h4>
                  <p className="text-sm text-gray-600 mt-1">
                    Supprime toutes vos donnees mais conserve votre compte
                  </p>
                </div>
              </div>
              <button
                onClick={() => openModal('delete-all')}
                disabled={deleteAllDataMutation.isPending}
                className="px-3 py-1.5 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors"
              >
                Supprimer
              </button>
            </div>
          </div>

          {/* Supprimer le compte */}
          <div className="border border-red-300 rounded-lg p-4 bg-red-100">
            <div className="flex items-center justify-between">
              <div className="flex items-start">
                <Trash2 className="h-5 w-5 text-red-600 mt-1" />
                <div className="ml-3">
                  <h4 className="text-sm font-medium text-gray-900">Supprimer mon compte</h4>
                  <p className="text-sm text-gray-600 mt-1">
                    Supprime definitivement votre compte et toutes vos donnees
                  </p>
                </div>
              </div>
              <button
                onClick={() => openModal('delete-account')}
                disabled={deleteAccountMutation.isPending}
                className="px-3 py-1.5 text-sm bg-red-700 text-white rounded-md hover:bg-red-800 transition-colors"
              >
                Supprimer
              </button>
            </div>
          </div>

          <div className="text-xs text-gray-500 bg-gray-50 p-3 rounded-md">
            <p>
              <strong>Important :</strong> Ces actions sont conformes au RGPD (Reglement General sur
              la Protection des Donnees). La suppression des donnees est irreversible. Nous vous
              recommandons d'exporter vos donnees avant toute suppression.
            </p>
          </div>
        </div>
      </div>

      {/* Modal de confirmation */}
      <ConfirmationModal
        isOpen={confirmationModal.isOpen}
        onClose={closeModal}
        onConfirm={handleConfirmAction}
        {...getModalProps()}
      />
    </div>
  )
}
