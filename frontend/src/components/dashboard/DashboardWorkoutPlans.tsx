import { useState } from 'react'
import { Calendar, Target, CheckCircle, TrendingUp, ChevronDown, ChevronUp } from 'lucide-react'
import type { WorkoutPlan } from '../../services/workoutPlanService'
import { formatDateRelative } from '../../lib/format'

interface DashboardWorkoutPlansProps {
  workoutPlans: WorkoutPlan[]
}

export default function DashboardWorkoutPlans({ workoutPlans }: DashboardWorkoutPlansProps) {
  const [showMore, setShowMore] = useState(false)

  const upcomingPlans = workoutPlans
    .filter(plan => {
      const planDate = new Date(plan.planned_date)
      const today = new Date()
      today.setHours(0, 0, 0, 0)
      return planDate >= today
    })
    .sort((a, b) => new Date(a.planned_date).getTime() - new Date(b.planned_date).getTime())

  const completedCount = workoutPlans.filter(p => p.is_completed).length
  const averageRate = workoutPlans.length > 0
    ? Math.round(workoutPlans.reduce((sum, p) => sum + (p.completion_percentage || 0), 0) / workoutPlans.length)
    : 0

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-medium text-gray-900">
          Plans d'Entraînement
        </h3>
        <a
          href="/plans"
          className="inline-flex items-center px-3 py-2 text-sm font-medium text-primary-600 bg-primary-50 rounded-md hover:bg-primary-100"
        >
          <Calendar className="h-4 w-4 mr-2" />
          Voir tous les plans
        </a>
      </div>

      {workoutPlans.length === 0 ? (
        <div className="text-center py-8">
          <Calendar className="h-12 w-12 text-gray-400 mx-auto mb-4" />
          <h4 className="text-lg font-medium text-gray-900 mb-2">Aucun plan d'entraînement</h4>
          <p className="text-gray-600 mb-4">
            Créez votre premier plan d'entraînement pour commencer à suivre vos objectifs
          </p>
          <a
            href="/plans"
            className="inline-flex items-center px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700"
          >
            Créer un plan
          </a>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Statistiques des plans */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="bg-gray-50 p-4 rounded-lg">
              <div className="flex items-center">
                <Target className="h-5 w-5 text-blue-500 mr-2" />
                <span className="text-sm font-medium text-gray-700">Total</span>
              </div>
              <p className="text-2xl font-bold text-gray-900 mt-1">{workoutPlans.length}</p>
            </div>
            <div className="bg-gray-50 p-4 rounded-lg">
              <div className="flex items-center">
                <CheckCircle className="h-5 w-5 text-green-500 mr-2" />
                <span className="text-sm font-medium text-gray-700">Terminés</span>
              </div>
              <p className="text-2xl font-bold text-gray-900 mt-1">{completedCount}</p>
            </div>
            <div className="bg-gray-50 p-4 rounded-lg">
              <div className="flex items-center">
                <TrendingUp className="h-5 w-5 text-orange-500 mr-2" />
                <span className="text-sm font-medium text-gray-700">Taux moyen</span>
              </div>
              <p className="text-2xl font-bold text-gray-900 mt-1">{averageRate}%</p>
            </div>
          </div>

          {/* Plans à venir */}
          <div>
            <h4 className="text-md font-medium text-gray-900 mb-3">Prochaines séances</h4>
            <div className="space-y-2">
              {upcomingPlans
                .slice(0, showMore ? 8 : 3)
                .map(plan => {
                  const dateLabel = formatDateRelative(plan.planned_date)
                  const isRelative = dateLabel === "Aujourd'hui" || dateLabel === 'Demain'

                  return (
                    <div key={plan.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                      <div className="flex items-center">
                        <div className={`w-3 h-3 rounded-full mr-3 ${
                          plan.is_completed ? 'bg-green-500' :
                          dateLabel === "Aujourd'hui" ? 'bg-blue-500' :
                          dateLabel === 'Demain' ? 'bg-orange-500' : 'bg-yellow-500'
                        }`} />
                        <div>
                          <p className="font-medium text-gray-900">{plan.name}</p>
                          <p className="text-sm text-gray-600">
                            {dateLabel} • {plan.planned_distance}km
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-medium text-gray-900">
                          {(plan.completion_percentage || 0).toFixed(0)}%
                        </p>
                        <p className="text-xs text-gray-500">
                          {plan.is_completed ? 'Terminé' :
                           isRelative ? dateLabel : 'À venir'}
                        </p>
                      </div>
                    </div>
                  )
                })}

              {/* Bouton "Voir plus" */}
              {upcomingPlans.length > 3 && (
                <button
                  onClick={() => setShowMore(!showMore)}
                  className="w-full mt-3 flex items-center justify-center px-4 py-2 text-sm font-medium text-primary-600 bg-primary-50 rounded-md hover:bg-primary-100 transition-colors"
                >
                  {showMore ? (
                    <>
                      <ChevronUp className="h-4 w-4 mr-2" />
                      Voir moins
                    </>
                  ) : (
                    <>
                      <ChevronDown className="h-4 w-4 mr-2" />
                      Voir plus ({upcomingPlans.length - 3} autres)
                    </>
                  )}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
