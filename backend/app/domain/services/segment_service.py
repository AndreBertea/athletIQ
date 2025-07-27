"""
Service de Segmentation - Domain Layer
Centralise la logique de segmentation répétée dans le code existant
"""
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Segment:
    """Représente un segment d'activité"""
    start_index: int
    end_index: int
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    distance: Optional[float] = None
    duration: Optional[float] = None


@dataclass
class LatLon:
    """Point GPS"""
    latitude: float
    longitude: float


class SegmentService:
    """
    Service unifié pour la segmentation d'activités
    Consolide la logique répétée dans visualizer.js, graph1.js, plotly_3D.py, etc.
    """
    
    def segment_by_pause(
        self, 
        time_series: List[float], 
        pause_threshold: int = 100,
        min_points: int = 30
    ) -> List[Segment]:
        """
        Découpe une activité en segments basés sur les pauses
        
        Args:
            time_series: Série temporelle (timestamps en secondes)
            pause_threshold: Seuil de pause en secondes (défaut: 100s comme dans le code existant)
            min_points: Nombre minimum de points pour garder un segment (défaut: 30)
            
        Returns:
            Liste des segments valides
        """
        if not time_series or len(time_series) < min_points:
            return []
        
        raw_segments = []
        start = 0
        
        for i in range(1, len(time_series)):
            time_gap = time_series[i] - time_series[i-1]
            if time_gap > pause_threshold:
                raw_segments.append((start, i))
                start = i
        
        # Ajouter le dernier segment
        raw_segments.append((start, len(time_series)))
        
        # Filtrer les segments trop courts
        valid_segments = []
        for start_idx, end_idx in raw_segments:
            if end_idx - start_idx >= min_points:
                segment = Segment(
                    start_index=start_idx,
                    end_index=end_idx,
                    start_time=time_series[start_idx],
                    end_time=time_series[end_idx - 1],
                    duration=time_series[end_idx - 1] - time_series[start_idx]
                )
                valid_segments.append(segment)
        
        return valid_segments
    
    def segment_by_distance(
        self, 
        distance_series: List[float],
        time_series: List[float],
        interval_km: float = 1.0
    ) -> List[Segment]:
        """
        Découpe une activité en segments de distance fixe (pour splits km)
        
        Args:
            distance_series: Distances cumulées en mètres
            time_series: Timestamps correspondants
            interval_km: Intervalle de distance en km (défaut: 1km)
            
        Returns:
            Liste des segments de distance
        """
        if not distance_series or not time_series:
            return []
        
        interval_meters = interval_km * 1000
        segments = []
        
        current_km = 1
        km_start_idx = 0
        
        for i in range(1, len(distance_series)):
            distance_from_start = distance_series[i] - distance_series[km_start_idx]
            
            if distance_from_start >= interval_meters or i == len(distance_series) - 1:
                segment = Segment(
                    start_index=km_start_idx,
                    end_index=i,
                    start_time=time_series[km_start_idx],
                    end_time=time_series[i],
                    distance=distance_from_start,
                    duration=time_series[i] - time_series[km_start_idx]
                )
                segments.append(segment)
                
                current_km += 1
                km_start_idx = i
        
        return segments
    
    def segment_by_laps(self, laps_data: List[Dict[str, Any]]) -> List[Segment]:
        """
        Convertit les données de tours Strava en segments
        
        Args:
            laps_data: Données de tours depuis l'API Strava
            
        Returns:
            Liste des segments correspondant aux tours
        """
        segments = []
        
        for i, lap in enumerate(laps_data):
            # Les données Strava peuvent varier, adaptation défensive
            start_index = lap.get('start_index', i * 100)  # Estimation si manquant
            end_index = lap.get('end_index', (i + 1) * 100)
            
            segment = Segment(
                start_index=start_index,
                end_index=end_index,
                distance=lap.get('distance', 0.0),
                duration=lap.get('moving_time', 0.0),
                start_time=lap.get('start_date_local')
            )
            segments.append(segment)
        
        return segments
    
    def get_segment_coordinates(
        self, 
        segment: Segment, 
        latlng_data: List[List[float]]
    ) -> List[LatLon]:
        """
        Extrait les coordonnées GPS d'un segment
        
        Args:
            segment: Segment à extraire
            latlng_data: Données GPS [[lat, lon], ...]
            
        Returns:
            Liste des coordonnées GPS du segment
        """
        if not latlng_data or segment.end_index > len(latlng_data):
            return []
        
        coords = []
        for i in range(segment.start_index, min(segment.end_index, len(latlng_data))):
            lat, lon = latlng_data[i]
            coords.append(LatLon(latitude=lat, longitude=lon))
        
        return coords
    
    def calculate_segment_metrics(
        self,
        segment: Segment,
        distance_series: List[float],
        time_series: List[float],
        altitude_series: Optional[List[float]] = None
    ) -> Dict[str, float]:
        """
        Calcule les métriques d'un segment
        
        Returns:
            Dictionnaire avec pace, elevation_gain, etc.
        """
        if segment.end_index > len(distance_series) or segment.end_index > len(time_series):
            return {}
        
        # Distance et temps
        distance_m = distance_series[segment.end_index - 1] - distance_series[segment.start_index]
        duration_s = time_series[segment.end_index - 1] - time_series[segment.start_index]
        
        metrics = {
            'distance_km': distance_m / 1000,
            'duration_min': duration_s / 60,
            'pace_min_km': (duration_s / 60) / (distance_m / 1000) if distance_m > 0 else 0,
            'speed_kmh': (distance_m / 1000) / (duration_s / 3600) if duration_s > 0 else 0
        }
        
        # Dénivelé si disponible
        if altitude_series and segment.end_index <= len(altitude_series):
            elevation_gain = 0
            for i in range(segment.start_index + 1, segment.end_index):
                if i < len(altitude_series):
                    diff = altitude_series[i] - altitude_series[i-1]
                    if diff > 0:
                        elevation_gain += diff
            
            metrics['elevation_gain_m'] = elevation_gain
            metrics['elevation_gain_km'] = elevation_gain / (distance_m / 1000) if distance_m > 0 else 0
        
        return metrics 