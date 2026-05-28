import { useMemo } from 'react';
import RouteMapTiler, { type RouteMapTrack } from '@/components/map/RouteMapTiler';
import type { LiveTrackpoint } from '@/lib/api/live';

interface Props {
  points: LiveTrackpoint[];
}

export default function LiveMap({ points }: Props) {
  const track = useMemo<RouteMapTrack>(
    () => ({
      id: 'live-session',
      color: '#A0432E',
      width: 4,
      points: points
        .filter((point) => point.lat != null && point.lng != null)
        .map((point) => ({
          lat: point.lat as number,
          lng: point.lng as number,
        })),
    }),
    [points],
  );

  return (
    <RouteMapTiler
      tracks={[track]}
      focusedTrackId="live-session"
      followLastPoint
      className="h-full w-full"
      fallbackLabel="En attente du premier point GPS..."
    />
  );
}
