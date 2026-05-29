import { useEffect, useMemo, useRef, type MutableRefObject, type ReactNode } from 'react';
import * as maptilersdk from '@maptiler/sdk';
import '@maptiler/sdk/dist/maptiler-sdk.css';
import { AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface RouteMapPoint {
  lat: number;
  lng: number;
}

export interface RouteMapTrack {
  id: string;
  color: string;
  points: RouteMapPoint[];
  opacity?: number;
  width?: number;
}

interface RouteMapTilerProps {
  tracks: RouteMapTrack[];
  focusedTrackId?: string | null;
  followLastPoint?: boolean;
  showEndpointMarkers?: boolean;
  className?: string;
  fallbackLabel?: string;
  fitPadding?: number;
}

interface NormalizedTrack {
  id: string;
  color: string;
  coords: [number, number][];
  opacity: number;
  width: number;
}

const ROUTE_PREFIX = 'agon-route-';

export default function RouteMapTiler({
  tracks,
  focusedTrackId = null,
  followLastPoint = false,
  showEndpointMarkers = true,
  className,
  fallbackLabel = 'En attente du premier point GPS...',
  fitPadding = 72,
}: RouteMapTilerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maptilersdk.Map | null>(null);
  const loadedRef = useRef(false);
  const fittedRef = useRef(false);
  const installedRef = useRef<Set<string>>(new Set());
  const markersRef = useRef<Map<string, maptilersdk.Marker>>(new Map());

  const apiKey = import.meta.env.VITE_MAPTILER_API_KEY as string | undefined;

  const normalizedTracks = useMemo<NormalizedTrack[]>(
    () =>
      tracks
        .map((track) => {
          const coords = track.points
            .filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lng))
            .map((point) => [point.lng, point.lat] as [number, number]);
          return {
            id: track.id,
            color: track.color,
            coords,
            opacity: track.opacity ?? 0.92,
            width: track.width ?? 4,
          };
        })
        .filter((track) => track.coords.length > 0),
    [tracks],
  );

  const trackSignature = normalizedTracks
    .map((track) => `${track.id}:${track.coords.length}`)
    .join('|');

  useEffect(() => {
    fittedRef.current = false;
  }, [trackSignature]);

  useEffect(() => {
    const markers = markersRef.current;
    const installedIds = installedRef.current;
    return () => {
      markers.forEach((marker) => marker.remove());
      markers.clear();
      installedIds.clear();
      loadedRef.current = false;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!apiKey || !containerRef.current || normalizedTracks.length === 0) return;

    maptilersdk.config.apiKey = apiKey;

    const firstCenter = resolveInitialCenter(normalizedTracks);
    if (!firstCenter) return;

    if (!mapRef.current) {
      const map = new maptilersdk.Map({
        container: containerRef.current,
        style: maptilersdk.MapStyle.OUTDOOR as unknown as string,
        center: firstCenter,
        zoom: 13,
        attributionControl: false,
      });

      mapRef.current = map;
      map.on('load', () => {
        loadedRef.current = true;
        applyTracks(map, normalizedTracks, installedRef.current, markersRef.current, showEndpointMarkers);
        positionMap(map, normalizedTracks, focusedTrackId, followLastPoint, fitPadding, fittedRef);
      });
      return;
    }

    const map = mapRef.current;
    if (!loadedRef.current) return;
    applyTracks(map, normalizedTracks, installedRef.current, markersRef.current, showEndpointMarkers);
    positionMap(map, normalizedTracks, focusedTrackId, followLastPoint, fitPadding, fittedRef);
  }, [apiKey, normalizedTracks, focusedTrackId, followLastPoint, showEndpointMarkers, fitPadding]);

  if (!apiKey) {
    return (
      <MapFallback
        className={className}
        icon={<AlertTriangle className="h-5 w-5 text-[var(--warning-fg)]" />}
        label="VITE_MAPTILER_API_KEY manquant"
      />
    );
  }

  if (normalizedTracks.length === 0) {
    return <MapFallback className={className} label={fallbackLabel} />;
  }

  return <div ref={containerRef} className={cn('h-full w-full', className)} />;
}

