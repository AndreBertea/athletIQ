// @ts-expect-error: Types manquants pour react-plotly.js
import Plot from 'react-plotly.js'
import type { LapData } from '../../services/activityService'

interface LapsTableProps {
  lapsData: LapData[] | null | undefined
}

function formatPace(paceMinPerKm: number): string {
  const minutes = Math.floor(paceMinPerKm)
  const seconds = Math.round((paceMinPerKm % 1) * 60)
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

function formatLapDuration(seconds: number): string {
  const min = Math.floor(seconds / 60)
  const sec = Math.round(seconds % 60)
  if (min >= 60) {
    const h = Math.floor(min / 60)
    const m = min % 60
    return `${h}h ${m}min`
  }
  return `${min}min ${String(sec).padStart(2, '0')}s`
}

function computePace(movingTime: number, distance: number): number | null {
  if (!distance || distance === 0) return null
  return (movingTime / 60) / (distance / 1000)
}

export default function LapsTable({ lapsData }: LapsTableProps) {
  if (!lapsData || lapsData.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 bg-gray-50 dark:bg-gray-800 rounded border-2 border-dashed border-gray-300 dark:border-gray-600">
        <span className="text-sm text-gray-500 dark:text-gray-400">Pas de données de tours disponibles</span>
      </div>
    )
  }

  // Calcul du pace par lap
  const lapPaces = lapsData.map(lap => computePace(lap.moving_time, lap.distance))

  // Pace moyen pondéré par la distance
  const totalDistance = lapsData.reduce((sum, lap) => sum + (lap.distance || 0), 0)
  const weightedPaceSum = lapsData.reduce((sum, lap, i) => {
    const pace = lapPaces[i]
    if (pace !== null && lap.distance > 0) {
      return sum + pace * lap.distance
    }
    return sum
  }, 0)
  const avgPace = totalDistance > 0 ? weightedPaceSum / totalDistance : null

  // Totaux
  const totalMovingTime = lapsData.reduce((sum, lap) => sum + (lap.moving_time || 0), 0)
  const totalElevation = lapsData.reduce((sum, lap) => sum + (lap.total_elevation_gain || 0), 0)
  const globalPace = computePace(totalMovingTime, totalDistance)
  const globalSpeed = totalMovingTime > 0 ? (totalDistance / totalMovingTime) * 3.6 : null

  const cadenceLaps = lapsData.filter(l => l.average_cadence != null)
  const avgCadence = cadenceLaps.length > 0
    ? cadenceLaps.reduce((sum, l) => sum + l.average_cadence! * 2, 0) / cadenceLaps.length
    : null

  const hrLaps = lapsData.filter(l => l.average_heartrate != null)
  const avgHr = hrLaps.length > 0
    ? hrLaps.reduce((sum, l) => sum + l.average_heartrate!, 0) / hrLaps.length
    : null

  const maxHrLaps = lapsData.filter(l => l.max_heartrate != null)
  const maxHr = maxHrLaps.length > 0
    ? Math.max(...maxHrLaps.map(l => l.max_heartrate!))
    : null

  // Colorisation par pace
  function getPaceRowClass(pace: number | null): string {
    if (pace === null || avgPace === null) return ''
    const lowerBound = avgPace * 0.9
    const upperBound = avgPace * 1.1
    if (pace < lowerBound) return 'bg-green-50 dark:bg-green-900/20'
    if (pace > upperBound) return 'bg-red-50 dark:bg-red-900/20'
    return ''
  }

  // Couleur pour le bar chart
  function getPaceBarColor(pace: number | null): string {
    if (pace === null || avgPace === null) return '#6b7280'
    const lowerBound = avgPace * 0.9
    const upperBound = avgPace * 1.1
    if (pace < lowerBound) return '#22c55e'
    if (pace > upperBound) return '#ef4444'
    return '#3b82f6'
  }

  // Données du bar chart
  const barChartData = [{
    x: lapsData.map((_, i) => `${i + 1}`),
    y: lapPaces.map(p => p ?? 0),
    type: 'bar' as const,
    marker: {
      color: lapPaces.map(p => getPaceBarColor(p))
    },
    hovertemplate: lapPaces.map((p, i) =>
      `Tour ${i + 1}<br>Allure: ${p !== null ? formatPace(p) : '—'} min/km<extra></extra>`
    ),
  }]

  const barChartLayout = {
    margin: { t: 20, r: 20, b: 40, l: 50 },
    height: 200,
    xaxis: {
      title: 'Tour',
      dtick: 1,
    },
    yaxis: {
      title: 'Allure (min/km)',
      autorange: 'reversed' as const,
      tickformat: '.1f',
    },
    showlegend: false,
    plot_bgcolor: 'rgba(0,0,0,0)',
    paper_bgcolor: 'rgba(0,0,0,0)',
    font: {
      family: 'Inter, system-ui, sans-serif',
      size: 12,
    },
  }

  const cellClass = 'px-3 py-2 text-sm text-gray-700 dark:text-gray-300 whitespace-nowrap'
  const headerClass = 'px-3 py-2 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider whitespace-nowrap'

  return (
    <div className="space-y-4">
      {/* Tableau des tours */}
      <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className={headerClass}>#</th>
              <th className={headerClass}>Distance</th>
              <th className={headerClass}>Temps</th>
              <th className={headerClass}>Allure</th>
              <th className={headerClass}>D+</th>
              <th className={headerClass}>Vitesse moy</th>
              <th className={headerClass}>Cadence</th>
              <th className={headerClass}>FC moy</th>
              <th className={headerClass}>FC max</th>
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
            {lapsData.map((lap, index) => {
              const pace = lapPaces[index]
              return (
                <tr key={index} className={getPaceRowClass(pace)}>
                  <td className={cellClass + ' font-medium'}>{index + 1}</td>
                  <td className={cellClass}>{lap.distance != null ? (lap.distance / 1000).toFixed(2) : '—'}</td>
                  <td className={cellClass}>{lap.moving_time != null ? formatLapDuration(lap.moving_time) : '—'}</td>
                  <td className={cellClass + ' font-medium'}>{pace !== null ? formatPace(pace) : '—'}</td>
                  <td className={cellClass}>{lap.total_elevation_gain != null ? Math.round(lap.total_elevation_gain) : '—'}</td>
                  <td className={cellClass}>{lap.average_speed != null ? (lap.average_speed * 3.6).toFixed(1) : '—'}</td>
                  <td className={cellClass}>{lap.average_cadence != null ? Math.round(lap.average_cadence * 2) : '—'}</td>
                  <td className={cellClass}>{lap.average_heartrate != null ? Math.round(lap.average_heartrate) : '—'}</td>
                  <td className={cellClass}>{lap.max_heartrate != null ? Math.round(lap.max_heartrate) : '—'}</td>
                </tr>
              )
            })}

            {/* Ligne Total */}
            <tr className="bg-gray-50 dark:bg-gray-800 font-bold border-t-2 border-gray-300 dark:border-gray-600">
              <td className={cellClass + ' font-bold'}>Total</td>
              <td className={cellClass + ' font-bold'}>{(totalDistance / 1000).toFixed(2)}</td>
              <td className={cellClass + ' font-bold'}>{formatLapDuration(totalMovingTime)}</td>
              <td className={cellClass + ' font-bold'}>{globalPace !== null ? formatPace(globalPace) : '—'}</td>
              <td className={cellClass + ' font-bold'}>{Math.round(totalElevation)}</td>
              <td className={cellClass + ' font-bold'}>{globalSpeed !== null ? globalSpeed.toFixed(1) : '—'}</td>
              <td className={cellClass + ' font-bold'}>{avgCadence !== null ? Math.round(avgCadence) : '—'}</td>
              <td className={cellClass + ' font-bold'}>{avgHr !== null ? Math.round(avgHr) : '—'}</td>
              <td className={cellClass + ' font-bold'}>{maxHr !== null ? Math.round(maxHr) : '—'}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Bar chart allure par tour */}
      <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Allure par tour</h4>
        <Plot
          data={barChartData}
          layout={barChartLayout}
          config={{ displayModeBar: false, responsive: true }}
          style={{ width: '100%' }}
        />
      </div>
    </div>
  )
}
