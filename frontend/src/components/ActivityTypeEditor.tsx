import React, { useState } from 'react'
import { Edit3, Save, X, Check, AlertCircle } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'

interface ActivityTypeEditorProps {
  activity: any
  onSave?: () => void
  onCancel?: () => void
}

const SPORT_TYPES = [
  { value: 'Run', label: 'Course à pied', emoji: '🏃‍♂️' },
  { value: 'TrailRun', label: 'Trail Running', emoji: '🥾' },
  { value: 'Ride', label: 'Vélo', emoji: '🚴‍♂️' },
  { value: 'Swim', label: 'Natation', emoji: '🏊‍♂️' },
  { value: 'Walk', label: 'Marche', emoji: '🚶‍♂️' },
  { value: 'RacketSport', label: 'Sport de raquette', emoji: '🎾' },
  { value: 'Tennis', label: 'Tennis', emoji: '🎾' },
  { value: 'Badminton', label: 'Badminton', emoji: '🏸' },
  { value: 'Squash', label: 'Squash', emoji: '🏓' },
  { value: 'Padel', label: 'Padel', emoji: '🏓' },
  { value: 'WeightTraining', label: 'Musculation', emoji: '🏋️‍♂️' },
  { value: 'RockClimbing', label: 'Escalade', emoji: '🧗‍♂️' },
  { value: 'Hiking', label: 'Randonnée', emoji: '🥾' },
  { value: 'Yoga', label: 'Yoga', emoji: '🧘‍♀️' },
  { value: 'Pilates', label: 'Pilates', emoji: '🤸‍♀' },
  { value: 'Crossfit', label: 'Crossfit', emoji: '🏋️‍♀️' },
  { value: 'Gym', label: 'Gym', emoji: '🏋️‍♂️' },
  { value: 'VirtualRun', label: 'Course virtuelle', emoji: '🏃‍♂️' },
  { value: 'VirtualRide', label: 'Vélo virtuel', emoji: '🚴‍♂️' },
  { value: 'Other', label: 'Autre', emoji: '🏃‍♂️' }
]

export default function ActivityTypeEditor({ activity, onSave, onCancel }: ActivityTypeEditorProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [selectedType, setSelectedType] = useState(activity.activity_type || 'Run')
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const currentSportType = SPORT_TYPES.find(type => type.value === activity.activity_type)
  const selectedSportType = SPORT_TYPES.find(type => type.value === selectedType)

  const handleSave = async () => {
    if (selectedType === activity.activity_type) {
      setIsEditing(false)
      return
    }

    setIsSaving(true)
    setError(null)

    try {
      // Appeler l'API pour mettre à jour le type d'activité
      const formData = new FormData()
      formData.append('activity_type', selectedType)
      
      // Utiliser l'API URL complète
      const VITE_API_URL = (import.meta as any).env?.VITE_API_URL
      const apiUrl = VITE_API_URL ? `${VITE_API_URL}/api/v1` : '/api/v1'

      const response = await fetch(`${apiUrl}/activities/${activity.id}/type`, {
        method: 'PATCH',
        credentials: 'include',
        body: formData
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        const errorMessage = errorData.detail || `Erreur ${response.status}: ${response.statusText}`
        throw new Error(errorMessage)
      }

      // Invalider les caches pour rafraîchir les données
      await queryClient.invalidateQueries({ queryKey: ['activities'] })
      await queryClient.invalidateQueries({ queryKey: ['enriched-activities'] })
      await queryClient.invalidateQueries({ queryKey: ['enriched-activities-for-badges'] })
      await queryClient.invalidateQueries({ queryKey: ['chronic-load'] })
      await queryClient.invalidateQueries({ queryKey: ['enriched-activity-stats'] })
      await queryClient.invalidateQueries({ queryKey: ['activity-stats'] })

      setIsEditing(false)
      onSave?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur inconnue')
    } finally {
      setIsSaving(false)
    }
  }

  const handleCancel = () => {
    setSelectedType(activity.activity_type || 'Run')
    setError(null)
    setIsEditing(false)
    onCancel?.()
  }

  if (!isEditing) {
    return (
      <div className="flex items-center space-x-2">
        <span className="text-lg">{currentSportType?.emoji}</span>
        <span className="text-sm font-medium text-gray-700">
          {currentSportType?.label || activity.activity_type}
        </span>
        <button
          onClick={(e) => {
            e.stopPropagation()
            e.preventDefault()
            setIsEditing(true)
          }}
          className="p-1 text-gray-400 hover:text-blue-600 transition-colors"
          title="Modifier le type de sport"
        >
          <Edit3 className="h-3 w-3" />
        </button>
      </div>
    )
  }

  return (
    <div 
      className="space-y-3"
      onClick={(e) => {
        e.stopPropagation()
        e.preventDefault()
      }}
    >
      {error && (
        <div className="flex items-center space-x-2 p-2 bg-red-50 border border-red-200 rounded-md">
          <AlertCircle className="h-4 w-4 text-red-600" />
          <span className="text-sm text-red-700">{error}</span>
        </div>
      )}

      <div className="space-y-2">
        <label className="text-sm font-medium text-gray-700">
          Type de sport
        </label>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 max-h-48 overflow-y-auto border border-gray-200 rounded-lg p-2">
          {SPORT_TYPES.map((type) => (
            <button
              key={type.value}
              onClick={() => setSelectedType(type.value)}
              className={`flex items-center space-x-2 p-2 rounded-md text-sm transition-colors ${
                selectedType === type.value
                  ? 'bg-blue-100 border-2 border-blue-300 text-blue-700'
                  : 'bg-gray-50 border border-gray-200 text-gray-700 hover:bg-gray-100'
              }`}
            >
              <span className="text-lg">{type.emoji}</span>
              <span className="truncate">{type.label}</span>
              {selectedType === type.value && (
                <Check className="h-3 w-3 text-blue-600" />
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center space-x-2">
        <button
          onClick={handleSave}
          disabled={isSaving || selectedType === activity.activity_type}
          className="inline-flex items-center px-3 py-1 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
        >
          {isSaving ? (
            <>
              <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-white mr-1"></div>
              Sauvegarde...
            </>
          ) : (
            <>
              <Save className="h-3 w-3 mr-1" />
              Sauvegarder
            </>
          )}
        </button>
        
        <button
          onClick={handleCancel}
          disabled={isSaving}
          className="inline-flex items-center px-3 py-1 bg-gray-200 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-300 disabled:bg-gray-100 disabled:cursor-not-allowed transition-colors"
        >
          <X className="h-3 w-3 mr-1" />
          Annuler
        </button>
      </div>

      {/* Aperçu du changement */}
      {selectedType !== activity.activity_type && (
        <div className="flex items-center space-x-2 p-2 bg-blue-50 border border-blue-200 rounded-md">
          <span className="text-sm text-blue-700">
            <span className="font-medium">Changement:</span> {currentSportType?.emoji} {currentSportType?.label} → {selectedSportType?.emoji} {selectedSportType?.label}
          </span>
        </div>
      )}
    </div>
  )
}
