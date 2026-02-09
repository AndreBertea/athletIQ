import { useRef, useEffect, useState, useCallback, useMemo } from 'react'
import * as maptilersdk from '@maptiler/sdk'
import '@maptiler/sdk/dist/maptiler-sdk.css'
import { ElevationProfileControl } from '@maptiler/elevation-profile-control'
import { buildGeoJSON3D, polylineToGeoJSON } from '../../utils/polylineDecode'
import { MapPin, AlertTriangle, Mountain, Satellite, Map, Moon } from 'lucide-react'

interface ActivityMapProps {
  polylineEncoded?: string
  streamsLatlng?: [number, number][] | { data?: [number, number][] }
  streamsAltitude?: number[] | { data?: number[] }
  startLatlng?: [number, number]
  endLatlng?: [number, number]
  isLoading?: boolean
}

interface MapStyleOption {
  id: string
  label: string
  style: string
  icon: typeof Mountain
}

const MAP_STYLES: MapStyleOption[] = [
  { id: 'outdoor', label: 'Outdoor', style: maptilersdk.MapStyle.OUTDOOR as unknown as string, icon: Mountain },
  { id: 'satellite', label: 'Satellite', style: maptilersdk.MapStyle.HYBRID as unknown as string, icon: Satellite },
  { id: 'streets', label: 'Streets', style: maptilersdk.MapStyle.STREETS as unknown as string, icon: Map },
  { id: 'dark', label: 'Dark', style: (maptilersdk.MapStyle.STREETS as any).DARK as string, icon: Moon },
]

