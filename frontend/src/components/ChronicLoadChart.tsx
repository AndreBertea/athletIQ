import { useState } from 'react'
import { AreaChart } from './ui/area-chart'
import { TrendingUp, TrendingDown, Minus, Heart } from 'lucide-react'

type LoadModel = 'banister' | 'edwards' | 'comparison'

interface ChronicLoadData {
  date: string
  chronicLoad: number
  acuteLoad: number
  trainingStressBalance: number
  chronicLoadEdwards: number
  acuteLoadEdwards: number
  tsbEdwards: number
}

interface ChronicLoadChartProps {
  data: ChronicLoadData[]
  isLoading?: boolean
  rhrDelta7d?: number
}

export default function ChronicLoadChart({ data, isLoading, rhrDelta7d }: ChronicLoadChartProps) {
  const [mode, setMode] = useState<LoadModel>('banister')

  if (isLoading) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-500">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mr-3"></div>
        Calcul de la charge chronique...
      </div>
    )
  }

  if (!data || data.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-500 bg-gray-50 rounded-lg">
        <div className="text-center">
          <div className="text-4xl mb-2">📊</div>
          <p>Données insuffisantes pour calculer la charge chronique</p>
          <p className="text-sm text-gray-400 mt-1">
            Au moins 42 jours d'activités sont nécessaires
          </p>
        </div>
      </div>
    )
  }

  // Calculer les statistiques de charge
  const latestData = data[data.length - 1]
  const previousData = data.length > 1 ? data[data.length - 2] : null

  const chronicTrend = previousData
    ? latestData.chronicLoad - previousData.chronicLoad
    : 0

  const chronicTrendEdwards = previousData
    ? latestData.chronicLoadEdwards - previousData.chronicLoadEdwards
    : 0

  const getTrendIcon = (trend: number) => {
    if (trend > 0) return <TrendingUp className="h-4 w-4 text-green-500" />
    if (trend < 0) return <TrendingDown className="h-4 w-4 text-red-500" />
    return <Minus className="h-4 w-4 text-gray-500" />
  }

  const getTrendColor = (trend: number) => {
    if (trend > 0) return 'text-green-600'
    if (trend < 0) return 'text-red-600'
    return 'text-gray-600'
  }

  const getTSBStatus = (tsb: number) => {
    if (tsb > 10) return { status: 'Récupération', color: 'text-green-600 bg-green-50' }
    if (tsb < -10) return { status: 'Surmenage', color: 'text-red-600 bg-red-50' }
    return { status: 'Équilibre', color: 'text-blue-600 bg-blue-50' }
  }

  const tsbStatusBanister = getTSBStatus(latestData.trainingStressBalance)
  const tsbStatusEdwards = getTSBStatus(latestData.tsbEdwards)

  // Catégories et couleurs selon le mode
  const getChartConfig = () => {
    switch (mode) {
      case 'banister':
        return {
          categories: ['chronicLoad', 'acuteLoad'],
          colors: ['hsl(var(--chart-1))', 'hsl(var(--chart-2))'],
        }
      case 'edwards':
        return {
          categories: ['chronicLoadEdwards', 'acuteLoadEdwards'],
          colors: ['hsl(160, 70%, 45%)', 'hsl(280, 60%, 55%)'],
        }
      case 'comparison':
        return {
          categories: ['chronicLoad', 'acuteLoad', 'chronicLoadEdwards', 'acuteLoadEdwards'],
          colors: ['hsl(var(--chart-1))', 'hsl(var(--chart-2))', 'hsl(160, 70%, 45%)', 'hsl(280, 60%, 55%)'],
        }
    }
  }

  const chartConfig = getChartConfig()

  const getSubtitle = () => {
    switch (mode) {
      case 'banister':
        return 'Charge chronique (EWMA 42j) vs Charge aiguë (EWMA 7j) - Modèle de Banister'
      case 'edwards':
        return 'Charge chronique (EWMA 42j) vs Charge aiguë (EWMA 7j) - Modèle d\'Edwards'
      case 'comparison':
        return 'Comparaison Banister vs Edwards - EWMA 42j / 7j'
    }
  }

  return (
    <div className="space-y-4">
      {/* Toggle modèle */}
      <div className="flex items-center justify-between">
        <div className="flex space-x-1 bg-gray-100 rounded-lg p-1">
          <button
            onClick={() => setMode('banister')}
            className={`px-3 py-1 text-sm rounded-md transition-colors ${mode === 'banister' ? 'bg-white shadow text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}
          >
            Banister
          </button>
          <button
            onClick={() => setMode('edwards')}
            className={`px-3 py-1 text-sm rounded-md transition-colors ${mode === 'edwards' ? 'bg-white shadow text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}
          >
            Edwards
          </button>
          <button
            onClick={() => setMode('comparison')}
            className={`px-3 py-1 text-sm rounded-md transition-colors ${mode === 'comparison' ? 'bg-white shadow text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}
          >
            Comparaison
          </button>
        </div>
      </div>

      {/* Métriques de charge */}
      {mode === 'comparison' ? (
        <div className={`grid grid-cols-1 ${rhrDelta7d !== undefined ? 'md:grid-cols-4' : 'md:grid-cols-3'} gap-4`}>
          {/* Charge Chronique - Comparaison */}
          <div className="bg-white p-4 rounded-lg border">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Charge Chronique (42j)</p>
                <div className="flex items-center space-x-3">
                  <div>
                    <p className="text-xs text-gray-400">Banister</p>
                    <p className="text-xl font-bold text-gray-900">{latestData.chronicLoad.toFixed(1)}</p>
                  </div>
                  <div className="text-gray-300">|</div>
                  <div>
                    <p className="text-xs text-gray-400">Edwards</p>
                    <p className="text-xl font-bold text-gray-900">{latestData.chronicLoadEdwards.toFixed(1)}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Charge Aiguë - Comparaison */}
          <div className="bg-white p-4 rounded-lg border">
            <div>
              <p className="text-sm font-medium text-gray-600">Charge Aiguë (7j)</p>
              <div className="flex items-center space-x-3">
                <div>
                  <p className="text-xs text-gray-400">Banister</p>
                  <p className="text-xl font-bold text-gray-900">{latestData.acuteLoad.toFixed(1)}</p>
                </div>
                <div className="text-gray-300">|</div>
                <div>
                  <p className="text-xs text-gray-400">Edwards</p>
                  <p className="text-xl font-bold text-gray-900">{latestData.acuteLoadEdwards.toFixed(1)}</p>
                </div>
              </div>
            </div>
          </div>

          {/* TSB - Comparaison */}
          <div className="bg-white p-4 rounded-lg border">
            <div>
              <p className="text-sm font-medium text-gray-600">Équilibre d'Entraînement</p>
              <div className="flex items-center space-x-3">
                <div>
                  <p className="text-xs text-gray-400">Banister</p>
                  <p className="text-xl font-bold text-gray-900">{latestData.trainingStressBalance.toFixed(1)}</p>
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${tsbStatusBanister.color}`}>
                    {tsbStatusBanister.status}
                  </span>
                </div>
                <div className="text-gray-300">|</div>
                <div>
                  <p className="text-xs text-gray-400">Edwards</p>
                  <p className="text-xl font-bold text-gray-900">{latestData.tsbEdwards.toFixed(1)}</p>
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${tsbStatusEdwards.color}`}>
                    {tsbStatusEdwards.status}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Delta RHR 7j */}
          {rhrDelta7d !== undefined && (
            <div className="bg-white p-4 rounded-lg border">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">Delta RHR 7j</p>
                  <p className={`text-2xl font-bold ${rhrDelta7d > 0 ? 'text-red-600' : rhrDelta7d < 0 ? 'text-green-600' : 'text-gray-600'}`}>
                    {rhrDelta7d > 0 ? '+' : ''}{Math.round(rhrDelta7d)} bpm
                  </p>
                </div>
                <Heart className={`h-5 w-5 ${rhrDelta7d > 0 ? 'text-red-500' : rhrDelta7d < 0 ? 'text-green-500' : 'text-gray-500'}`} />
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className={`grid grid-cols-1 ${rhrDelta7d !== undefined ? 'md:grid-cols-4' : 'md:grid-cols-3'} gap-4`}>
          {/* Charge Chronique */}
          <div className="bg-white p-4 rounded-lg border">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Charge Chronique (42j)</p>
                <p className="text-2xl font-bold text-gray-900">
                  {mode === 'banister'
                    ? latestData.chronicLoad.toFixed(1)
                    : latestData.chronicLoadEdwards.toFixed(1)}
                </p>
              </div>
              <div className="flex items-center space-x-1">
                {getTrendIcon(mode === 'banister' ? chronicTrend : chronicTrendEdwards)}
                <span className={`text-sm font-medium ${getTrendColor(mode === 'banister' ? chronicTrend : chronicTrendEdwards)}`}>
                  {Math.abs(mode === 'banister' ? chronicTrend : chronicTrendEdwards).toFixed(1)}
                </span>
              </div>
            </div>
          </div>

          {/* Charge Aiguë */}
          <div className="bg-white p-4 rounded-lg border">
            <div>
              <p className="text-sm font-medium text-gray-600">Charge Aiguë (7j)</p>
              <p className="text-2xl font-bold text-gray-900">
                {mode === 'banister'
                  ? latestData.acuteLoad.toFixed(1)
                  : latestData.acuteLoadEdwards.toFixed(1)}
              </p>
            </div>
          </div>

          {/* Training Stress Balance */}
          <div className="bg-white p-4 rounded-lg border">
            <div>
              <p className="text-sm font-medium text-gray-600">Équilibre d'Entraînement</p>
              <p className="text-2xl font-bold text-gray-900">
                {mode === 'banister'
                  ? latestData.trainingStressBalance.toFixed(1)
                  : latestData.tsbEdwards.toFixed(1)}
              </p>
              <span className={`inline-flex px-2 py-1 rounded-full text-xs font-medium ${
                mode === 'banister' ? tsbStatusBanister.color : tsbStatusEdwards.color
              }`}>
                {mode === 'banister' ? tsbStatusBanister.status : tsbStatusEdwards.status}
              </span>
            </div>
          </div>

          {/* Delta RHR 7j */}
          {rhrDelta7d !== undefined && (
            <div className="bg-white p-4 rounded-lg border">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600">Delta RHR 7j</p>
                  <p className={`text-2xl font-bold ${rhrDelta7d > 0 ? 'text-red-600' : rhrDelta7d < 0 ? 'text-green-600' : 'text-gray-600'}`}>
                    {rhrDelta7d > 0 ? '+' : ''}{Math.round(rhrDelta7d)} bpm
                  </p>
                </div>
                <Heart className={`h-5 w-5 ${rhrDelta7d > 0 ? 'text-red-500' : rhrDelta7d < 0 ? 'text-green-500' : 'text-gray-500'}`} />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Graphique */}
      <div className="bg-white p-6 rounded-lg border">
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Évolution de la Charge d'Entraînement</h3>
          <p className="text-sm text-gray-600">{getSubtitle()}</p>
        </div>

        <AreaChart
          data={data}
          index="date"
          categories={chartConfig.categories}
          colors={chartConfig.colors}
          valueFormatter={(value: number) => value.toFixed(1)}
          showAnimation={true}
          showTooltip={true}
          showGrid={true}
        />

        {/* Légende */}
        <div className="flex justify-center flex-wrap gap-x-6 gap-y-2 mt-4 text-sm">
          {(mode === 'banister' || mode === 'comparison') && (
            <>
              <div className="flex items-center space-x-2">
                <div className="w-3 h-3 rounded-full bg-blue-500"></div>
                <span className="text-gray-600">CTL Banister (42j)</span>
              </div>
              <div className="flex items-center space-x-2">
                <div className="w-3 h-3 rounded-full bg-orange-500"></div>
                <span className="text-gray-600">ATL Banister (7j)</span>
              </div>
            </>
          )}
          {(mode === 'edwards' || mode === 'comparison') && (
            <>
              <div className="flex items-center space-x-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: 'hsl(160, 70%, 45%)' }}></div>
                <span className="text-gray-600">CTL Edwards (42j)</span>
              </div>
              <div className="flex items-center space-x-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: 'hsl(280, 60%, 55%)' }}></div>
                <span className="text-gray-600">ATL Edwards (7j)</span>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Explication */}
      {(mode === 'banister' || mode === 'comparison') && (
        <div className="bg-blue-50 p-4 rounded-lg">
          <h4 className="font-medium text-blue-900 mb-2">Modèle de Banister</h4>
          <div className="text-sm text-blue-800 space-y-1">
            <p><strong>Charge Chronique (CTL) :</strong> EWMA 42 jours (fitness)</p>
            <p><strong>Charge Aiguë (ATL) :</strong> EWMA 7 jours (fatigue)</p>
            <p><strong>TSB :</strong> CTL - ATL (équilibre d'entraînement)</p>
            <p className="mt-2 text-xs">
              TSB positif = Récupération | TSB négatif = Surmenage | TSB proche de 0 = Équilibre optimal
            </p>
          </div>
        </div>
      )}
      {(mode === 'edwards' || mode === 'comparison') && (
        <div className="bg-purple-50 p-4 rounded-lg">
          <h4 className="font-medium text-purple-900 mb-2">Modèle d'Edwards</h4>
          <div className="text-sm text-purple-800 space-y-1">
            <p><strong>TRIMP Edwards :</strong> Basé sur le temps passé dans 5 zones de fréquence cardiaque (%FCmax)</p>
            <p>Zone 1 (50-59%) ×1 | Zone 2 (60-69%) ×2 | Zone 3 (70-79%) ×3 | Zone 4 (80-89%) ×4 | Zone 5 (90-100%) ×5</p>
            <p className="mt-2 text-xs">
              Plus le temps en zones élevées est important, plus le TRIMP est élevé. Les moyennes CTL/ATL/TSB suivent le même principe EWMA.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
