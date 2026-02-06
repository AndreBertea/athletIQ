// @ts-expect-error: Types manquants pour react-plotly.js
import Plot from 'react-plotly.js'
import { Heart } from 'lucide-react'
import PaceChart from './PaceChart'

interface HeartRateChartProps {
  timeData?: number[]
  heartrateData?: number[]
  distanceData?: number[]
  showMiniVersion?: boolean
}

export default function HeartRateChart({ 
  timeData, 
  heartrateData, 
  distanceData,
  showMiniVersion = false 
}: HeartRateChartProps) {
  // Vérifier que nous avons les données nécessaires
  if (!timeData || !heartrateData || timeData.length === 0 || heartrateData.length === 0) {
    return (
      <div className="flex items-center justify-center h-24 bg-gray-50 rounded border-2 border-dashed border-gray-300">
        <div className="text-center text-gray-500">
          <Heart className="h-4 w-4 mx-auto mb-1 opacity-50" />
          <span className="text-xs">Pas de données cardio</span>
        </div>
      </div>
    )
  }

  // Préparer les données pour le graphique
  const chartData = [{
    x: timeData.map(t => t / 60), // Convertir en minutes
    y: heartrateData,
    type: 'scatter',
    mode: 'lines',
    line: {
      color: '#ef4444', // Rouge pour la fréquence cardiaque
      width: showMiniVersion ? 1 : 2
    },
    name: 'Fréquence cardiaque',
    hovertemplate: '<b>%{y} bpm</b><br>Temps: %{x:.1f} min<extra></extra>'
  }]

  const layout = {
    margin: showMiniVersion 
      ? { t: 10, r: 10, b: 20, l: 30 }
      : { t: 20, r: 20, b: 40, l: 50 },
    height: showMiniVersion ? 80 : 200,
    xaxis: {
      title: showMiniVersion ? '' : 'Temps (min)',
      showgrid: !showMiniVersion,
      showticklabels: !showMiniVersion
    },
    yaxis: {
      title: showMiniVersion ? '' : 'BPM',
      showgrid: !showMiniVersion,
      showticklabels: !showMiniVersion
    },
    showlegend: false,
    font: { 
      family: 'Inter, system-ui, sans-serif',
      size: showMiniVersion ? 8 : 12
    },
    plot_bgcolor: 'rgba(0,0,0,0)',
    paper_bgcolor: 'rgba(0,0,0,0)'
  }

  const config = {
    displayModeBar: false,
    responsive: true
  }

  return (
    <div className="space-y-4">
      {/* Graphique de fréquence cardiaque */}
      <div className={showMiniVersion ? "w-full" : "w-full bg-white rounded-lg border"}>
        {!showMiniVersion && (
          <div className="flex items-center p-3 border-b">
            <Heart className="h-4 w-4 mr-2 text-red-500" />
            <span className="text-sm font-medium text-gray-900">Fréquence cardiaque</span>
            {heartrateData.length > 0 && (
              <span className="ml-auto text-xs text-gray-500">
                {Math.min(...heartrateData)}-{Math.max(...heartrateData)} bpm
              </span>
            )}
          </div>
        )}
        <div className={showMiniVersion ? "" : "p-2"}>
          <Plot
            data={chartData}
            layout={layout}
            config={config}
            style={{ width: '100%' }}
          />
        </div>
      </div>

      {/* Graphique de rythme de course */}
      {!showMiniVersion && distanceData && (
        <PaceChart
          timeData={timeData}
          distanceData={distanceData}
          showMiniVersion={false}
        />
      )}
    </div>
  )
} 