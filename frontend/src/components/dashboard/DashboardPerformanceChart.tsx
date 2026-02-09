import { TrendingUp, BarChart3 } from 'lucide-react'
import { AreaChart } from '../ui/area-chart'

interface MetricOption {
  value: string
  label: string
  shortLabel: string
  formatter: (value: number) => string
}

interface ChartDataPoint {
  date: string
  distance: number
  duration: number
  pace: number
  elevation: number
}

interface DashboardPerformanceChartProps {
  chartData: ChartDataPoint[]
  selectedMetric: string
  onMetricChange: (metric: string) => void
  chartInterval: 'day' | 'week' | 'month'
  metricOptions: MetricOption[]
  isLoading: boolean
  selectedSportLabel?: string
}

const intervalLabels: Record<string, string> = {
  day: 'par jour',
  week: 'par semaine',
  month: 'par mois',
}

export default function DashboardPerformanceChart({
  chartData,
  selectedMetric,
  onMetricChange,
  chartInterval,
  metricOptions,
  isLoading,
  selectedSportLabel = 'Course à pied',
}: DashboardPerformanceChartProps) {
  const selectedMetricOption = metricOptions.find(opt => opt.value === selectedMetric)

  return (
    <div className="bg-white rounded-xl border border-gray-200/60 p-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-5">
        <div className="flex items-start gap-2.5">
          <div className="p-2 rounded-lg bg-orange-100 mt-0.5">
            <TrendingUp className="h-5 w-5 text-orange-600" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-gray-900">
              Évolution des performances
            </h3>
            <p className="text-sm text-gray-500 mt-0.5">
              {selectedSportLabel} — {intervalLabels[chartInterval]}
            </p>
          </div>
        </div>

        {/* Controles */}
        <div className="flex items-center gap-3 flex-wrap">
          {/* Toggle metrique */}
          <div className="inline-flex items-center bg-gray-100 rounded-lg p-1 gap-0.5">
            {metricOptions.map((opt) => (
              <button
                key={opt.value}
                onClick={() => onMetricChange(opt.value)}
                className={
                  selectedMetric === opt.value
                    ? 'px-3 py-1.5 text-xs font-medium rounded-md bg-white text-gray-900 shadow-sm transition-all duration-200'
                    : 'px-3 py-1.5 text-xs font-medium rounded-md text-gray-500 hover:text-gray-700 transition-all duration-200'
                }
              >
                {opt.shortLabel}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Chart area */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12 text-gray-400">
          <div className="h-6 w-6 border-2 border-gray-200 border-t-orange-500 rounded-full animate-spin" />
          <span className="ml-3 text-sm">Chargement...</span>
        </div>
      ) : chartData.length > 0 ? (
        <AreaChart
          data={chartData}
          index="date"
          categories={[selectedMetric]}
          colors={['#f97316']}
          valueFormatter={selectedMetricOption?.formatter || ((value: number) => value.toString())}
          showAnimation={true}
          showTooltip={true}
          showGrid={true}
          className="h-[280px]"
        />
      ) : (
        <div className="flex flex-col items-center justify-center py-12 text-gray-400">
          <BarChart3 className="h-10 w-10 mb-3 text-gray-300" />
          <p className="text-sm font-medium text-gray-500">Aucune donnée de performance</p>
          <p className="text-xs text-gray-400 mt-1">
            Commencez à vous entraîner pour voir vos tendances ici
          </p>
        </div>
      )}
    </div>
  )
}
