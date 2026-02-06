// @ts-expect-error: Types manquants pour react-plotly.js
import Plot from 'react-plotly.js'
import { Clock } from 'lucide-react'

interface PaceChartProps {
  timeData?: number[]
  distanceData?: number[]
  showMiniVersion?: boolean
}

export default function PaceChart({ 
  timeData, 
  distanceData, 
  showMiniVersion = false 
}: PaceChartProps) {
  // Vérifier que nous avons les données nécessaires
  if (!timeData || !distanceData || timeData.length === 0 || distanceData.length === 0) {
    return (
      <div className="flex items-center justify-center h-24 bg-gray-50 rounded border-2 border-dashed border-gray-300">
        <div className="text-center text-gray-500">
          <Clock className="h-4 w-4 mx-auto mb-1 opacity-50" />
          <span className="text-xs">Pas de données de rythme</span>
        </div>
      </div>
    )
  }

  // Calculer le rythme (pace) en min/km
  const calculatePace = (timeData: number[], distanceData: number[]) => {
    const paceData: number[] = []
    
    for (let i = 1; i < timeData.length; i++) {
      const timeDiff = timeData[i] - timeData[i - 1] // en secondes
      const distanceDiff = distanceData[i] - distanceData[i - 1] // en mètres
      
      if (distanceDiff > 0 && timeDiff > 0) {
        // Convertir en min/km
        const paceMinPerKm = (timeDiff / 60) / (distanceDiff / 1000)
        
        // Exclure les données dépassant 20:00/km (erreurs de mesure)
        if (paceMinPerKm <= 20) {
          paceData.push(paceMinPerKm)
        } else {
          paceData.push(0) // Marquer comme invalide
        }
      } else {
        paceData.push(0)
      }
    }
    
    return paceData
  }

  const paceData = calculatePace(timeData, distanceData)
  
  // Convertir les données de temps en minutes pour l'affichage
  const timeInMinutes = timeData.map(t => t / 60)

  // Filtrer les données pour le graphique (exclure les valeurs nulles/invalides)
  const validIndices = paceData.map((pace, index) => pace > 0 && pace <= 20 ? index : -1).filter(index => index !== -1)
  
  const filteredTimeData = validIndices.map(index => timeInMinutes[index])
  const filteredPaceData = validIndices.map(index => paceData[index])

  // Préparer les données pour le graphique
  const chartData = [{
    x: filteredTimeData,
    y: filteredPaceData,
    type: 'scatter',
    mode: 'lines',
    line: {
      color: '#3b82f6', // Bleu pour le rythme
      width: showMiniVersion ? 1 : 2
    },
    name: 'Rythme de course',
    hovertemplate: '<b>%{customdata}</b><br>Temps: %{x:.1f} min<extra></extra>',
    customdata: filteredPaceData.map(pace => {
      const minutes = Math.floor(pace)
      const seconds = Math.round((pace - minutes) * 60)
      return `${minutes}:${seconds.toString().padStart(2, '0')}/km`
    })
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
      title: showMiniVersion ? '' : 'Rythme (min/km)',
      showgrid: !showMiniVersion,
      showticklabels: !showMiniVersion,
      tickformat: '.1f'
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

  // Calculer les statistiques du rythme (exclure les données invalides)
  const validPaces = paceData.filter(pace => pace > 0 && pace <= 20)
  const avgPace = validPaces.length > 0 ? validPaces.reduce((a, b) => a + b, 0) / validPaces.length : 0
  const minPace = validPaces.length > 0 ? Math.min(...validPaces) : 0
  const maxPace = validPaces.length > 0 ? Math.max(...validPaces) : 0

  const formatPace = (pace: number): string => {
    if (pace === 0) return 'N/A'
    const minutes = Math.floor(pace)
    const seconds = Math.round((pace - minutes) * 60)
    return `${minutes}:${seconds.toString().padStart(2, '0')}/km`
  }

  return (
    <div className={showMiniVersion ? "w-full" : "w-full bg-white rounded-lg border"}>
      {!showMiniVersion && (
        <div className="flex items-center p-3 border-b">
          <Clock className="h-4 w-4 mr-2 text-blue-500" />
          <span className="text-sm font-medium text-gray-900">Rythme de course</span>
          {validPaces.length > 0 && (
            <span className="ml-auto text-xs text-gray-500">
              {formatPace(minPace)} - {formatPace(maxPace)}
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
      {!showMiniVersion && validPaces.length > 0 && (
        <div className="px-3 pb-3">
          <div className="text-xs text-gray-600">
            Rythme moyen: <span className="font-medium">{formatPace(avgPace)}</span>
          </div>
        </div>
      )}
    </div>
  )
}
