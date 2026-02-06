import axios from 'axios'

// Utiliser l'URL de l'API configurée via VITE_API_URL ou fallback sur relative
const VITE_API_URL = (import.meta as any).env?.VITE_API_URL
const API_URL = VITE_API_URL ? `${VITE_API_URL}/api/v1` : '/api/v1'

// Types pour les plans d'entraînement
export interface WorkoutPlan {
  id: string
  name: string
  workout_type: 'easy_run' | 'interval' | 'tempo' | 'long_run' | 'recovery' | 'fartlek' | 'hill_repeat' | 'race'
  planned_date: string
  planned_distance: number
  planned_duration?: number
  planned_pace?: number
  planned_elevation_gain?: number
  intensity_zone?: 'zone_1' | 'zone_2' | 'zone_3' | 'zone_4' | 'zone_5'
  description?: string
  coach_notes?: string
  workout_structure?: Record<string, any>
  planned_route?: Array<{ lat: number; lng: number }>
  is_completed: boolean
  completion_percentage?: number
  actual_activity_id?: string
  created_at: string
  updated_at: string
  // Nouveaux champs pour l'import CSV
  phase?: string
  week?: number
  rpe?: number
}

export interface WorkoutPlanCreate {
  name: string
  workout_type: WorkoutPlan['workout_type']
  planned_date: string
  planned_distance: number
  planned_duration?: number
  planned_pace?: number
  planned_elevation_gain?: number
  intensity_zone?: WorkoutPlan['intensity_zone']
  description?: string
  coach_notes?: string
  workout_structure?: Record<string, any>
  planned_route?: Array<{ lat: number; lng: number }>
  phase?: string
  week?: number
  rpe?: number
}

export interface WorkoutPlanUpdate {
  name?: string
  workout_type?: WorkoutPlan['workout_type']
  planned_date?: string
  planned_distance?: number
  planned_duration?: number
  planned_pace?: number
  planned_elevation_gain?: number
  intensity_zone?: WorkoutPlan['intensity_zone']
  description?: string
  coach_notes?: string
  is_completed?: boolean
  completion_percentage?: number | null
  phase?: string
  week?: number
  rpe?: number
}





// Configuration axios avec token d'authentification
const getAuthHeaders = () => {
  const token = localStorage.getItem('access_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// Service pour les plans d'entraînement
export const workoutPlanService = {
  // Créer un nouveau plan d'entraînement
  async createWorkoutPlan(plan: WorkoutPlanCreate): Promise<WorkoutPlan> {
    const response = await axios.post(`${API_URL}/workout-plans`, plan, {
      headers: getAuthHeaders()
    })
    return response.data
  },

  // Récupérer la liste des plans d'entraînement
  async getWorkoutPlans(params?: {
    start_date?: string
    end_date?: string
    workout_type?: string
    is_completed?: boolean
  }): Promise<WorkoutPlan[]> {
    const response = await axios.get(`${API_URL}/workout-plans`, {
      headers: getAuthHeaders(),
      params
    })
    return response.data
  },

  // Récupérer un plan d'entraînement spécifique
  async getWorkoutPlan(id: string): Promise<WorkoutPlan> {
    const response = await axios.get(`${API_URL}/workout-plans/${id}`, {
      headers: getAuthHeaders()
    })
    return response.data
  },

  // Mettre à jour un plan d'entraînement
  async updateWorkoutPlan(id: string, updates: WorkoutPlanUpdate): Promise<WorkoutPlan> {
    const response = await axios.patch(`${API_URL}/workout-plans/${id}`, updates, {
      headers: getAuthHeaders()
    })
    return response.data
  },

  // Supprimer un plan d'entraînement
  async deleteWorkoutPlan(id: string): Promise<void> {
    await axios.delete(`${API_URL}/workout-plans/${id}`, {
      headers: getAuthHeaders()
    })
  },





  // Marquer un plan comme terminé
  async markAsCompleted(planId: string, completionPercentage?: number): Promise<WorkoutPlan> {
    return this.updateWorkoutPlan(planId, {
      is_completed: true,
      ...(completionPercentage !== undefined && { completion_percentage: completionPercentage })
    })
  },

  // Marquer un plan comme non terminé
  async markAsIncomplete(planId: string): Promise<WorkoutPlan> {
    return this.updateWorkoutPlan(planId, {
      is_completed: false,
      completion_percentage: null
    })
  },

  // Importer des plans depuis un fichier CSV
  async importFromCSV(file: File): Promise<{
    success: boolean
    message: string
    imported_count: number
    total_count: number
    errors: string[]
  }> {
    const formData = new FormData()
    formData.append('file', file)

    const response = await axios.post(`${API_URL}/workout-plans/import-csv`, formData, {
      headers: {
        ...getAuthHeaders()
        // Ne pas définir Content-Type pour multipart/form-data
        // Le navigateur le fait automatiquement avec la boundary
      }
    })
    return response.data
  }
}

// Utilitaires pour les plans d'entraînement
export const workoutPlanUtils = {
  // Obtenir le nom lisible du type d'entraînement
  getWorkoutTypeLabel(type: WorkoutPlan['workout_type']): string {
    const labels: Record<WorkoutPlan['workout_type'], string> = {
      easy_run: 'Course facile',
      interval: 'Intervalles',
      tempo: 'Tempo',
      long_run: 'Sortie longue',
      recovery: 'Récupération',
      fartlek: 'Fartlek',
      hill_repeat: 'Côtes',
      race: 'Course'
    }
    return labels[type] || type
  },

  // Obtenir la couleur du type d'entraînement
  getWorkoutTypeColor(type: WorkoutPlan['workout_type']): string {
    const colors: Record<WorkoutPlan['workout_type'], string> = {
      easy_run: 'bg-green-100 text-green-800',
      interval: 'bg-red-100 text-red-800',
      tempo: 'bg-orange-100 text-orange-800',
      long_run: 'bg-blue-100 text-blue-800',
      recovery: 'bg-gray-100 text-gray-800',
      fartlek: 'bg-purple-100 text-purple-800',
      hill_repeat: 'bg-yellow-100 text-yellow-800',
      race: 'bg-pink-100 text-pink-800'
    }
    return colors[type] || 'bg-gray-100 text-gray-800'
  },

  // Obtenir le nom de la zone d'intensité
  getIntensityZoneLabel(zone?: WorkoutPlan['intensity_zone']): string {
    if (!zone) return 'Non définie'
    const labels: Record<NonNullable<WorkoutPlan['intensity_zone']>, string> = {
      zone_1: 'Zone 1 - Récupération',
      zone_2: 'Zone 2 - Endurance',
      zone_3: 'Zone 3 - Tempo',
      zone_4: 'Zone 4 - Seuil',
      zone_5: 'Zone 5 - VO2 Max'
    }
    return labels[zone] || zone
  },

  // Formater la durée en format lisible
  formatDuration(seconds?: number): string {
    if (!seconds) return 'Non définie'
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    if (hours > 0) {
      return `${hours}h${minutes.toString().padStart(2, '0')}`
    }
    return `${minutes}min`
  },

  // Formater le pace en format lisible
  formatPace(pace?: number): string {
    if (!pace) return 'Non défini'
    const minutes = Math.floor(pace)
    const seconds = Math.round((pace - minutes) * 60)
    return `${minutes}:${seconds.toString().padStart(2, '0')}/km`
  },

  // Calculer le pourcentage de réalisation
  calculateCompletionRate(plan: WorkoutPlan): number {
    if (plan.completion_percentage !== undefined) {
      return plan.completion_percentage
    }
    return plan.is_completed ? 100 : 0
  }
} 