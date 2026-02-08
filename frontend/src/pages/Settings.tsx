import { useState } from 'react'
import { Link2, Watch, User } from 'lucide-react'
import StravaSection from '../components/settings/StravaSection'
import GarminSection from '../components/settings/GarminSection'
import AccountSection from '../components/settings/AccountSection'

type Tab = 'strava' | 'garmin' | 'compte'

const tabs: { id: Tab; label: string; icon: typeof Link2 }[] = [
  { id: 'strava', label: 'Strava', icon: Link2 },
  { id: 'garmin', label: 'Garmin', icon: Watch },
  { id: 'compte', label: 'Compte', icon: User },
]

export default function Settings() {
  const [activeTab, setActiveTab] = useState<Tab>('strava')

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Paramètres</h1>

      {/* Onglets */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          {tabs.map((tab) => {
            const Icon = tab.icon
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`inline-flex items-center px-1 pb-3 text-sm font-medium border-b-2 ${
                  isActive
                    ? 'border-primary-500 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <Icon className="h-4 w-4 mr-2" />
                {tab.label}
              </button>
            )
          })}
        </nav>
      </div>

      {/* Contenu de l'onglet actif */}
      {activeTab === 'strava' && <StravaSection />}
      {activeTab === 'garmin' && <GarminSection />}
      {activeTab === 'compte' && <AccountSection />}
    </div>
  )
}