function applyTracks(
  map: maptilersdk.Map,
  tracks: NormalizedTrack[],
  installedIds: Set<string>,
  markers: Map<string, maptilersdk.Marker>,
  showEndpointMarkers: boolean,
) {
  const activeIds = new Set(tracks.map((track) => track.id));

  for (const id of Array.from(installedIds)) {
    if (!activeIds.has(id)) {
      const layerId = layerIdFor(id);
      const sourceId = sourceIdFor(id);
      if (map.getLayer(layerId)) map.removeLayer(layerId);
      if (map.getSource(sourceId)) map.removeSource(sourceId);
      installedIds.delete(id);
    }
  }

  for (const track of tracks) {
    const sourceId = sourceIdFor(track.id);
    const layerId = layerIdFor(track.id);
    const geojson: GeoJSON.Feature<GeoJSON.LineString> = {
      type: 'Feature',
      properties: {},
      geometry: { type: 'LineString', coordinates: track.coords },
    };

    if (!map.getSource(sourceId)) {
      map.addSource(sourceId, { type: 'geojson', data: geojson });
      map.addLayer({
        id: layerId,
        type: 'line',
        source: sourceId,
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': track.color,
          'line-width': track.width,
          'line-opacity': track.opacity,
        },
      });
      installedIds.add(track.id);
    } else {
      const source = map.getSource(sourceId) as maptilersdk.GeoJSONSource | undefined;
      source?.setData(geojson);
      map.setPaintProperty(layerId, 'line-color', track.color);
      map.setPaintProperty(layerId, 'line-width', track.width);
      map.setPaintProperty(layerId, 'line-opacity', track.opacity);
    }

    syncTrackMarkers(map, track, markers, showEndpointMarkers);
  }

  const activeMarkerIds = new Set<string>();
  tracks.forEach((track) => {
    activeMarkerIds.add(markerKey(track.id, 'cursor'));
    if (showEndpointMarkers) {
      activeMarkerIds.add(markerKey(track.id, 'start'));
      activeMarkerIds.add(markerKey(track.id, 'end'));
    }
  });

  for (const [id, marker] of Array.from(markers.entries())) {
    if (!activeMarkerIds.has(id)) {
      marker.remove();
      markers.delete(id);
    }
  }
}

function syncTrackMarkers(
  map: maptilersdk.Map,
  track: NormalizedTrack,
  markers: Map<string, maptilersdk.Marker>,
  showEndpointMarkers: boolean,
) {
  const first = track.coords[0];
  const last = track.coords[track.coords.length - 1];
  if (!first || !last) return;

  setMarker(map, markers, markerKey(track.id, 'cursor'), last, buildCursorMarker(track.color));

  if (showEndpointMarkers) {
    setMarker(map, markers, markerKey(track.id, 'start'), first, buildStaticMarker('#10B981'));
    setMarker(map, markers, markerKey(track.id, 'end'), last, buildStaticMarker('#EF4444'));
  }
}

function setMarker(
  map: maptilersdk.Map,
  markers: Map<string, maptilersdk.Marker>,
  key: string,
  coord: [number, number],
  markerFactory: () => HTMLElement,
) {
  const existing = markers.get(key);
  if (existing) {
    existing.setLngLat(coord);
    return;
  }
  const marker = new maptilersdk.Marker({ element: markerFactory() }).setLngLat(coord).addTo(map);
  markers.set(key, marker);
}

function positionMap(
  map: maptilersdk.Map,
  tracks: NormalizedTrack[],
  focusedTrackId: string | null,
  followLastPoint: boolean,
  fitPadding: number,
  fittedRef: MutableRefObject<boolean>,
) {
  const focusedTrack = focusedTrackId ? tracks.find((track) => track.id === focusedTrackId) : null;
  const focusCoord = focusedTrack?.coords[focusedTrack.coords.length - 1];

  if (followLastPoint && focusCoord) {
    map.easeTo({ center: focusCoord, duration: 600 });
    return;
  }

  if (!fittedRef.current) {
    fitMapToTracks(map, tracks, fitPadding);
    fittedRef.current = true;
  }
}

function fitMapToTracks(map: maptilersdk.Map, tracks: NormalizedTrack[], padding: number) {
  const allCoords = tracks.flatMap((track) => track.coords);
  if (allCoords.length === 0) return;
  if (allCoords.length === 1) {
    const coord = allCoords[0];
    if (coord) map.easeTo({ center: coord, zoom: 14, duration: 400 });
    return;
  }
  const bounds = new maptilersdk.LngLatBounds();
  allCoords.forEach((coord) => bounds.extend(coord));
  map.fitBounds(bounds, { padding, maxZoom: 16, duration: 500 });
}

function resolveInitialCenter(tracks: NormalizedTrack[]): [number, number] | null {
  const firstTrack = tracks[0];
  if (!firstTrack) return null;
  return firstTrack.coords[firstTrack.coords.length - 1] ?? firstTrack.coords[0] ?? null;
}

