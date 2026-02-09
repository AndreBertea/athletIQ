import { Thermometer, Wind, Droplets, Cloud, Gauge } from 'lucide-react'
import type { ActivityWeather } from '../../services/dataService'

interface WeatherWidgetProps {
  weather: ActivityWeather
}

function weatherDescription(code: number | null): { label: string; colorClass: string } | null {
  if (code === null) return null
  if (code === 0) return { label: 'Clair', colorClass: 'text-yellow-500 dark:text-yellow-400' }
  if (code <= 3) return { label: 'Nuageux', colorClass: 'text-gray-500 dark:text-gray-400' }
  if (code >= 45 && code <= 48) return { label: 'Brouillard', colorClass: 'text-gray-400 dark:text-gray-500' }
  if (code >= 51 && code <= 57) return { label: 'Bruine', colorClass: 'text-blue-400 dark:text-blue-300' }
  if (code >= 61 && code <= 67) return { label: 'Pluie', colorClass: 'text-blue-600 dark:text-blue-400' }
  if (code >= 71 && code <= 77) return { label: 'Neige', colorClass: 'text-sky-300 dark:text-sky-200' }
  if (code >= 80 && code <= 82) return { label: 'Averses', colorClass: 'text-blue-500 dark:text-blue-400' }
  if (code >= 95 && code <= 99) return { label: 'Orage', colorClass: 'text-purple-600 dark:text-purple-400' }
  return null
}

function windDirectionLabel(deg: number): string {
  const dirs = ['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO']
  const index = Math.round(deg / 45) % 8
  return dirs[index]
}

export default function WeatherWidget({ weather }: WeatherWidgetProps) {
  const desc = weatherDescription(weather.weather_code)

  const metrics: Array<{
    label: string
    value: string
    icon: typeof Thermometer
    colorClass: string
  }> = []

  if (weather.temperature_c != null) {
    metrics.push({
      label: 'Température',
      value: `${weather.temperature_c.toFixed(1)}°C`,
      icon: Thermometer,
      colorClass: 'text-amber-600 dark:text-amber-400',
    })
  }

  if (weather.humidity_pct != null) {
    metrics.push({
      label: 'Humidité',
      value: `${weather.humidity_pct.toFixed(0)}%`,
      icon: Droplets,
      colorClass: 'text-blue-600 dark:text-blue-400',
    })
  }

  if (weather.wind_speed_kmh != null) {
    const dirStr = weather.wind_direction_deg != null
      ? ` ${windDirectionLabel(weather.wind_direction_deg)}`
      : ''
    metrics.push({
      label: 'Vent',
      value: `${weather.wind_speed_kmh.toFixed(0)} km/h${dirStr}`,
      icon: Wind,
      colorClass: 'text-cyan-600 dark:text-cyan-400',
    })
  }

  if (weather.pressure_hpa != null) {
    metrics.push({
      label: 'Pression',
      value: `${weather.pressure_hpa.toFixed(0)} hPa`,
      icon: Gauge,
      colorClass: 'text-gray-600 dark:text-gray-400',
    })
  }

  if (weather.precipitation_mm != null && weather.precipitation_mm > 0) {
    metrics.push({
      label: 'Précipitations',
      value: `${weather.precipitation_mm.toFixed(1)} mm`,
      icon: Cloud,
      colorClass: 'text-indigo-600 dark:text-indigo-400',
    })
  }

  if (weather.cloud_cover_pct != null) {
    metrics.push({
      label: 'Couverture nuageuse',
      value: `${weather.cloud_cover_pct.toFixed(0)}%`,
      icon: Cloud,
      colorClass: 'text-gray-500 dark:text-gray-400',
    })
  }

  if (metrics.length === 0) return null

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-3">
      {/* En-tête avec condition météo */}
      {desc && (
        <p className={`text-sm font-medium mb-2 ${desc.colorClass}`}>
          {desc.label}
        </p>
      )}

      {/* Grille de métriques */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-2">
        {metrics.map((m) => {
          const Icon = m.icon
          return (
            <div key={m.label} className="flex items-center gap-1.5">
              <Icon className={`h-3.5 w-3.5 ${m.colorClass} shrink-0`} />
              <span className="text-xs text-gray-500 dark:text-gray-400">{m.label}</span>
              <span className="text-xs font-medium text-gray-900 dark:text-gray-100 ml-auto">{m.value}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
