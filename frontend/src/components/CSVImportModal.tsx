import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, CheckCircle, XCircle } from 'lucide-react'
import { workoutPlanService } from '../services/workoutPlanService'

interface CSVImportModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
}

export default function CSVImportModal({ isOpen, onClose, onSuccess }: CSVImportModalProps) {
  const [isUploading, setIsUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState<{
    success: boolean
    message: string
    imported_count: number
    total_count: number
    errors: string[]
  } | null>(null)

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return

    const file = acceptedFiles[0]
    setIsUploading(true)
    setUploadResult(null)

    try {
      const result = await workoutPlanService.importFromCSV(file)
      setUploadResult(result)
      
      if (result.success) {
        // Attendre un peu avant de fermer le modal
        setTimeout(() => {
          onSuccess()
          onClose()
        }, 2000)
      }
    } catch (error: any) {
      setUploadResult({
        success: false,
        message: error.response?.data?.detail || 'Erreur lors de l\'import',
        imported_count: 0,
        total_count: 0,
        errors: []
      })
    } finally {
      setIsUploading(false)
    }
  }, [onSuccess, onClose])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/csv': ['.csv'],
      'application/vnd.ms-excel': ['.csv']
    },
    multiple: false
  })

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-full max-w-md mx-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-900">Importer un plan CSV</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            <XCircle className="h-6 w-6" />
          </button>
        </div>

        {!uploadResult ? (
          <div>
            <div className="mb-4">
              <p className="text-sm text-gray-600 mb-2">
                Glissez-déposez votre fichier CSV ou cliquez pour sélectionner
              </p>
              <p className="text-xs text-gray-500">
                Format attendu : phase, Semaine, Date, Type, Km, D+ (m), notes du coach, allure, zone d'intensité, durée, description, rpe
              </p>
            </div>

            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
                isDragActive
                  ? 'border-primary-400 bg-primary-50'
                  : 'border-gray-300 hover:border-primary-400'
              }`}
            >
              <input {...getInputProps()} />
              {isUploading ? (
                <div className="flex flex-col items-center">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mb-2"></div>
                  <p className="text-sm text-gray-600">Import en cours...</p>
                </div>
              ) : (
                <div className="flex flex-col items-center">
                  <Upload className="h-8 w-8 text-gray-400 mb-2" />
                  <p className="text-sm text-gray-600">
                    {isDragActive ? 'Déposez le fichier ici' : 'Glissez-déposez un fichier CSV'}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">ou cliquez pour sélectionner</p>
                </div>
              )}
            </div>

            <div className="mt-4 p-3 bg-blue-50 rounded-lg">
              <h4 className="font-medium text-blue-900 mb-2">Format CSV attendu :</h4>
              <div className="text-xs text-blue-800 space-y-1">
                <p><strong>phase</strong> : base 1, base 2, build, peak, affu</p>
                <p><strong>Semaine</strong> : numéro de semaine</p>
                <p><strong>Date</strong> : DD/MM/YYYY</p>
                <p><strong>Type</strong> : trail, vma, seuil, ef, spécifique, etc.</p>
                <p><strong>Km</strong> : distance en kilomètres</p>
                <p><strong>D+ (m)</strong> : dénivelé positif en mètres</p>
                <p><strong>notes du coach</strong> : instructions détaillées</p>
                <p><strong>allure</strong> : pace en min/km</p>
                <p><strong>zone d'intensité</strong> : zone 1-5</p>
                <p><strong>durée</strong> : temps en secondes</p>
                <p><strong>description</strong> : description du parcours</p>
                <p><strong>rpe</strong> : Rate of Perceived Exertion (1-10)</p>
              </div>
            </div>
          </div>
        ) : (
          <div className="text-center">
            {uploadResult.success ? (
              <div className="flex flex-col items-center">
                <CheckCircle className="h-12 w-12 text-green-500 mb-4" />
                <h3 className="text-lg font-medium text-green-900 mb-2">
                  Import réussi !
                </h3>
                <p className="text-sm text-green-700 mb-4">
                  {uploadResult.imported_count} plans importés sur {uploadResult.total_count}
                </p>
                {uploadResult.errors.length > 0 && (
                  <div className="w-full">
                    <p className="text-sm text-orange-700 mb-2">
                      {uploadResult.errors.length} erreur(s) rencontrée(s) :
                    </p>
                    <div className="max-h-32 overflow-y-auto text-xs text-orange-600">
                      {uploadResult.errors.map((error, index) => (
                        <p key={index} className="mb-1">• {error}</p>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center">
                <XCircle className="h-12 w-12 text-red-500 mb-4" />
                <h3 className="text-lg font-medium text-red-900 mb-2">
                  Échec de l'import
                </h3>
                <p className="text-sm text-red-700 mb-4">
                  {uploadResult.message}
                </p>
                {uploadResult.errors.length > 0 && (
                  <div className="w-full">
                    <p className="text-sm text-red-700 mb-2">Erreurs :</p>
                    <div className="max-h-32 overflow-y-auto text-xs text-red-600">
                      {uploadResult.errors.map((error, index) => (
                        <p key={index} className="mb-1">• {error}</p>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="mt-6 flex justify-center space-x-3">
              <button
                onClick={onClose}
                className="px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
              >
                Fermer
              </button>
              {!uploadResult.success && (
                <button
                  onClick={() => setUploadResult(null)}
                  className="px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700"
                >
                  Réessayer
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
} 