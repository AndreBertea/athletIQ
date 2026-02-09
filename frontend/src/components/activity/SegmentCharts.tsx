// @ts-expect-error: Types manquants pour react-plotly.js
import Plot from 'react-plotly.js'
import { Heart, Mountain, Gauge, Zap, Target } from 'lucide-react'
import type { SegmentWithFeatures } from '../../services/segmentService'

interface SegmentChartsProps {
  segments: SegmentWithFeatures[]
}

const plotlyLayout = {
  margin: { t: 20, r: 20, b: 40, l: 50 },
  height: 250,
  showlegend: false,
  font: { family: 'Inter, system-ui, sans-serif', size: 12 },
  plot_bgcolor: 'rgba(0,0,0,0)',
  paper_bgcolor: 'rgba(0,0,0,0)',
}
const plotlyConfig = { displayModeBar: false, responsive: true }

function getPaceColor(pace: number | null): string {
  if (pace === null) return '#9ca3af'
  if (pace < 4.5) return '#22c55e'
  if (pace < 5.5) return '#3b82f6'
  if (pace < 6.5) return '#f97316'
  return '#ef4444'
}

export default function SegmentCharts({ segments }: SegmentChartsProps) {
  const distAxis = segments.map(
    s => s.features?.cumulative_distance_km ?? s.segment.distance_m / 1000
  )

  // --- 1. Pace par segment ---
  const paceData = segments.map(s => s.segment.pace_min_per_km)
  const paceColors = paceData.map(p => getPaceColor(p))
  const paceHoverText = segments.map((s, i) =>
    `Segment #${i + 1} • Pace: ${s.segment.pace_min_per_km?.toFixed(2) ?? '—'} min/km • Distance: ${distAxis[i].toFixed(2)} km`
  )

  // --- 2. FC + Cadence ---
  const hrData = segments.map(s => s.segment.avg_hr)
  const cadenceData = segments.map(s => s.segment.avg_cadence !== null ? s.segment.avg_cadence * 2 : null)
  const hasHr = hrData.some(v => v !== null)
  const hasCadence = cadenceData.some(v => v !== null)

  // --- 3. Profil altimétrique ---
  const altData = segments.map(s => s.segment.altitude_m)
  const hasAlt = altData.some(v => v !== null)

  // --- 4. Features avancées ---
  const effData = segments.map(s => s.features?.efficiency_factor ?? null)
  const minettiData = segments.map(s => s.features?.minetti_cost ?? null)
  const hasEff = effData.some(v => v !== null)
  const hasMinetti = minettiData.some(v => v !== null)

  // --- 5. Race completion vs Pace ---
  const raceCompData = segments.map(s => s.features?.race_completion_pct ?? null)
  const hasRaceComp = raceCompData.some(v => v !== null)

  return (
    <div className="space-y-4">
      {/* Graphique 1 — Pace par segment */}
      <div className="bg-white rounded-lg border">
        <div className="flex items-center p-3 border-b">
          <Target className="h-4 w-4 mr-2 text-blue-500" />
          <span className="text-sm font-medium text-gray-900">Allure par segment</span>
        </div>
        <div className="p-2">
          <Plot
            data={[{
              x: distAxis,
              y: paceData,
              type: 'bar',
              marker: { color: paceColors },
              text: paceHoverText,
              hoverinfo: 'text',
            }]}
            layout={{
              ...plotlyLayout,
              xaxis: { title: 'Distance (km)' },
              yaxis: { title: 'Allure (min/km)', autorange: 'reversed' },
            }}
            config={plotlyConfig}
            style={{ width: '100%' }}
          />
        </div>
      </div>

      {/* Graphique 2 — FC + Cadence */}
      {(hasHr || hasCadence) && (
        <div className="bg-white rounded-lg border">
          <div className="flex items-center p-3 border-b">
            <Heart className="h-4 w-4 mr-2 text-red-500" />
            <span className="text-sm font-medium text-gray-900">Fréquence cardiaque & Cadence</span>
          </div>
          <div className="p-2">
            <Plot
              data={[
                ...(hasHr ? [{
                  x: distAxis,
                  y: hrData,
                  type: 'scatter' as const,
                  mode: 'lines+markers' as const,
                  name: 'FC (bpm)',
                  line: { color: '#ef4444', width: 2 },
                  marker: { size: 4 },
                  hovertemplate: '<b>%{y:.0f} bpm</b><br>Distance: %{x:.2f} km<extra></extra>',
                }] : []),
                ...(hasCadence ? [{
                  x: distAxis,
                  y: cadenceData,
                  type: 'scatter' as const,
                  mode: 'lines+markers' as const,
                  name: 'Cadence (ppm)',
                  line: { color: '#8b5cf6', width: 2 },
                  marker: { size: 4 },
                  yaxis: 'y2' as const,
                  hovertemplate: '<b>%{y:.0f} ppm</b><br>Distance: %{x:.2f} km<extra></extra>',
                }] : []),
              ]}
              layout={{
                ...plotlyLayout,
                showlegend: true,
                legend: { orientation: 'h', y: 1.15 },
                xaxis: { title: 'Distance (km)' },
                yaxis: { title: 'FC (bpm)', side: 'left' },
                ...(hasCadence ? { yaxis2: { title: 'Cadence (ppm)', overlaying: 'y', side: 'right' } } : {}),
              }}
              config={plotlyConfig}
              style={{ width: '100%' }}
            />
          </div>
        </div>
      )}

      {/* Graphique 3 — Profil altimétrique */}
      {hasAlt && (
        <div className="bg-white rounded-lg border">
          <div className="flex items-center p-3 border-b">
            <Mountain className="h-4 w-4 mr-2 text-emerald-500" />
            <span className="text-sm font-medium text-gray-900">Profil altimétrique</span>
          </div>
          <div className="p-2">
            <Plot
              data={[{
                x: distAxis,
                y: altData,
                type: 'scatter',
                mode: 'lines',
                fill: 'tozeroy',
                line: { color: '#10b981', width: 2 },
                fillcolor: 'rgba(16, 185, 129, 0.15)',
                hovertemplate: '<b>%{y:.0f} m</b><br>Distance: %{x:.2f} km<extra></extra>',
              }]}
              layout={{
                ...plotlyLayout,
                xaxis: { title: 'Distance (km)' },
                yaxis: { title: 'Altitude (m)' },
              }}
              config={plotlyConfig}
              style={{ width: '100%' }}
            />
          </div>
        </div>
      )}

      {/* Graphique 4 — Features avancées */}
      {(hasEff || hasMinetti) && (
        <div className="bg-white rounded-lg border">
          <div className="flex items-center p-3 border-b">
            <Zap className="h-4 w-4 mr-2 text-amber-500" />
            <span className="text-sm font-medium text-gray-900">Features avancées</span>
          </div>
          <div className="p-2">
            <Plot
              data={[
                ...(hasEff ? [{
                  x: distAxis,
                  y: effData,
                  type: 'scatter' as const,
                  mode: 'lines+markers' as const,
                  name: 'Efficiency Factor',
                  line: { color: '#3b82f6', width: 2 },
                  marker: { size: 4 },
                  hovertemplate: '<b>EF: %{y:.4f}</b><br>Distance: %{x:.2f} km<extra></extra>',
                }] : []),
                ...(hasMinetti ? [{
                  x: distAxis,
                  y: minettiData,
                  type: 'scatter' as const,
                  mode: 'lines+markers' as const,
                  name: 'Coût Minetti',
                  line: { color: '#f97316', width: 2 },
                  marker: { size: 4 },
                  yaxis: 'y2' as const,
                  hovertemplate: '<b>Minetti: %{y:.2f}</b><br>Distance: %{x:.2f} km<extra></extra>',
                }] : []),
              ]}
              layout={{
                ...plotlyLayout,
                showlegend: true,
                legend: { orientation: 'h', y: 1.15 },
                xaxis: { title: 'Distance (km)' },
                yaxis: { title: 'Efficiency Factor', side: 'left' },
                ...(hasMinetti ? { yaxis2: { title: 'Coût Minetti', overlaying: 'y', side: 'right' } } : {}),
              }}
              config={plotlyConfig}
              style={{ width: '100%' }}
            />
          </div>
        </div>
      )}

      {/* Graphique 5 — Race completion vs Pace */}
      {hasRaceComp && (
        <div className="bg-white rounded-lg border">
          <div className="flex items-center p-3 border-b">
            <Gauge className="h-4 w-4 mr-2 text-indigo-500" />
            <span className="text-sm font-medium text-gray-900">Progression vs Allure</span>
          </div>
          <div className="p-2">
            <Plot
              data={[{
                x: raceCompData,
                y: paceData,
                type: 'scatter',
                mode: 'markers',
                marker: {
                  size: 8,
                  color: altData.map(a => a ?? 0),
                  colorscale: 'Viridis',
                  showscale: true,
                  colorbar: { title: 'Alt. (m)', thickness: 15 },
                },
                hovertemplate: '<b>Pace: %{y:.2f} min/km</b><br>Progression: %{x:.1%}<extra></extra>',
              }]}
              layout={{
                ...plotlyLayout,
                xaxis: { title: 'Progression course (%)', tickformat: '.0%' },
                yaxis: { title: 'Allure (min/km)', autorange: 'reversed' },
              }}
              config={plotlyConfig}
              style={{ width: '100%' }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
