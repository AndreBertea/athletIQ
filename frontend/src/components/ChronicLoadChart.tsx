import { useState } from 'react'
import {
  Area,
  AreaChart as RechartsAreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceLine,
  CartesianGrid,
} from 'recharts'
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Heart,
  Zap,
  Scale,
  Info,
  BarChart3,
} from 'lucide-react'

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

const MODEL_INFO: Record<LoadModel, { title: string; description: string }> = {
  banister: {
    title: 'Modèle de Banister',
    description: 'CTL = EWMA 42j (fitness) | ATL = EWMA 7j (fatigue) | TSB = CTL \u2212 ATL. Un TSB positif indique la fraîcheur, négatif la fatigue.',
  },
  edwards: {
    title: "Modèle d'Edwards",
    description: 'TRIMP basé sur le temps en 5 zones FC (%FCmax). Zone 1 ×1, Zone 2 ×2, Zone 3 ×3, Zone 4 ×4, Zone 5 ×5. Mêmes EWMA CTL/ATL/TSB.',
  },
  comparison: {
    title: 'Comparaison Banister vs Edwards',
    description: 'Les deux modèles côte à côte. Banister utilise la FC brute, Edwards pondère par zones.',
  },
}

const COLORS = {
  ctlBanister: '#3b82f6',
  atlBanister: '#f97316',
  tsbBanister: '#22c55e',
  ctlEdwards: '#8b5cf6',
  atlEdwards: '#ec4899',
  tsbEdwards: '#14b8a6',
}

const LABEL_MAP: Record<string, string> = {
  chronicLoad: 'CTL Banister',
  acuteLoad: 'ATL Banister',
  tsbBanister: 'TSB Banister',
  chronicLoadEdwards: 'CTL Edwards',
  acuteLoadEdwards: 'ATL Edwards',
  tsbEdwardsVal: 'TSB Edwards',
}