function sourceIdFor(id: string): string {
  return `${ROUTE_PREFIX}source-${safeId(id)}`;
}

function layerIdFor(id: string): string {
  return `${ROUTE_PREFIX}layer-${safeId(id)}`;
}

function markerKey(id: string, type: 'cursor' | 'start' | 'end'): string {
  return `${safeId(id)}-${type}`;
}

function safeId(id: string): string {
  return id.replace(/[^a-zA-Z0-9_-]/g, '_');
}

function buildCursorMarker(color: string): () => HTMLElement {
  return () => {
    ensurePulseStyles();
    const el = document.createElement('div');
    el.style.cssText =
      `width:17px;height:17px;background:${color};border:3px solid #f5efe0;` +
      `border-radius:999px;box-shadow:0 0 0 7px ${hexToRgba(color, 0.18)},0 10px 24px rgba(0,0,0,.38);position:relative;`;
    const pulse = document.createElement('span');
    pulse.style.cssText =
      `position:absolute;inset:-10px;border:2px solid ${color};border-radius:999px;` +
      'animation:agon-map-pulse 2.15s ease-out infinite;opacity:0;';
    el.appendChild(pulse);
    return el;
  };
}

function buildStaticMarker(color: string): () => HTMLElement {
  return () => {
    const el = document.createElement('div');
    el.style.cssText =
      `width:11px;height:11px;background:${color};border:2px solid #f5efe0;` +
      'border-radius:999px;box-shadow:0 6px 16px rgba(0,0,0,.36);';
    return el;
  };
}

function ensurePulseStyles() {
  if (document.getElementById('agon-map-pulse-style')) return;
  const style = document.createElement('style');
  style.id = 'agon-map-pulse-style';
  style.textContent = `@keyframes agon-map-pulse {
    0% { transform: scale(0.4); opacity: 0.72; }
    100% { transform: scale(1.7); opacity: 0; }
  }`;
  document.head.appendChild(style);
}

function hexToRgba(color: string, opacity: number): string {
  if (!color.startsWith('#') || (color.length !== 7 && color.length !== 4)) {
    return 'rgba(156,73,245,.18)';
  }
  const hex =
    color.length === 4
      ? `#${color[1]}${color[1]}${color[2]}${color[2]}${color[3]}${color[3]}`
      : color;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${opacity})`;
}

function MapFallback({
  className,
  label,
  icon,
}: {
  className?: string | undefined;
  label: string;
  icon?: ReactNode | undefined;
}) {
  return (
    <div className={cn('relative h-full w-full overflow-hidden bg-[#c2ae88]', className)}>
      <svg
        aria-hidden="true"
        viewBox="0 0 390 700"
        preserveAspectRatio="xMidYMid slice"
        className="absolute inset-0 h-full w-full"
      >
        <rect width="390" height="700" fill="#c2ae88" />
        <ellipse cx="300" cy="170" rx="92" ry="64" fill="#8fa068" opacity="0.3" />
        <ellipse cx="72" cy="365" rx="72" ry="88" fill="#8fa068" opacity="0.24" />
        <ellipse cx="196" cy="520" rx="112" ry="56" fill="#8fa068" opacity="0.2" />
        {[190, 160, 130, 100, 72, 46, 24].map((radius, index) => (
          <ellipse
            key={radius}
            cx="204"
            cy={202 - index * 2}
            rx={radius}
            ry={Math.max(14, radius * 0.68)}
            fill="none"
            stroke="#9a7a52"
            strokeWidth={index > 4 ? 1 : 0.75}
            opacity={0.42 + index * 0.055}
          />
        ))}
        <path
          d="M 28 548 Q 55 522 82 494 Q 112 462 140 432 Q 165 404 188 372 Q 212 338 240 300 Q 268 260 294 225 Q 316 198 338 178 Q 356 164 372 156"
          fill="none"
          stroke="#9C49F5"
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity="0.82"
        />
      </svg>
      <div className="absolute inset-0 bg-gradient-to-b from-[#0a0c08]/45 via-[#0a0c08]/10 to-[#0a0c08]/65" />
      <div className="absolute inset-x-8 top-1/2 z-10 -translate-y-1/2 rounded-[18px] border border-[var(--glass-panel-border)] bg-[var(--glass-panel)] px-4 py-4 text-center text-sm font-semibold text-[var(--glass-panel-fg)] backdrop-blur-xl">
        <div className="mb-2 flex justify-center">{icon}</div>
        {label}
      </div>
    </div>
  );
}