export default function ActivityMap({
  polylineEncoded,
  streamsLatlng,
  streamsAltitude,
  startLatlng,
  endLatlng,
  isLoading = false,
}: ActivityMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null)
  const elevationContainer = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maptilersdk.Map | null>(null)
  const cursorMarkerRef = useRef<maptilersdk.Marker | null>(null)
  const startMarkerRef = useRef<maptilersdk.Marker | null>(null)
  const endMarkerRef = useRef<maptilersdk.Marker | null>(null)
  const geoJsonRef = useRef<GeoJSON.Feature<GeoJSON.LineString> | null>(null)
  const boundsRef = useRef<maptilersdk.LngLatBounds | null>(null)
  const [noData, setNoData] = useState(false)
  const [noApiKey, setNoApiKey] = useState(false)

  const isDark = document.documentElement.classList.contains('dark')
  const [currentStyle, setCurrentStyle] = useState(isDark ? 'dark' : 'outdoor')

  const normalizedLatlng = useMemo(() => {
    if (Array.isArray(streamsLatlng)) return streamsLatlng
    const data = streamsLatlng?.data
    return Array.isArray(data) ? data : []
  }, [streamsLatlng])

  const normalizedAltitude = useMemo(() => {
    if (Array.isArray(streamsAltitude)) return streamsAltitude
    const data = streamsAltitude?.data
    return Array.isArray(data) ? data : []
  }, [streamsAltitude])

  const hasCandidateData = normalizedLatlng.length > 0 || Boolean(polylineEncoded)
  const isWaitingForData = isLoading && !hasCandidateData

  // Coordonnees de depart/arrivee calculees a partir des donnees
  const coordsRef = useRef<{
    startCoord: [number, number]
    endCoord: [number, number]
  } | null>(null)

  const setupRouteAndMarkers = useCallback((map: maptilersdk.Map) => {
    if (!geoJsonRef.current || !coordsRef.current) return

    // Supprimer les anciens markers
    startMarkerRef.current?.remove()
    endMarkerRef.current?.remove()
    cursorMarkerRef.current?.remove()

    // Ajouter le trace GPS
    if (!map.getSource('route')) {
      map.addSource('route', {
        type: 'geojson',
        data: geoJsonRef.current,
      })
    }

    if (!map.getLayer('route-line')) {
      map.addLayer({
        id: 'route-line',
        type: 'line',
        source: 'route',
        layout: {
          'line-join': 'round',
          'line-cap': 'round',
        },
        paint: {
          'line-color': '#3b82f6',
          'line-width': 4,
          'line-opacity': 0.85,
        },
      })
    }

    const { startCoord, endCoord } = coordsRef.current

    // Marqueur de depart (vert)
    const sm = new maptilersdk.Marker({ color: '#22c55e' })
      .setLngLat(startCoord)
      .addTo(map)
    startMarkerRef.current = sm

    // Marqueur d'arrivee (rouge)
    const em = new maptilersdk.Marker({ color: '#ef4444' })
      .setLngLat(endCoord)
      .addTo(map)
    endMarkerRef.current = em

    // Marqueur curseur (bleu, avec pulse)
    const cursorEl = document.createElement('div')
    cursorEl.className = 'activity-map-cursor'
    cursorEl.style.cssText = 'width:16px;height:16px;background:#3b82f6;border:2px solid white;border-radius:50%;box-shadow:0 0 6px rgba(59,130,246,0.5);position:relative;'

    // Anneau de pulsation
    const pulseRing = document.createElement('div')
    pulseRing.style.cssText = 'position:absolute;top:-4px;left:-4px;width:24px;height:24px;border-radius:50%;border:2px solid #3b82f6;animation:cursor-pulse 2s ease-out infinite;opacity:0;'
    cursorEl.appendChild(pulseRing)

    const cursorMarker = new maptilersdk.Marker({ element: cursorEl })
      .setLngLat(startCoord)
      .addTo(map)
    cursorMarkerRef.current = cursorMarker

    // Fit bounds
    if (boundsRef.current) {
      map.fitBounds(boundsRef.current, { padding: 50 })
    }
  }, [])

  useEffect(() => {
    if (isWaitingForData) {
      setNoData(false)
      return
    }
    if (!hasCandidateData) {
      setNoData(true)
      return
    }
    setNoData(false)

    if (!mapContainer.current || !elevationContainer.current) return

    // Determiner les coordonnees GeoJSON
    let geoJsonCoords: [number, number][] | [number, number, number][] = []
    let geoJsonFeature: GeoJSON.Feature<GeoJSON.LineString>

    if (normalizedLatlng.length > 0) {
      geoJsonFeature = buildGeoJSON3D(normalizedLatlng, normalizedAltitude)
      geoJsonCoords = geoJsonFeature.geometry.coordinates as [number, number, number][]
    } else if (polylineEncoded) {
      geoJsonFeature = polylineToGeoJSON(polylineEncoded)
      geoJsonCoords = geoJsonFeature.geometry.coordinates as [number, number][]
    } else {
      setNoData(true)
      return
    }

    if (geoJsonCoords.length === 0) {
      setNoData(true)
      return
    }

    // Stocker le GeoJSON pour reutilisation apres changement de style
    geoJsonRef.current = geoJsonFeature

    // Configurer MapTiler
    const apiKey = (import.meta as any).env.VITE_MAPTILER_API_KEY || ''
    if (!apiKey) {
      setNoApiKey(true)
      return
    }
    maptilersdk.config.apiKey = apiKey

    // Calculer les coordonnees de depart/arrivee
    const startCoord: [number, number] = startLatlng
      ? [startLatlng[1], startLatlng[0]]
      : [geoJsonCoords[0][0], geoJsonCoords[0][1]]

    const endCoord: [number, number] = endLatlng
      ? [endLatlng[1], endLatlng[0]]
      : [geoJsonCoords[geoJsonCoords.length - 1][0], geoJsonCoords[geoJsonCoords.length - 1][1]]

    coordsRef.current = { startCoord, endCoord }

    // Calculer les bounds
    const bounds = new maptilersdk.LngLatBounds()
    geoJsonCoords.forEach((coord: number[]) => {
      bounds.extend([coord[0], coord[1]])
    })
    boundsRef.current = bounds

    // Trouver le style initial
    const initialStyleOption = MAP_STYLES.find(s => s.id === currentStyle)
    const initialStyle = initialStyleOption?.style || (isDark
      ? (maptilersdk.MapStyle.STREETS as any).DARK as string
      : maptilersdk.MapStyle.OUTDOOR as unknown as string)

    const map = new maptilersdk.Map({
      container: mapContainer.current,
      style: initialStyle,
      center: [geoJsonCoords[0][0], geoJsonCoords[0][1]],
      zoom: 12,
      terrain: true,
      pitch: 60,
    })
    mapRef.current = map

    // Injecter le CSS de pulsation
    if (!document.getElementById('cursor-pulse-style')) {
      const style = document.createElement('style')
      style.id = 'cursor-pulse-style'
      style.textContent = `
        @keyframes cursor-pulse {
          0% { transform: scale(1); opacity: 0.6; }
          100% { transform: scale(2.5); opacity: 0; }
        }
      `
      document.head.appendChild(style)
    }

    map.on('load', () => {
      setupRouteAndMarkers(map)

      // Profil de denivele
      try {
        const epc = new ElevationProfileControl({
          visible: true,
          container: elevationContainer.current!,
          unit: 'metric',
          profileLineColor: '#3b82f6',
          profileBackgroundColor: '#3b82f622',
          tooltipDisplayDPlus: true,
          tooltipDisplayGrade: true,
          tooltipDisplayDistance: true,
          tooltipDisplayElevation: true,
          displayElevationLabels: true,
          displayDistanceLabels: true,
          onMove: (data: any) => {
            if (data && cursorMarkerRef.current) {
              cursorMarkerRef.current.setLngLat([data.lng, data.lat])
              const el = cursorMarkerRef.current.getElement()
              if (el) el.style.display = 'block'
            }
          },
          onLeave: () => {
            if (cursorMarkerRef.current) {
              const el = cursorMarkerRef.current.getElement()
              if (el) el.style.display = 'none'
            }
          },
        })
        map.addControl(epc as any)
        epc.setData(geoJsonFeature as any)
      } catch (err) {
        console.warn('ElevationProfileControl error:', err)
      }
    })

    // Re-ajouter le trace apres un changement de style
    map.on('style.load', () => {
      // Le terrain doit etre re-active apres un changement de style
      try {
        map.setTerrain({ exaggeration: 1.2 })
      } catch {
        // Ignorer si le terrain n'est pas supporte pour ce style
      }

      setupRouteAndMarkers(map)
    })

    return () => {
      startMarkerRef.current?.remove()
      endMarkerRef.current?.remove()
      cursorMarkerRef.current?.remove()
      map.remove()
      mapRef.current = null
      cursorMarkerRef.current = null
      startMarkerRef.current = null
      endMarkerRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    isWaitingForData,
    hasCandidateData,
    normalizedLatlng,
    normalizedAltitude,
    polylineEncoded,
    startLatlng,
    endLatlng,
  ])

  const handleStyleChange = (styleId: string) => {
    setCurrentStyle(styleId)
    const map = mapRef.current
    if (!map) return

    const styleOption = MAP_STYLES.find(s => s.id === styleId)
    if (styleOption) {
      map.setStyle(styleOption.style)
    }
  }

  if (noApiKey) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-gray-500 dark:text-gray-400">
        <AlertTriangle className="h-8 w-8 mb-2 text-amber-500" />
        <p className="text-sm">Cle API MapTiler manquante (VITE_MAPTILER_API_KEY)</p>
      </div>
    )
  }

  if (isWaitingForData) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-gray-500 dark:text-gray-400">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500 mb-2" />
        <p className="text-sm">Chargement de la carte...</p>
      </div>
    )
  }

  if (noData) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-gray-500 dark:text-gray-400">
        <MapPin className="h-8 w-8 mb-2 text-gray-400 dark:text-gray-500" />
        <p className="text-sm">Pas de trace GPS disponible pour cette activite</p>
      </div>
    )
  }

  return (
    <div className="w-full bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      {/* Carte avec switcher overlay */}
      <div className="relative">
        <div
          ref={mapContainer}
          className="w-full"
          style={{ height: 'clamp(300px, 50vh, 400px)' }}
        />

        {/* Switcher de styles */}
        <div className="absolute top-3 right-3 flex bg-white dark:bg-gray-800 rounded-lg shadow-lg overflow-hidden border border-gray-200 dark:border-gray-600">
          {MAP_STYLES.map((s) => {
            const Icon = s.icon
            const isActive = currentStyle === s.id
            return (
              <button
                key={s.id}
                onClick={() => handleStyleChange(s.id)}
                title={s.label}
                className={`p-2 transition-colors ${
                  isActive
                    ? 'bg-blue-500 text-white'
                    : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                }`}
              >
                <Icon className="h-4 w-4" />
              </button>
            )
          })}
        </div>
      </div>

      {/* Profil de denivele */}
      <div
        ref={elevationContainer}
        className="w-full border-t border-gray-200 dark:border-gray-700"
        style={{ height: 'clamp(150px, 25vh, 200px)' }}
      />
    </div>
  )
}
