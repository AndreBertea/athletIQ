import { Calendar, Target, CheckCircle, TrendingUp, Zap, ArrowRight } from 'lucide-react'
import type { WorkoutPlan } from '../../services/workoutPlanService'
import { workoutPlanUtils } from '../../services/workoutPlanService'
import { formatDateRelative } from '../../lib/format'

interface DashboardWorkoutPlansProps {
  workoutPlans: WorkoutPlan[]
}

export default function DashboardWorkoutPlans({ workoutPlans }: DashboardWorkoutPlansProps) {
  const upcomingPlans = workoutPlans
    .filter(plan => {
      const planDate = new Date(plan.planned_date)
      const today = new Date()
      today.setHours(0, 0, 0, 0)
      return planDate >= today
    })
    .sort((a, b) => new Date(a.planned_date).getTime() - new Date(b.planned_date).getTime())

  const completedCount = workoutPlans.filter(p => p.is_completed).length
  const totalCount = workoutPlans.length
  const completionRate = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0

  return (
    <div className="bg-white rounded-xl border border-gray-200/60 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <Calendar className="h-5 w-5 text-cyan-500" />
          <h3 className="text-base font-semibold text-gray-900">Prochaines séances</h3>
        </div>
        <a
          href="/plans"
          className="inline-flex items-center gap-1 text-sm font-medium text-orange-600 hover:text-orange-700 transition-colors"
        >
          Tous les plans
          <ArrowRight className="h-3.5 w-3.5" />
        </a>
      </div>

      {workoutPlans.length === 0 ? (
        /* État vide — pattern unifié */
        <div className="flex flex-col items-center justify-center py-12 text-gray-400">
          <Calendar className="h-10 w-10 mb-3 text-gray-300" />
          <p className="text-sm font-medium text-gray-500">Aucun plan d'entraînement</p>
          <p className="text-xs text-gray-400 mt-1">
            Créez votre premier plan pour suivre vos objectifs
          </p>
          <a
            href="/plans"
            className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-cyan-500 rounded-lg hover:bg-cyan-600 transition-colors"
          >
            <Target className="h-4 w-4" />
            Créer un plan
          </a>
        </div>
      ) : (
        <div className="space-y-5">
          {/* Stats compactes */}
          <div className="grid grid-cols-3 gap-4">
            {/* Total plans */}
            <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
              <div className="flex items-center gap-2 mb-2">
                <div className="p-1.5 rounded-md bg-cyan-100">
                  <Target className="h-4 w-4 text-cyan-600" />
                </div>
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Total</span>
              </div>
              <p className="text-2xl font-bold text-gray-900">{totalCount}</p>
            </div>

            {/* Terminés */}
            <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
              <div className="flex items-center gap-2 mb-2">
                <div className="p-1.5 rounded-md bg-green-100">
                  <CheckCircle className="h-4 w-4 text-green-600" />
                </div>
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Terminés</span>
              </div>
              <p className="text-2xl font-bold text-gray-900">{completedCount}</p>
            </div>

            {/* Taux de complétion */}
            <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
              <div className="flex items-center gap-2 mb-2">
                <div className="p-1.5 rounded-md bg-cyan-100">
                  <TrendingUp className="h-4 w-4 text-cyan-600" />
                </div>
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Complétion</span>
              </div>
              <p className="text-2xl font-bold text-gray-900">{completionRate}%</p>
            </div>
          </div>

          {/* Barre de progression globale */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs text-gray-500">
                {completedCount} sur {totalCount} séances terminées
              </span>
              <span className="text-xs font-medium text-cyan-600">{completionRate}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-cyan-500 h-2 rounded-full transition-all duration-500"
                style={{ width: `${completionRate}%` }}
              />
            </div>
          </div>

          {/* Prochaines séances (max 3) */}
          {upcomingPlans.length > 0 ? (
            <div>
              <div className="divide-y divide-gray-100">
                {upcomingPlans.slice(0, 3).map(plan => {
                  const dateLabel = formatDateRelative(plan.planned_date)
                  const typeLabel = workoutPlanUtils.getWorkoutTypeLabel(plan.workout_type)
                  const typeColor = workoutPlanUtils.getWorkoutTypeColor(plan.workout_type)

                  return (
                    <div
                      key={plan.id}
                      className="flex items-center justify-between py-3 first:pt-0 last:pb-0 hover:bg-gray-50 -mx-2 px-2 rounded-lg transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="flex-shrink-0">
                          <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${typeColor}`}>
                            <Zap className="h-3 w-3" />
                            {typeLabel}
                          </span>
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-gray-900 truncate">{plan.name}</p>
                          <p className="text-xs text-gray-500">
                            {dateLabel}
                            {plan.planned_distance ? ` · ${plan.planned_distance} km` : ''}
                            {plan.planned_duration ? ` · ${workoutPlanUtils.formatDuration(plan.planned_duration)}` : ''}
                          </p>
                        </div>
                      </div>
                      <div className="flex-shrink-0 text-right ml-3">
                        {plan.is_completed ? (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-green-600">
                            <CheckCircle className="h-3.5 w-3.5" />
                            Terminé
                          </span>
                        ) : (
                          <span className={`text-xs font-medium ${
                            dateLabel === "Aujourd'hui" ? 'text-cyan-600' :
                            dateLabel === 'Demain' ? 'text-orange-500' : 'text-gray-400'
                          }`}>
                            {dateLabel === "Aujourd'hui" ? "Aujourd'hui" :
                             dateLabel === 'Demain' ? 'Demain' : 'À venir'}
                          </span>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center py-6 text-gray-400">
              <CheckCircle className="h-8 w-8 mb-2 text-green-300" />
              <p className="text-sm font-medium text-gray-500">Toutes les séances sont terminées</p>
              <p className="text-xs text-gray-400 mt-0.5">Bravo !</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
