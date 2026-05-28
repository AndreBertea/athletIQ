import { useMemo } from 'react';
import RouteMapTiler, { type RouteMapTrack } from '@/components/map/RouteMapTiler';
import type { LiveTrackpoint } from '@/lib/api/live';

export interface AthleteTrack {
  id: string;
  color: string;
  points: LiveTrackpoint[];
}

interface Props {
  tracks: AthleteTrack[];
  focusedId: string | null;
}

export default function LiveSharedMap({ tracks, focusedId }: Props) {
  const mapTracks = useMemo<RouteMapTrack[]>(
    () =>
      tracks.map((track) => ({
        id: track.id,
        color: track.color,
        width: focusedId == null || focusedId === track.id ? 4 : 2,
        opacity: focusedId == null || focusedId === track.id ? 0.9 : 0.22,
        points: track.points
          .filter((point) => point.lat != null && point.lng != null)
          .map((point) => ({
            lat: point.lat as number,
            lng: point.lng as number,
          })),
      })),
    [focusedId, tracks],
  );

  return (
    <RouteMapTiler
      tracks={mapTracks}
      focusedTrackId={focusedId}
      followLastPoint={focusedId != null}
      showEndpointMarkers={false}
      className="h-full w-full"
      fallbackLabel="En attente du premier point GPS..."
    />
  );
}