export default function ChronicLoadChart({ data, isLoading, rhrDelta7d }: ChronicLoadChartProps) {
  const [mode, setMode] = useState<LoadModel>('banister')
  const [showInfo, setShowInfo] = useState(false)

  if (isLoading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200/60 p-6">
        <div className="flex items-center justify-center py-12 text-gray-400">
          <div className="h-6 w-6 border-2 border-gray-200 border-t-blue-500 rounded-full animate-spin" />
          <span className="ml-3 text-sm">Calcul de la charge chronique...</span>
        </div>
      </div>
    )
  }

  if (!data || data.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-200/60 p-6">
        <div className="flex flex-col items-center justify-center py-12 text-gray-400">
          <BarChart3 className="h-10 w-10 mb-3 text-gray-300" />
          <p className="text-sm font-medium text-gray-500">Données insuffisantes</p>
          <p className="text-xs text-gray-400 mt-1">
            Au moins 42 jours d'activités sont nécessaires pour calculer la charge chronique
          </p>
        </div>
      </div>
    )
  }

  const latestData = data[data.length - 1]
  const previousData = data.length > 1 ? data[data.length - 2] : null

  const getMetrics = (m: 'banister' | 'edwards') => {
    const isBanister = m === 'banister'
    const ctl = isBanister ? latestData.chronicLoad : latestData.chronicLoadEdwards
    const atl = isBanister ? latestData.acuteLoad : latestData.acuteLoadEdwards
    const tsb = isBanister ? latestData.trainingStressBalance : latestData.tsbEdwards
    const ctlPrev = previousData
      ? (isBanister ? previousData.chronicLoad : previousData.chronicLoadEdwards)
      : ctl
    return { ctl, atl, tsb, ctlDelta: ctl - ctlPrev }
  }

  const getTSBStatus = (tsb: number) => {
    if (tsb > 10) return { label: 'Frais', className: 'bg-green-100 text-green-700' }
    if (tsb > 0) return { label: 'Forme', className: 'bg-emerald-100 text-emerald-700' }
    if (tsb > -10) return { label: 'Équilibre', className: 'bg-blue-100 text-blue-700' }
    if (tsb > -20) return { label: 'Fatigue', className: 'bg-orange-100 text-orange-700' }
    return { label: 'Surmenage', className: 'bg-red-100 text-red-700' }
  }

  const getTrendIcon = (delta: number) => {
    if (delta > 0.5) return <TrendingUp className="h-3.5 w-3.5 text-green-500" />
    if (delta < -0.5) return <TrendingDown className="h-3.5 w-3.5 text-red-500" />
    return <Minus className="h-3.5 w-3.5 text-gray-400" />
  }

  const chartData = data.map(d => ({
    ...d,
    tsbBanister: d.trainingStressBalance,
    tsbEdwardsVal: d.tsbEdwards,
  }))

  const getChartSeries = () => {
    switch (mode) {
      case 'banister':
        return [
          { key: 'chronicLoad', label: 'CTL Banister (42j)', color: COLORS.ctlBanister },
          { key: 'acuteLoad', label: 'ATL Banister (7j)', color: COLORS.atlBanister },
          { key: 'tsbBanister', label: 'TSB Banister', color: COLORS.tsbBanister },
        ]
      case 'edwards':
        return [
          { key: 'chronicLoadEdwards', label: 'CTL Edwards (42j)', color: COLORS.ctlEdwards },
          { key: 'acuteLoadEdwards', label: 'ATL Edwards (7j)', color: COLORS.atlEdwards },
          { key: 'tsbEdwardsVal', label: 'TSB Edwards', color: COLORS.tsbEdwards },
        ]
      case 'comparison':
        return [
          { key: 'chronicLoad', label: 'CTL Banister', color: COLORS.ctlBanister },
          { key: 'acuteLoad', label: 'ATL Banister', color: COLORS.atlBanister },
          { key: 'chronicLoadEdwards', label: 'CTL Edwards', color: COLORS.ctlEdwards },
          { key: 'acuteLoadEdwards', label: 'ATL Edwards', color: COLORS.atlEdwards },
        ]
    }
  }

  const series = getChartSeries()
  const modelInfo = MODEL_INFO[mode]

  const renderRhrCard = () => {
    if (rhrDelta7d === undefined) return null
    return (
      <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-2.5 rounded-lg ${rhrDelta7d > 0 ? 'bg-red-100' : 'bg-green-100'}`}>
              <Heart className={`h-5 w-5 ${rhrDelta7d > 0 ? 'text-red-600' : 'text-green-600'}`} />
            </div>
            <div>
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Delta RHR 7j</p>
              <p className={`text-2xl font-bold ${rhrDelta7d > 0 ? 'text-red-600' : rhrDelta7d < 0 ? 'text-green-600' : 'text-gray-600'}`}>
                {rhrDelta7d > 0 ? '+' : ''}{Math.round(rhrDelta7d)}
                <span className="text-sm font-normal text-gray-400 ml-1">bpm</span>
              </p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const renderMetricCards = () => {
    const hasRhr = rhrDelta7d !== undefined

    if (mode === 'comparison') {
      const banister = getMetrics('banister')
      const edwards = getMetrics('edwards')
      const tsbStatusB = getTSBStatus(banister.tsb)
      const tsbStatusE = getTSBStatus(edwards.tsb)

      return (
        <div className={`grid grid-cols-1 md:grid-cols-3 ${hasRhr ? 'xl:grid-cols-4' : ''} gap-4 mb-5`}>
          <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
            <div className="flex items-center gap-2 mb-3">
              <div className="p-2 rounded-lg bg-blue-100">
                <TrendingUp className="h-4 w-4 text-blue-600" />
              </div>
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Fitness (42j)</p>
            </div>
            <div className="flex items-center gap-4">
              <div>
                <p className="text-[10px] text-gray-400 uppercase">Banister</p>
                <p className="text-lg font-bold text-gray-900">{banister.ctl.toFixed(1)}</p>
              </div>
              <div className="h-8 w-px bg-gray-200" />
              <div>
                <p className="text-[10px] text-gray-400 uppercase">Edwards</p>
                <p className="text-lg font-bold text-gray-900">{edwards.ctl.toFixed(1)}</p>
              </div>
            </div>
          </div>

          <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
            <div className="flex items-center gap-2 mb-3">
              <div className="p-2 rounded-lg bg-orange-100">
                <Zap className="h-4 w-4 text-orange-600" />
              </div>
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Fatigue (7j)</p>
            </div>
            <div className="flex items-center gap-4">
              <div>
                <p className="text-[10px] text-gray-400 uppercase">Banister</p>
                <p className="text-lg font-bold text-gray-900">{banister.atl.toFixed(1)}</p>
              </div>
              <div className="h-8 w-px bg-gray-200" />
              <div>
                <p className="text-[10px] text-gray-400 uppercase">Edwards</p>
                <p className="text-lg font-bold text-gray-900">{edwards.atl.toFixed(1)}</p>
              </div>
            </div>
          </div>

          <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
            <div className="flex items-center gap-2 mb-3">
              <div className="p-2 rounded-lg bg-emerald-100">
                <Scale className="h-4 w-4 text-emerald-600" />
              </div>
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Form (TSB)</p>
            </div>
            <div className="flex items-center gap-4">
              <div>
                <p className="text-[10px] text-gray-400 uppercase">Banister</p>
                <p className="text-lg font-bold text-gray-900">{banister.tsb.toFixed(1)}</p>
                <span className={`inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium ${tsbStatusB.className}`}>
                  {tsbStatusB.label}
                </span>
              </div>
              <div className="h-8 w-px bg-gray-200" />
              <div>
                <p className="text-[10px] text-gray-400 uppercase">Edwards</p>
                <p className="text-lg font-bold text-gray-900">{edwards.tsb.toFixed(1)}</p>
                <span className={`inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium ${tsbStatusE.className}`}>
                  {tsbStatusE.label}
                </span>
              </div>
            </div>
          </div>

          {renderRhrCard()}
        </div>
      )
    }

    const metrics = getMetrics(mode)
    const tsbStatus = getTSBStatus(metrics.tsb)

    return (
      <div className={`grid grid-cols-1 md:grid-cols-3 ${hasRhr ? 'xl:grid-cols-4' : ''} gap-4 mb-5`}>
        <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-lg bg-blue-100">
                <TrendingUp className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Fitness (42j)</p>
                <p className="text-2xl font-bold text-gray-900">{metrics.ctl.toFixed(1)}</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              {getTrendIcon(metrics.ctlDelta)}
              <span className={`text-xs font-medium ${metrics.ctlDelta > 0.5 ? 'text-green-600' : metrics.ctlDelta < -0.5 ? 'text-red-600' : 'text-gray-400'}`}>
                {Math.abs(metrics.ctlDelta).toFixed(1)}
              </span>
            </div>
          </div>
        </div>

        <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-orange-100">
              <Zap className="h-5 w-5 text-orange-600" />
            </div>
            <div>
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Fatigue (7j)</p>
              <p className="text-2xl font-bold text-gray-900">{metrics.atl.toFixed(1)}</p>
            </div>
          </div>
        </div>

        <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-emerald-100">
              <Scale className="h-5 w-5 text-emerald-600" />
            </div>
            <div>
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Form (TSB)</p>
              <p className="text-2xl font-bold text-gray-900">{metrics.tsb.toFixed(1)}</p>
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${tsbStatus.className}`}>
                {tsbStatus.label}
              </span>
            </div>
          </div>
        </div>

        {renderRhrCard()}
      </div>
    )
  }

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload || payload.length === 0) return null
    return (
      <div className="bg-white rounded-lg border border-gray-200 shadow-lg p-3 text-sm">
        <p className="text-xs font-medium text-gray-500 mb-2">{label}</p>
        <div className="space-y-1">
          {payload.map((entry: any) => (
            <div key={entry.dataKey} className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: entry.color }} />
                <span className="text-gray-600">{LABEL_MAP[entry.dataKey] || entry.dataKey}</span>
              </div>
              <span className="font-semibold text-gray-900">{Number(entry.value).toFixed(1)}</span>
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200/60 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-blue-500" />
          <h3 className="text-base font-semibold text-gray-900">Charge d'Entraînement</h3>
          <div className="relative">
            <button
              className="text-gray-400 hover:text-gray-600 transition-colors"
              onMouseEnter={() => setShowInfo(true)}
              onMouseLeave={() => setShowInfo(false)}
              onClick={() => setShowInfo(!showInfo)}
            >
              <Info className="h-4 w-4" />
            </button>
            {showInfo && (
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-20">
                <div className="bg-gray-900 text-white text-xs rounded-lg px-3 py-2 shadow-lg max-w-xs w-64">
                  <p className="font-medium mb-1">{modelInfo.title}</p>
                  <p className="text-gray-300 leading-relaxed">{modelInfo.description}</p>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="inline-flex items-center bg-gray-100 rounded-lg p-1 gap-0.5">
          {(['banister', 'edwards', 'comparison'] as LoadModel[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200 ${
                mode === m
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {m === 'banister' ? 'Banister' : m === 'edwards' ? 'Edwards' : 'Comparaison'}
            </button>
          ))}
        </div>
      </div>

      {/* Metric Cards */}
      {renderMetricCards()}

      {/* Chart */}
      <div className="h-[350px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <RechartsAreaChart
            data={chartData}
            margin={{ top: 5, right: 10, left: 10, bottom: 0 }}
          >
            <defs>
              {series.map((s) => (
                <linearGradient key={s.key} id={`grad-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={s.color} stopOpacity={0.15} />
                  <stop offset="100%" stopColor={s.color} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: '#9ca3af' }}
              tickLine={false}
              axisLine={false}
              minTickGap={30}
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#9ca3af' }}
              tickLine={false}
              axisLine={false}
              width={45}
            />
            {mode !== 'comparison' && (
              <ReferenceLine y={0} stroke="#d1d5db" strokeDasharray="4 4" />
            )}
            <Tooltip content={<CustomTooltip />} />
            {series.map((s) => (
              <Area
                key={s.key}
                type="monotone"
                dataKey={s.key}
                stroke={s.color}
                strokeWidth={2}
                fill={`url(#grad-${s.key})`}
                isAnimationActive={true}
              />
            ))}
          </RechartsAreaChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div className="flex justify-center flex-wrap gap-x-5 gap-y-2 mt-4">
        {series.map((s) => (
          <div key={s.key} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: s.color }} />
            <span className="text-xs text-gray-500">{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
