import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, startOfWeek, endOfWeek, startOfMonth, endOfMonth, addMonths, subMonths, eachDayOfInterval, isSameDay, isSameMonth } from 'date-fns'
import { fr } from 'date-fns/locale'
import {
  Plus,
  Calendar,
  Target,
  Edit,
  Trash2,
  CheckCircle,
  XCircle,
  Search,
  TrendingUp,
  Upload,
  Clock
} from 'lucide-react'

import { workoutPlanService, workoutPlanUtils, type WorkoutPlan, type WorkoutPlanCreate, type WorkoutPlanUpdate } from '../services/workoutPlanService'
import { googleCalendarService, type GoogleCalendar } from '../services/googleCalendarService'
import { useToast } from '../contexts/ToastContext'
import ConfirmationModal from '../components/ConfirmationModal'
import CSVImportModal from '../components/CSVImportModal'
import GoogleCalendarModal from '../components/GoogleCalendarModal'


export default function WorkoutPlans() {
  const [selectedWeek, setSelectedWeek] = useState(new Date())
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedWorkoutType, setSelectedWorkoutType] = useState<string>('')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingPlan, setEditingPlan] = useState<WorkoutPlan | null>(null)
  const [showCSVImportModal, setShowCSVImportModal] = useState(false)
  const [showGoogleCalendarModal, setShowGoogleCalendarModal] = useState(false)

  const [confirmationModal, setConfirmationModal] = useState<{
    isOpen: boolean
    type: 'delete' | null
    planId?: string
  }>({ isOpen: false, type: null })

  const toast = useToast()
  const queryClient = useQueryClient()

  // Récupération des calendriers Google
  const { data: googleCalendars = [] } = useQuery({
    queryKey: ['google-calendars'],
    queryFn: googleCalendarService.getGoogleCalendars,
    enabled: false // On ne charge que quand nécessaire
  })

  // Calcul des dates du mois
  const monthStart = startOfMonth(selectedWeek)
  const monthEnd = endOfMonth(selectedWeek)
  
  // Calcul du début de la première semaine du mois (pour aligner avec lundi)
  const firstWeekStart = startOfWeek(monthStart, { weekStartsOn: 1 })
  const lastWeekEnd = endOfWeek(monthEnd, { weekStartsOn: 1 })
  const allDays = eachDayOfInterval({ start: firstWeekStart, end: lastWeekEnd })

  // Récupération des plans d'entraînement
  const { data: plans = [] } = useQuery({
    queryKey: ['workout-plans', format(monthStart, 'yyyy-MM-dd'), format(monthEnd, 'yyyy-MM-dd')],
    queryFn: () => workoutPlanService.getWorkoutPlans({
      start_date: format(monthStart, 'yyyy-MM-dd'),
      end_date: format(monthEnd, 'yyyy-MM-dd')
    })
  })

  // Mutations
  const createMutation = useMutation({
    mutationFn: workoutPlanService.createWorkoutPlan,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workout-plans'] })
      setShowCreateModal(false)
      toast.success('Plan créé avec succès')
    },
    onError: () => {
      toast.error('Erreur lors de la création du plan')
    }
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: WorkoutPlanUpdate }) =>
      workoutPlanService.updateWorkoutPlan(id, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workout-plans'] })
      setEditingPlan(null)
      toast.success('Plan modifié avec succès')
    },
    onError: () => {
      toast.error('Erreur lors de la modification du plan')
    }
  })

  const deleteMutation = useMutation({
    mutationFn: workoutPlanService.deleteWorkoutPlan,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workout-plans'] })
      setConfirmationModal({ isOpen: false, type: null })
      toast.success('Plan supprimé')
    },
    onError: () => {
      toast.error('Erreur lors de la suppression du plan')
    }
  })

  const toggleCompletionMutation = useMutation({
    mutationFn: ({ id, isCompleted }: { id: string; isCompleted: boolean }) =>
      isCompleted
        ? workoutPlanService.markAsCompleted(id)
        : workoutPlanService.markAsIncomplete(id),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['workout-plans'] })
      setConfirmationModal({ isOpen: false, type: null })
      toast.info(variables.isCompleted ? 'Plan marqué comme terminé' : 'Plan marqué comme non terminé')
    },
    onError: () => {
      toast.error('Erreur lors de la mise à jour du statut')
    }
  })

  // Navigation des mois
  const goToPreviousMonth = () => setSelectedWeek(subMonths(selectedWeek, 1))
  const goToNextMonth = () => setSelectedWeek(addMonths(selectedWeek, 1))
  const goToCurrentMonth = () => setSelectedWeek(new Date())

  // Filtrage des plans
  const filteredPlans = useMemo(() => {
    return plans.filter(plan => {
      const matchesSearch = plan.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                           plan.description?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                           plan.coach_notes?.toLowerCase().includes(searchTerm.toLowerCase())
      const matchesType = !selectedWorkoutType || plan.workout_type === selectedWorkoutType
      return matchesSearch && matchesType
    })
  }, [plans, searchTerm, selectedWorkoutType])

  // Grouper les plans par jour
  const plansByDay = useMemo(() => {
    return filteredPlans.reduce((acc, plan) => {
      const day = format(new Date(plan.planned_date), 'yyyy-MM-dd')
      if (!acc[day]) acc[day] = []
      acc[day].push(plan)
      return acc
    }, {} as Record<string, WorkoutPlan[]>)
  }, [filteredPlans])

  // Statistiques de la semaine
  const weeklyStats = useMemo(() => {
    const totalPlans = filteredPlans.length
    const completedPlans = filteredPlans.filter(p => p.is_completed).length
    const totalDistance = filteredPlans.reduce((sum, p) => sum + p.planned_distance, 0)
    const completionRate = totalPlans > 0 ? (completedPlans / totalPlans) * 100 : 0

    return {
      totalPlans,
      completedPlans,
      totalDistance,
      completionRate
    }
  }, [filteredPlans])

  // Gestion des actions
  const handleEdit = (plan: WorkoutPlan) => {
    setEditingPlan(plan)
  }

  const handleDelete = (planId: string) => {
    setConfirmationModal({ isOpen: true, type: 'delete', planId })
  }

  const handleToggleCompletion = (planId: string, isCompleted: boolean) => {
    // Action directe sans confirmation pour le toggle
    toggleCompletionMutation.mutate({ id: planId, isCompleted: !isCompleted })
  }

  const handleCreatePlan = (data: WorkoutPlanCreate) => {
    createMutation.mutate(data)
  }

  const handleUpdatePlan = (data: WorkoutPlanUpdate) => {
    if (editingPlan) {
      updateMutation.mutate({ id: editingPlan.id, updates: data })
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Plans d'Entraînement</h1>
          <p className="text-gray-600">Planifiez et suivez vos entraînements</p>
        </div>
        <div className="flex space-x-3">
          <button
            onClick={() => setShowGoogleCalendarModal(true)}
            className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <Calendar className="h-4 w-4 mr-2" />
            Google Calendar
          </button>

          <button
            onClick={() => setShowCSVImportModal(true)}
            className="inline-flex items-center px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500"
          >
            <Upload className="h-4 w-4 mr-2" />
            Importer CSV
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <Plus className="h-4 w-4 mr-2" />
            Nouveau Plan
          </button>
        </div>
      </div>

      {/* Statistiques de la semaine */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-lg shadow">
          <div className="flex items-center">
            <Calendar className="h-8 w-8 text-blue-500" />
            <div className="ml-3">
              <p className="text-sm font-medium text-gray-500">Plans prévus</p>
              <p className="text-2xl font-bold text-gray-900">{weeklyStats.totalPlans}</p>
            </div>
          </div>
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <div className="flex items-center">
            <CheckCircle className="h-8 w-8 text-green-500" />
            <div className="ml-3">
              <p className="text-sm font-medium text-gray-500">Terminés</p>
              <p className="text-2xl font-bold text-gray-900">{weeklyStats.completedPlans}</p>
            </div>
          </div>
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <div className="flex items-center">
            <Target className="h-8 w-8 text-orange-500" />
            <div className="ml-3">
              <p className="text-sm font-medium text-gray-500">Distance (km)</p>
              <p className="text-2xl font-bold text-gray-900">{weeklyStats.totalDistance.toFixed(1)}</p>
            </div>
          </div>
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <div className="flex items-center">
            <TrendingUp className="h-8 w-8 text-purple-500" />
            <div className="ml-3">
              <p className="text-sm font-medium text-gray-500">Taux de réalisation</p>
              <p className="text-2xl font-bold text-gray-900">{weeklyStats.completionRate.toFixed(0)}%</p>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation et filtres */}
      <div className="bg-white p-4 rounded-lg shadow">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          {/* Navigation des mois */}
          <div className="flex items-center space-x-4">
            <button
              onClick={goToPreviousMonth}
              className="p-2 text-gray-400 hover:text-gray-600"
            >
              ←
            </button>
            <div className="text-center">
              <h3 className="text-lg font-semibold text-gray-900">
                {format(selectedWeek, 'MMMM yyyy', { locale: fr })}
              </h3>
            </div>
            <button
              onClick={goToNextMonth}
              className="p-2 text-gray-400 hover:text-gray-600"
            >
              →
            </button>
            <button
              onClick={goToCurrentMonth}
              className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200"
            >
              Aujourd'hui
            </button>
          </div>

          {/* Filtres */}
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                placeholder="Rechercher..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10 pr-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              />
            </div>
            <select
              value={selectedWorkoutType}
              onChange={(e) => setSelectedWorkoutType(e.target.value)}
              className="px-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">Tous les types</option>
              <option value="easy_run">Course facile</option>
              <option value="interval">Intervalles</option>
              <option value="tempo">Tempo</option>
              <option value="long_run">Sortie longue</option>
              <option value="recovery">Récupération</option>
              <option value="fartlek">Fartlek</option>
              <option value="hill_repeat">Côtes</option>
              <option value="race">Course</option>
            </select>
          </div>
        </div>
      </div>

      {/* Calendrier simplifié */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        {/* En-têtes des jours */}
        <div className="grid grid-cols-7 bg-gray-50 border-b">
          {['lun.', 'mar.', 'mer.', 'jeu.', 'ven.', 'sam.', 'dim.'].map(dayName => (
            <div key={dayName} className="p-3 text-center">
              <div className="text-sm font-medium text-gray-900">
                {dayName}
              </div>
            </div>
          ))}
        </div>

        {/* Grille du calendrier */}
        <div className="grid grid-cols-7">
          {allDays.map(day => {
            const dayKey = format(day, 'yyyy-MM-dd')
            const dayPlans = plansByDay[dayKey] || []
            const isCurrentMonth = isSameMonth(day, selectedWeek)
            const isToday = isSameDay(day, new Date())
            
            return (
              <div 
                key={dayKey} 
                className={`border-r border-b border-gray-200 min-h-[120px] p-2 ${
                  !isCurrentMonth ? 'bg-gray-50' : ''
                }`}
              >
                {/* Numéro du jour */}
                <div className={`text-right mb-2 ${
                  isToday 
                    ? 'text-white bg-red-500 rounded-full w-6 h-6 flex items-center justify-center text-sm font-bold mx-auto' 
                    : isCurrentMonth 
                      ? 'text-gray-900 font-medium' 
                      : 'text-gray-400'
                }`}>
                  {format(day, 'd')}
                </div>
                
                {/* Plans d'entraînement */}
                <div className="space-y-1">
                  {dayPlans.map(plan => (
                    <WorkoutPlanCard
                      key={plan.id}
                      plan={plan}
                      onEdit={() => handleEdit(plan)}
                      onDelete={() => handleDelete(plan.id)}
                      onToggleCompletion={() => handleToggleCompletion(plan.id, plan.is_completed)}
                    />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Modals */}
      <WorkoutPlanModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onSubmit={handleCreatePlan}
        isLoading={createMutation.isPending}
      />

      <WorkoutPlanModal
        isOpen={!!editingPlan}
        onClose={() => setEditingPlan(null)}
        onSubmit={handleUpdatePlan}
        isLoading={updateMutation.isPending}
        plan={editingPlan || undefined}
        isEditing={true}
      />

      <ConfirmationModal
        isOpen={confirmationModal.isOpen}
        onClose={() => setConfirmationModal({ isOpen: false, type: null })}
        onConfirm={() => {
          if (!confirmationModal.planId) return
          if (confirmationModal.type === 'delete') {
            deleteMutation.mutate(confirmationModal.planId)
          }
        }}
        title="Supprimer le plan"
        message="Êtes-vous sûr de vouloir supprimer ce plan d'entraînement ?"
        confirmText="Supprimer"
        dangerLevel="high"
      />

      <CSVImportModal
        isOpen={showCSVImportModal}
        onClose={() => setShowCSVImportModal(false)}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: ['workout-plans'] })
        }}
      />

      <GoogleCalendarModal
        isOpen={showGoogleCalendarModal}
        onClose={() => setShowGoogleCalendarModal(false)}
      />


    </div>
  )
}

// Composant simple pour un plan d'entraînement
function WorkoutPlanCard({ 
  plan, 
  onEdit, 
  onDelete, 
  onToggleCompletion 
}: { 
  plan: WorkoutPlan
  onEdit: () => void
  onDelete: () => void
  onToggleCompletion: () => void
}) {
  return (
    <div className={`p-2 rounded-lg border transition-all hover:shadow-md relative ${
      plan.is_completed 
        ? 'bg-green-50 border-green-200' 
        : 'bg-blue-50 border-blue-200'
    }`}>
      {/* Numéro du jour en haut à droite */}
      <div className="absolute top-1 right-1 text-xs font-bold text-gray-500">
        {format(new Date(plan.planned_date), 'd')}
      </div>
      
      {/* En-tête avec boutons d'action */}
      <div className="flex items-start justify-between mb-1">
        <div className="flex-1 min-w-0 pr-6">
          <h4 className="font-medium text-gray-900 text-xs truncate">{plan.name}</h4>
          <div className="flex items-center space-x-2 mt-1">
            <span className="text-xs text-gray-600">{plan.planned_distance}km</span>
            {plan.planned_elevation_gain && (
              <span className="text-xs text-gray-600">+{plan.planned_elevation_gain}m</span>
            )}
          </div>
        </div>
        <div className="flex space-x-1">
          <button
            onClick={onToggleCompletion}
            className="p-1 text-gray-400 hover:text-gray-600"
          >
            {plan.is_completed ? (
              <CheckCircle className="h-3 w-3 text-green-500" />
            ) : (
              <XCircle className="h-3 w-3" />
            )}
          </button>
          <button
            onClick={onEdit}
            className="p-1 text-gray-400 hover:text-gray-600"
          >
            <Edit className="h-3 w-3" />
          </button>
          <button
            onClick={onDelete}
            className="p-1 text-gray-400 hover:text-red-600"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      </div>

      {/* Type d'entraînement */}
      <div className="mb-1">
        <span className={`inline-flex items-center px-1 py-0.5 rounded-full text-xs font-medium ${
          workoutPlanUtils.getWorkoutTypeColor(plan.workout_type)
        }`}>
          {workoutPlanUtils.getWorkoutTypeLabel(plan.workout_type)}
        </span>
      </div>

      {/* Description */}
      {plan.description && (
        <div className="mb-1">
          <p className="text-xs text-gray-700 line-clamp-2">{plan.description}</p>
        </div>
      )}

      {/* Notes du coach */}
      {plan.coach_notes && (
        <div className="mb-1">
          <p className="text-xs text-gray-600 line-clamp-1 italic">"{plan.coach_notes}"</p>
        </div>
      )}

      {/* Détails supplémentaires */}
      <div className="flex items-center space-x-2 text-xs text-gray-500">
        {plan.planned_pace && (
          <span className="flex items-center">
            <Clock className="h-3 w-3 mr-1" />
            {workoutPlanUtils.formatPace(plan.planned_pace)}
          </span>
        )}
        {plan.intensity_zone && (
          <span className="flex items-center">
            <Target className="h-3 w-3 mr-1" />
            {workoutPlanUtils.getIntensityZoneLabel(plan.intensity_zone)}
          </span>
        )}
      </div>
    </div>
  )
}

// Composant modal pour créer/éditer un plan
function WorkoutPlanModal({ 
  isOpen, 
  onClose, 
  onSubmit, 
  isLoading, 
  plan, 
  isEditing = false 
}: { 
  isOpen: boolean
  onClose: () => void
  onSubmit: (data: any) => void
  isLoading: boolean
  plan?: WorkoutPlan
  isEditing?: boolean
}) {
  const [formData, setFormData] = useState<WorkoutPlanCreate>({
    name: '',
    workout_type: 'easy_run',
    planned_date: format(new Date(), 'yyyy-MM-dd'),
    planned_distance: 0,
    planned_duration: undefined,
    planned_pace: undefined,
    planned_elevation_gain: undefined,
    intensity_zone: undefined,
    description: '',
    coach_notes: '',
    phase: '',
    week: undefined,
    rpe: undefined
  })

  // Initialiser le formulaire avec les données du plan à éditer
  if (isEditing && plan && !formData.name) {
    setFormData({
      name: plan.name,
      workout_type: plan.workout_type,
      planned_date: plan.planned_date,
      planned_distance: plan.planned_distance,
      planned_duration: plan.planned_duration,
      planned_pace: plan.planned_pace,
      planned_elevation_gain: plan.planned_elevation_gain,
      intensity_zone: plan.intensity_zone,
      description: plan.description || '',
      coach_notes: plan.coach_notes || '',
      phase: plan.phase || '',
      week: plan.week,
      rpe: plan.rpe
    })
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit(formData)
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-900">
            {isEditing ? 'Modifier le plan' : 'Nouveau plan d\'entraînement'}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            <XCircle className="h-6 w-6" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Nom et type */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Nom du plan
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Type d'entraînement
              </label>
              <select
                value={formData.workout_type}
                onChange={(e) => setFormData(prev => ({ ...prev, workout_type: e.target.value as any }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="easy_run">Course facile</option>
                <option value="interval">Intervalles</option>
                <option value="tempo">Tempo</option>
                <option value="long_run">Sortie longue</option>
                <option value="recovery">Récupération</option>
                <option value="fartlek">Fartlek</option>
                <option value="hill_repeat">Côtes</option>
                <option value="race">Course</option>
              </select>
            </div>
          </div>

          {/* Date et distance */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Date
              </label>
              <input
                type="date"
                value={formData.planned_date}
                onChange={(e) => setFormData(prev => ({ ...prev, planned_date: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Distance (km)
              </label>
              <input
                type="number"
                step="0.1"
                value={formData.planned_distance}
                onChange={(e) => setFormData(prev => ({ ...prev, planned_distance: parseFloat(e.target.value) }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
                required
              />
            </div>
          </div>

          {/* Dénivelé et pace */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Dénivelé positif (m)
              </label>
              <input
                type="number"
                value={formData.planned_elevation_gain || ''}
                onChange={(e) => setFormData(prev => ({ ...prev, planned_elevation_gain: e.target.value ? parseFloat(e.target.value) : undefined }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Allure (min/km)
              </label>
              <input
                type="number"
                step="0.1"
                value={formData.planned_pace || ''}
                onChange={(e) => setFormData(prev => ({ ...prev, planned_pace: e.target.value ? parseFloat(e.target.value) : undefined }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              />
            </div>
          </div>

          {/* Zone d'intensité et durée */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Zone d'intensité
              </label>
              <select
                value={formData.intensity_zone || ''}
                onChange={(e) => setFormData(prev => ({ ...prev, intensity_zone: e.target.value as any || undefined }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">Non définie</option>
                <option value="zone_1">Zone 1 - Récupération</option>
                <option value="zone_2">Zone 2 - Endurance</option>
                <option value="zone_3">Zone 3 - Tempo</option>
                <option value="zone_4">Zone 4 - Seuil</option>
                <option value="zone_5">Zone 5 - VO2 Max</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Durée (minutes)
              </label>
              <input
                type="number"
                value={formData.planned_duration ? Math.floor(formData.planned_duration / 60) : ''}
                onChange={(e) => setFormData(prev => ({ ...prev, planned_duration: e.target.value ? parseInt(e.target.value) * 60 : undefined }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              />
            </div>
          </div>

          {/* Phase et semaine */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Phase d'entraînement
              </label>
              <input
                type="text"
                value={formData.phase}
                onChange={(e) => setFormData(prev => ({ ...prev, phase: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
                placeholder="ex: base 1, build, peak..."
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Semaine
              </label>
              <input
                type="number"
                value={formData.week || ''}
                onChange={(e) => setFormData(prev => ({ ...prev, week: e.target.value ? parseInt(e.target.value) : undefined }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              />
            </div>
          </div>

          {/* RPE */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              RPE (Rate of Perceived Exertion)
            </label>
            <input
              type="number"
              min="1"
              max="10"
              value={formData.rpe || ''}
              onChange={(e) => setFormData(prev => ({ ...prev, rpe: e.target.value ? parseInt(e.target.value) : undefined }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              placeholder="1-10"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              placeholder="Description du parcours ou de l'entraînement..."
            />
          </div>

          {/* Notes du coach */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Notes du coach
            </label>
            <textarea
              value={formData.coach_notes}
              onChange={(e) => setFormData(prev => ({ ...prev, coach_notes: e.target.value }))}
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              placeholder="Instructions détaillées du coach..."
            />
          </div>

          {/* Boutons */}
          <div className="flex justify-end space-x-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 disabled:opacity-50"
            >
              {isLoading ? 'Enregistrement...' : (isEditing ? 'Modifier' : 'Créer')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
} 