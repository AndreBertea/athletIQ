import { useState } from 'react'
import { X, AlertTriangle, Trash2, Shield } from 'lucide-react'

interface ConfirmationModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  message: string
  confirmText: string
  confirmationPhrase?: string
  dangerLevel: 'low' | 'medium' | 'high'
  isLoading?: boolean
}

export default function ConfirmationModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmText,
  confirmationPhrase,
  dangerLevel,
  isLoading = false
}: ConfirmationModalProps) {
  const [typedPhrase, setTypedPhrase] = useState('')

  if (!isOpen) return null

  const isConfirmationValid = !confirmationPhrase || typedPhrase === confirmationPhrase

  const getDangerStyles = () => {
    switch (dangerLevel) {
      case 'low':
        return {
          icon: Shield,
          iconColor: 'text-blue-600',
          bgColor: 'bg-blue-50',
          borderColor: 'border-blue-200',
          buttonColor: 'bg-blue-600 hover:bg-blue-700'
        }
      case 'medium':
        return {
          icon: AlertTriangle,
          iconColor: 'text-orange-600',
          bgColor: 'bg-orange-50',
          borderColor: 'border-orange-200',
          buttonColor: 'bg-orange-600 hover:bg-orange-700'
        }
      case 'high':
        return {
          icon: Trash2,
          iconColor: 'text-red-600',
          bgColor: 'bg-red-50',
          borderColor: 'border-red-200',
          buttonColor: 'bg-red-600 hover:bg-red-700'
        }
    }
  }

  const styles = getDangerStyles()
  const IconComponent = styles.icon

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg max-w-md w-full mx-4 shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b">
          <div className="flex items-center">
            <div className={`p-2 rounded-full ${styles.bgColor} ${styles.borderColor} border`}>
              <IconComponent className={`h-6 w-6 ${styles.iconColor}`} />
            </div>
            <h3 className="ml-3 text-lg font-semibold text-gray-900">
              {title}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            disabled={isLoading}
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          <p className="text-gray-700 mb-4">{message}</p>

          {confirmationPhrase && (
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Pour confirmer, tapez <span className="font-mono bg-gray-100 px-1 rounded">{confirmationPhrase}</span>
              </label>
              <input
                type="text"
                value={typedPhrase}
                onChange={(e) => setTypedPhrase(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder={confirmationPhrase}
                disabled={isLoading}
              />
            </div>
          )}

          {dangerLevel === 'high' && (
            <div className={`p-3 rounded-md ${styles.bgColor} ${styles.borderColor} border mb-4`}>
              <div className="flex">
                <AlertTriangle className={`h-5 w-5 ${styles.iconColor} mt-0.5`} />
                <div className="ml-3">
                  <h4 className="text-sm font-medium text-red-800">
                    Cette action est irréversible
                  </h4>
                  <p className="text-sm text-red-700 mt-1">
                    Toutes vos données seront définitivement supprimées et ne pourront pas être récupérées.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex justify-end space-x-3 px-6 py-4 bg-gray-50 rounded-b-lg">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
            disabled={isLoading}
          >
            Annuler
          </button>
          <button
            onClick={onConfirm}
            disabled={!isConfirmationValid || isLoading}
            className={`px-4 py-2 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${styles.buttonColor}`}
          >
            {isLoading ? (
              <div className="flex items-center">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                Traitement...
              </div>
            ) : (
              confirmText
            )}
          </button>
        </div>
      </div>
    </div>
  )
} 