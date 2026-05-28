import { useEffect, useRef } from 'react'
import * as maptilersdk from '@maptiler/sdk'
import '@maptiler/sdk/dist/maptiler-sdk.css'
import { AlertTriangle } from 'lucide-react'
import type { LiveTrackpoint } from '@/lib/api/live'

interface Props {
  points: LiveTrackpoint[]
}

const ROUTE_SOURCE_ID = 'live-route'
const ROUTE_LAYER_ID = 'live-route-line'

export default function LiveMap({ points }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maptilersdk.Map | null>(null)
  const cursorMarkerRef = useRef<maptilersdk.Marker | null>(null)
  const startMarkerRef = useRef<maptilersdk.Marker | null>(null)
  const layerReadyRef = useRef(false)

  // Cleanup au unmount
  useEffect(() => {
    return () => {
      if (mapRef.current) {
        mapRef.current.remove()
        mapRef.current = null
      }
      cursorMarkerRef.current = null
      startMarkerRef.current = null
      layerReadyRef.current = false
    }
  }, [])

  // Init au premier point dispo, puis update a chaque changement
  useEffect(() => {
    const apiKey = (import.meta as any).env?.VITE_MAPTILER_API_KEY
    if (!apiKey || !containerRef.current) return

    const valid = points.filter(
      (p): p is LiveTrackpoint & { lat: number; lng: number } =>
        p.lat != null && p.lng != null,
    )
    if (valid.length === 0) return

    const coords = valid.map((p) => [p.lng, p.lat] as [number, number])
    const last = coords[coords.length - 1]
    const first = coords[0]

    // 1. Init map (lazy : seulement quand on a un premier point)
    if (!mapRef.current) {
      maptilersdk.config.apiKey = apiKey
      const isDark = document.documentElement.classList.contains('dark')
      const style = (isDark
        ? (maptilersdk.MapStyle.STREETS as any).DARK
        : maptilersdk.MapStyle.OUTDOOR) as unknown as string

      const map = new maptilersdk.Map({
        container: containerRef.current,
        style,
        center: last,
        zoom: 14,
      })
      mapRef.current = map

      map.on('load', () => {
        if (!mapRef.current) return
        installRouteLayer(map, coords)
        startMarkerRef.current = new maptilersdk.Marker({ color: '#22c55e' })
          .setLngLat(first)
          .addTo(map)
        cursorMarkerRef.current = buildCursorMarker(last).addTo(map)
        layerReadyRef.current = true
      })
      return
    }

    // 2. Update : la map existe, on rafraichit
    const map = mapRef.current
    if (!layerReadyRef.current) return

    // Update polyline source
    const src = map.getSource(ROUTE_SOURCE_ID) as
      | maptilersdk.GeoJSONSource
      | undefined
    if (src) {
      src.setData({
        type: 'Feature',
        properties: {},
        geometry: { type: 'LineString', coordinates: coords },
      } as GeoJSON.Feature<GeoJSON.LineString>)
    }
    // Move cursor + pan
    cursorMarkerRef.current?.setLngLat(last)
    if (!startMarkerRef.current) {
      startMarkerRef.current = new maptilersdk.Marker({ color: '#22c55e' })
        .setLngLat(first)
        .addTo(map)
    }
    map.easeTo({ center: last, duration: 500 })
  }, [points])

  const apiKey = (import.meta as any).env?.VITE_MAPTILER_API_KEY
  if (!apiKey) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-sm text-gray-500 gap-2">
        <AlertTriangle className="h-5 w-5 text-yellow-500" />
        <span>VITE_MAPTILER_API_KEY manquant dans frontend/.env</span>
      </div>
    )
  }
  if (points.filter((p) => p.lat != null && p.lng != null).length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-sm text-gray-500">
        En attente du premier point GPS...
      </div>
    )
  }

  return <div ref={containerRef} className="w-full h-full" />
}

function installRouteLayer(
  map: maptilersdk.Map,
  coords: [number, number][],
): void {
  if (!map.getSource(ROUTE_SOURCE_ID)) {
    map.addSource(ROUTE_SOURCE_ID, {
      type: 'geojson',
      data: {
        type: 'Feature',
        properties: {},
        geometry: { type: 'LineString', coordinates: coords },
      } as GeoJSON.Feature<GeoJSON.LineString>,
    })
  }
  if (!map.getLayer(ROUTE_LAYER_ID)) {
    map.addLayer({
      id: ROUTE_LAYER_ID,
      type: 'line',
      source: ROUTE_SOURCE_ID,
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: {
        'line-color': '#dc2626',
        'line-width': 4,
        'line-opacity': 0.85,
      },
    })
  }
}

function buildCursorMarker(coord: [number, number]): maptilersdk.Marker {
  // Pin bleu pulsant pour le point live
  const el = document.createElement('div')
  el.style.cssText =
    'width:16px;height:16px;background:#3b82f6;border:2px solid white;' +
    'border-radius:50%;box-shadow:0 0 8px rgba(59,130,246,0.6);position:relative;'
  const pulse = document.createElement('div')
  pulse.style.cssText =
    'position:absolute;top:-6px;left:-6px;width:28px;height:28px;' +
    'border-radius:50%;border:2px solid #3b82f6;' +
    'animation:live-cursor-pulse 2s ease-out infinite;opacity:0;'
  el.appendChild(pulse)

  // Inject l'animation CSS 1 fois
  if (!document.getElementById('live-cursor-pulse-style')) {
    const style = document.createElement('style')
    style.id = 'live-cursor-pulse-style'
    style.textContent = `@keyframes live-cursor-pulse {
      0% { transform: scale(0.5); opacity: 0.8; }
      100% { transform: scale(1.6); opacity: 0; }
    }`
    document.head.appendChild(style)
  }

  return new maptilersdk.Marker({ element: el }).setLngLat(coord)
}
