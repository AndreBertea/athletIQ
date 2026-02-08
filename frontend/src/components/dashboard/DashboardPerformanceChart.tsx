import { AreaChart } from '../ui/area-chart'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'

interface MetricOption {
  value: string
  label: string
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
  onIntervalChange: (interval: 'day' | 'week' | 'month') => void
  metricOptions: MetricOption[]
  isLoading: boolean
}

export default function DashboardPerformanceChart({
  chartData,
  selectedMetric,
  onMetricChange,
  chartInterval,
  onIntervalChange,
  metricOptions,
  isLoading,
}: DashboardPerformanceChartProps) {
  const selectedMetricOption = metricOptions.find(opt => opt.value === selectedMetric)

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-medium text-gray-900">
          Évolution des performances - Course à pied
        </h3>
        <div className="flex items-center space-x-4">
          {/* Boutons d'intervalle J/S/M */}
          <div className="flex items-center space-x-1">
            {([
              { value: 'day', label: 'J' },
              { value: 'week', label: 'S' },
              { value: 'month', label: 'M' },
            ] as const).map((interval) => (
              <button
                key={interval.value}
                onClick={() => onIntervalChange(interval.value)}
                className={`px-2 py-1 text-xs rounded transition-colors ${
                  chartInterval === interval.value
                    ? 'bg-orange-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
                title={`Par ${interval.value === 'day' ? 'jour' : interval.value === 'week' ? 'semaine' : 'mois'}`}
              >
                {interval.label}
              </button>
            ))}
          </div>

          {/* Sélecteur de métrique */}
          <div className="flex items-center space-x-2">
            <label className="text-sm font-medium text-gray-700">Métrique :</label>
            <Select value={selectedMetric} onValueChange={onMetricChange}>
              <SelectTrigger className="w-[180px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {metricOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {/* Graphique */}
      {isLoading ? (
        <div className="h-64 flex items-center justify-center text-gray-500">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-orange-500 mr-3"></div>
          Chargement des données...
        </div>
      ) : chartData.length > 0 ? (
        <AreaChart
          data={chartData}
          index="date"
          categories={[selectedMetric]}
          colors={["hsl(var(--chart-1))"]}
          valueFormatter={selectedMetricOption?.formatter || ((value: number) => value.toString())}
          showAnimation={true}
          showTooltip={true}
          showGrid={true}
        />
      ) : (
        <div className="h-64 flex items-center justify-center text-gray-500 bg-gray-50 rounded-lg">
          <div className="text-center">
            <div className="text-4xl mb-2">🏃‍♂️</div>
            <p>Aucune activité de course trouvée pour cette période</p>
            <p className="text-sm text-gray-400 mt-1">
              Commencez à courir pour voir vos données ici !
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
