import { Clock3, Link2 } from 'lucide-react'

export default function StravaSection() {
  return (
    <div className="space-y-6">
      <div className="card">
        <div className="flex items-start">
          <div className="rounded-full bg-gray-100 p-3">
            <Link2 className="h-7 w-7 text-gray-500" />
          </div>
          <div className="ml-4">
            <h3 className="text-lg font-medium text-gray-900">
              Connexion Strava suspendue
            </h3>
            <p className="mt-1 text-sm text-gray-600">
              La connexion a Strava sera proposee dans une future version,
              apres validation du cadre d'utilisation des donnees.
            </p>
          </div>
        </div>

        <div className="mt-6 rounded-md border border-amber-200 bg-amber-50 p-4">
          <div className="flex items-start text-amber-900">
            <Clock3 className="mr-3 mt-0.5 h-5 w-5 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium">Integration en attente</p>
              <p className="mt-1 text-sm">
                Les activites et les predictions reposent actuellement sur les
                donnees Garmin. Aucune nouvelle synchronisation Strava ne peut
                etre lancee depuis AGON.
              </p>
            </div>
          </div>
        </div>

        <p className="mt-4 text-xs text-gray-500">
          Les options de suppression des donnees existantes restent accessibles
          dans l'onglet Compte.
        </p>
      </div>
    </div>
  )
}
