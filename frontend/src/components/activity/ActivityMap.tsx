import { useRef, useEffect, useState } from 'react'
import * as maptilersdk from '@maptiler/sdk'
import '@maptiler/sdk/dist/maptiler-sdk.css'
import { ElevationProfileControl } from '@maptiler/elevation-profile-control'
import { buildGeoJSON3D, polylineToGeoJSON } from '../../utils/polylineDecode'
import { MapPin } from 'lucide-react'

interface ActivityMapProps {
  polylineEncoded?: string
  streamsLatlng?: [number, number][]
  streamsAltitude?: number[]
  startLatlng?: [number, number]
  endLatlng?: [number, number]
}

export default function ActivityMap({
  polylineEncoded,
  streamsLatlng,
  streamsAltitude,
  startLatlng,
  endLatlng,
}: ActivityMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null)
  const elevationContainer = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maptilersdk.Map | null>(null)
  const cursorMarkerRef = useRef<maptilersdk.Marker | null>(null)
  const [noData, setNoData] = useState(false)

  useEffect(() => {
    if (!mapContainer.current || !elevationContainer.current) return

    // Déterminer les coordonnées GeoJSON
    let geoJsonCoords: [number, number][] | [number, number, number][] = []
    let geoJsonFeature: GeoJSON.Feature<GeoJSON.LineString>

    if (streamsLatlng && streamsLatlng.length > 0) {
      // Source 1 : streams latlng (plus précis)
      geoJsonFeature = buildGeoJSON3D(streamsLatlng, streamsAltitude)
      geoJsonCoords = geoJsonFeature.geometry.coordinates as [number, number, number][]
    } else if (polylineEncoded) {
      // Source 2 : polyline encodé
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

    // Configurer MapTiler
    maptilersdk.config.apiKey = (import.meta as any).env.VITE_MAPTILER_API_KEY || ''

    const map = new maptilersdk.Map({
      container: mapContainer.current,
      style: maptilersdk.MapStyle.OUTDOOR,
      center: [geoJsonCoords[0][0], geoJsonCoords[0][1]],
      zoom: 12,
    })
    mapRef.current = map

    map.on('load', () => {
      // Ajouter le tracé GPS
      map.addSource('route', {
        type: 'geojson',
        data: geoJsonFeature,
      })

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

      // Marqueur de départ (vert)
      const startCoord = startLatlng
        ? [startLatlng[1], startLatlng[0]] as [number, number]  // [lng, lat]
        : [geoJsonCoords[0][0], geoJsonCoords[0][1]] as [number, number]

      new maptilersdk.Marker({ color: '#22c55e' })
        .setLngLat(startCoord)
        .addTo(map)

      // Marqueur d'arrivée (rouge)
      const endCoord = endLatlng
        ? [endLatlng[1], endLatlng[0]] as [number, number]
        : [geoJsonCoords[geoJsonCoords.length - 1][0], geoJsonCoords[geoJsonCoords.length - 1][1]] as [number, number]

      new maptilersdk.Marker({ color: '#ef4444' })
        .setLngLat(endCoord)
        .addTo(map)

      // Marqueur curseur (bleu, pour sync avec profil)
      const cursorEl = document.createElement('div')
      cursorEl.style.cssText = 'width:12px;height:12px;background:#3b82f6;border:2px solid white;border-radius:50%;box-shadow:0 0 4px rgba(0,0,0,0.3);'
      const cursorMarker = new maptilersdk.Marker({ element: cursorEl })
        .setLngLat(startCoord)
        .addTo(map)
      cursorMarkerRef.current = cursorMarker

      // Fit bounds
      const bounds = new maptilersdk.LngLatBounds()
      geoJsonCoords.forEach((coord: number[]) => {
        bounds.extend([coord[0], coord[1]])
      })
      map.fitBounds(bounds, { padding: 50 })

      // Profil de dénivelé
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
            }
          },
        })
        map.addControl(epc as any)
        epc.setData(geoJsonFeature as any)
      } catch (err) {
        console.warn('ElevationProfileControl error:', err)
      }
    })

    return () => {
      map.remove()
      mapRef.current = null
      cursorMarkerRef.current = null
    }
  }, [streamsLatlng, streamsAltitude, polylineEncoded, startLatlng, endLatlng])

  if (noData) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-gray-500 dark:text-gray-400">
        <MapPin className="h-8 w-8 mb-2 text-gray-400 dark:text-gray-500" />
        <p className="text-sm">Pas de tracé GPS disponible pour cette activité</p>
      </div>
    )
  }

  return (
    <div className="w-full bg-white dark:bg-gray-900 rounded-lg border overflow-hidden">
      {/* Carte */}
      <div
        ref={mapContainer}
        className="w-full"
        style={{ height: 'clamp(300px, 50vh, 400px)' }}
      />
      {/* Profil de dénivelé */}
      <div
        ref={elevationContainer}
        className="w-full border-t"
        style={{ height: 'clamp(150px, 25vh, 200px)' }}
      />
    </div>
  )
}
