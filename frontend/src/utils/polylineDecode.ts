import polyline from '@mapbox/polyline'

/**
 * Décode une Google Encoded Polyline et la convertit en GeoJSON LineString.
 * Strava fournit des coordonnées en [lat, lng], mais GeoJSON attend [lng, lat].
 */
export function decodePolyline(encoded: string): [number, number][] {
  // polyline.decode retourne [lat, lng][]
  const decoded = polyline.decode(encoded)
  // Inverser en [lng, lat] pour GeoJSON
  return decoded.map(([lat, lng]: [number, number]) => [lng, lat])
}

export function polylineToGeoJSON(encoded: string): GeoJSON.Feature<GeoJSON.LineString> {
  const coordinates = decodePolyline(encoded)
  return {
    type: 'Feature',
    properties: {},
    geometry: {
      type: 'LineString',
      coordinates,
    },
  }
}

/**
 * Convertit un array de coordonnées [lat, lng][] (format Strava streams)
 * en coordonnées GeoJSON [lng, lat][].
 */
export function latlngToGeoJSONCoords(latlng: [number, number][]): [number, number][] {
  return latlng.map(([lat, lng]) => [lng, lat])
}

/**
 * Construit un GeoJSON LineString 3D à partir de latlng + altitude.
 * Les coordonnées 3D [lng, lat, alt] permettent à l'ElevationProfileControl
 * d'utiliser directement l'altitude sans requêter l'API MapTiler.
 */
export function buildGeoJSON3D(
  latlng: [number, number][],
  altitude?: number[]
): GeoJSON.Feature<GeoJSON.LineString> {
  const coordinates = latlng.map(([lat, lng], i) => {
    const alt = altitude && altitude[i] !== undefined ? altitude[i] : 0
    return [lng, lat, alt] as [number, number, number]
  })

  return {
    type: 'Feature',
    properties: {},
    geometry: {
      type: 'LineString',
      coordinates,
    },
  }
}
