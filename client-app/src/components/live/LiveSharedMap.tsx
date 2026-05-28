import { useEffect, useRef } from 'react'
import * as maptilersdk from '@maptiler/sdk'
import '@maptiler/sdk/dist/maptiler-sdk.css'
import { AlertTriangle } from 'lucide-react'
import type { LiveTrackpoint } from '@/lib/api/live'

export interface AthleteTrack {
  /** Identifiant unique : on utilise session_id ou athlete_id */
  id: string
  color: string
  points: LiveTrackpoint[]
}

interface Props {
  tracks: AthleteTrack[]
  /** Id du track centre en focus (auto-pan dessus). Si null, pas de pan auto. */
  focusedId: string | null
}

const LAYER_PREFIX = 'shared-route-'

export default function LiveSharedMap({ tracks, focusedId }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maptilersdk.Map | null>(null)
  const cursorMarkersRef = useRef<Map<string, maptilersdk.Marker>>(new Map())
  const installedIdsRef = useRef<Set<string>>(new Set())
  const mapLoadedRef = useRef(false)

  // Cleanup au unmount
  useEffect(() => {
    return () => {
      if (mapRef.current) {
        mapRef.current.remove()
        mapRef.current = null
      }
      cursorMarkersRef.current.clear()
      installedIdsRef.current.clear()
      mapLoadedRef.current = false
    }
  }, [])

  // Init / Update map
  useEffect(() => {
    const apiKey = (import.meta as any).env?.VITE_MAPTILER_API_KEY
    if (!apiKey || !containerRef.current) return

    // Compute valid coords par track
    const allValidCoords: [number, number][] = []
    for (const t of tracks) {
      for (const p of t.points) {
        if (p.lat != null && p.lng != null) allValidCoords.push([p.lng, p.lat])
      }
    }
    if (allValidCoords.length === 0) return

    // 1. Init map
    if (!mapRef.current) {
      maptilersdk.config.apiKey = apiKey
      const isDark = document.documentElement.classList.contains('dark')
      const style = (isDark
        ? (maptilersdk.MapStyle.STREETS as any).DARK
        : maptilersdk.MapStyle.OUTDOOR) as unknown as string

      const map = new maptilersdk.Map({
        container: containerRef.current,
        style,
        center: allValidCoords[allValidCoords.length - 1],
        zoom: 13,
      })
      mapRef.current = map
      map.on('load', () => {
        mapLoadedRef.current = true
        applyTracks(map, tracks, installedIdsRef.current, cursorMarkersRef.current)
        fitToAllTracks(map, tracks)
      })
      return
    }

    // 2. Update (map deja chargee)
    const map = mapRef.current
    if (!mapLoadedRef.current) return

    applyTracks(map, tracks, installedIdsRef.current, cursorMarkersRef.current)
  }, [tracks])

  // Pan vers le focused track quand il bouge
  useEffect(() => {
    if (!focusedId || !mapRef.current || !mapLoadedRef.current) return
    const t = tracks.find((x) => x.id === focusedId)
    if (!t) return
    const last = lastValidPoint(t.points)
    if (!last) return
    mapRef.current.easeTo({ center: [last.lng!, last.lat!], duration: 600 })
  }, [focusedId, tracks])

  const apiKey = (import.meta as any).env?.VITE_MAPTILER_API_KEY
  if (!apiKey) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-sm text-gray-500 gap-2">
        <AlertTriangle className="h-5 w-5 text-yellow-500" />
        <span>VITE_MAPTILER_API_KEY manquant</span>
      </div>
    )
  }
  if (tracks.every((t) => t.points.length === 0)) {
    return (
      <div className="h-full flex items-center justify-center text-sm text-gray-500">
        En attente du premier point GPS...
      </div>
    )
  }

  return <div ref={containerRef} className="w-full h-full" />
}

// ---------- Helpers ----------

function applyTracks(
  map: maptilersdk.Map,
  tracks: AthleteTrack[],
  installedIds: Set<string>,
  cursorMarkers: Map<string, maptilersdk.Marker>,
): void {
  const currentIds = new Set(tracks.map((t) => t.id))

  // 1. Retirer les layers / markers obsoletes
  for (const id of Array.from(installedIds)) {
    if (!currentIds.has(id)) {
      const layerId = LAYER_PREFIX + id
      if (map.getLayer(layerId)) map.removeLayer(layerId)
      if (map.getSource(layerId)) map.removeSource(layerId)
      installedIds.delete(id)
      const m = cursorMarkers.get(id)
      if (m) {
        m.remove()
        cursorMarkers.delete(id)
      }
    }
  }

  // 2. Installer / updater les layers actifs
  for (const t of tracks) {
    const coords = t.points
      .filter((p) => p.lat != null && p.lng != null)
      .map((p) => [p.lng as number, p.lat as number] as [number, number])
    if (coords.length === 0) continue

    const layerId = LAYER_PREFIX + t.id
    const geojson: GeoJSON.Feature<GeoJSON.LineString> = {
      type: 'Feature',
      properties: {},
      geometry: { type: 'LineString', coordinates: coords },
    }

    if (!installedIds.has(t.id)) {
      map.addSource(layerId, { type: 'geojson', data: geojson })
      map.addLayer({
        id: layerId,
        type: 'line',
        source: layerId,
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: {
          'line-color': t.color,
          'line-width': 4,
          'line-opacity': 0.85,
        },
      })
      installedIds.add(t.id)
    } else {
      const src = map.getSource(layerId) as
        | maptilersdk.GeoJSONSource
        | undefined
      src?.setData(geojson)
      // Update color au cas ou
      map.setPaintProperty(layerId, 'line-color', t.color)
    }

    // Cursor marker (pin pulsant a la couleur du track)
    const last = coords[coords.length - 1]
    let cursor = cursorMarkers.get(t.id)
    if (!cursor) {
      cursor = buildCursorMarker(last, t.color)
      cursor.addTo(map)
      cursorMarkers.set(t.id, cursor)
    } else {
      cursor.setLngLat(last)
    }
  }
}

function fitToAllTracks(map: maptilersdk.Map, tracks: AthleteTrack[]): void {
  const allCoords: [number, number][] = []
  for (const t of tracks) {
    for (const p of t.points) {
      if (p.lat != null && p.lng != null) allCoords.push([p.lng, p.lat])
    }
  }
  if (allCoords.length === 0) return
  const bounds = new maptilersdk.LngLatBounds()
  allCoords.forEach((c) => bounds.extend(c))
  map.fitBounds(bounds, { padding: 60, maxZoom: 16 })
}

function buildCursorMarker(
  coord: [number, number],
  color: string,
): maptilersdk.Marker {
  const el = document.createElement('div')
  el.style.cssText =
    `width:16px;height:16px;background:${color};border:2px solid white;` +
    `border-radius:50%;box-shadow:0 0 8px ${color}99;position:relative;`
  const pulse = document.createElement('div')
  pulse.style.cssText =
    `position:absolute;top:-6px;left:-6px;width:28px;height:28px;` +
    `border-radius:50%;border:2px solid ${color};` +
    `animation:live-cursor-pulse 2s ease-out infinite;opacity:0;`
  el.appendChild(pulse)

  // L'animation CSS est injectee 1x par LiveMap.tsx mais on s'assure
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

function lastValidPoint(points: LiveTrackpoint[]) {
  for (let i = points.length - 1; i >= 0; i--) {
    if (points[i].lat != null && points[i].lng != null) return points[i]
  }
  return null
}
