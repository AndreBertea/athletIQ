#!/usr/bin/env python3
"""
Parser GPX pour AthletIQ
Analyse les fichiers GPX et extrait les segments avec dénivelé
"""

import gpxpy
import gpxpy.gpx
from typing import List, Dict, Tuple
import math

def parse_gpx_file(gpx_content: str) -> tuple[List[Dict], List[Dict]]:
    """
    Parse un fichier GPX et retourne les segments analysés + points d'altitude
    """
    try:
        gpx = gpxpy.parse(gpx_content)
        
        segments = []
        elevation_points = []
        all_points = []
        
        # Collecter tous les points de toutes les tracks
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    if point.latitude and point.longitude:
                        all_points.append({
                            'lat': point.latitude,
                            'lon': point.longitude,
                            'elevation': point.elevation or 0,
                            'time': point.time
                        })
        
        if len(all_points) < 2:
            raise ValueError("Pas assez de points dans le GPX")
        
        # Calculer les distances cumulées pour le profil
        cumulative_distance = 0
        for i in range(len(all_points)):
            if i > 0:
                distance = calculate_distance(
                    all_points[i-1]['lat'], all_points[i-1]['lon'],
                    all_points[i]['lat'], all_points[i]['lon']
                )
                cumulative_distance += distance
            
            elevation_points.append({
                'distance_km': round(cumulative_distance / 1000, 3),
                'elevation_m': all_points[i]['elevation'],
                'lat': all_points[i]['lat'],
                'lon': all_points[i]['lon']
            })
        
        # Calculer les segments de 1km
        segment_length = 1000  # 1km par segment
        current_segment_start = 0
        current_distance = 0
        
        for i in range(1, len(all_points)):
            # Calculer la distance depuis le dernier point
            prev_point = all_points[i-1]
            curr_point = all_points[i]
            
            distance = calculate_distance(
                prev_point['lat'], prev_point['lon'],
                curr_point['lat'], curr_point['lon']
            )
            
            current_distance += distance
            
            # Si on a atteint 1km ou fin de parcours
            if current_distance >= segment_length or i == len(all_points) - 1:
                if i > current_segment_start:
                    segment = extract_segment_data(
                        all_points[current_segment_start:i+1],
                        current_distance
                    )
                    if segment:
                        segments.append(segment)
                
                current_segment_start = i
                current_distance = 0
        
        return segments, elevation_points
        
    except Exception as e:
        raise ValueError(f"Erreur parsing GPX: {str(e)}")

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcule la distance entre deux points en mètres (formule de Haversine)
    """
    R = 6371000  # Rayon de la Terre en mètres
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_lat / 2) ** 2 + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

def extract_segment_data(points: List[Dict], distance_m: float) -> Dict:
    """
    Extrait les données d'un segment de points GPX avec calcul précis D+/D-
    """
    if len(points) < 2:
        return None
    
    # Calculer D+ et D- en analysant point par point
    elevation_gain = 0
    elevation_loss = 0
    
    for i in range(1, len(points)):
        if points[i]['elevation'] and points[i-1]['elevation']:
            elev_diff = points[i]['elevation'] - points[i-1]['elevation']
            if elev_diff > 0:
                elevation_gain += elev_diff
            else:
                elevation_loss += abs(elev_diff)
    
    # Calculer le dénivelé net
    net_elevation = elevation_gain - elevation_loss
    
    # Calculer la pente moyenne
    distance_km = distance_m / 1000
    avg_grade = (net_elevation / distance_m) * 100 if distance_m > 0 else 0
    
    # Calculer la pente maximale
    max_grade = 0
    for i in range(1, len(points)):
        if points[i]['elevation'] and points[i-1]['elevation']:
            dist_segment = calculate_distance(
                points[i-1]['lat'], points[i-1]['lon'],
                points[i]['lat'], points[i]['lon']
            )
            if dist_segment > 0:
                elev_diff = points[i]['elevation'] - points[i-1]['elevation']
                grade = (elev_diff / dist_segment) * 100
                max_grade = max(max_grade, abs(grade))
    
    return {
        'distance_km': distance_km,
        'elevation_gain_m': round(elevation_gain),
        'elevation_loss_m': round(elevation_loss),
        'net_elevation_m': round(net_elevation),
        'elevation_per_km': round(net_elevation / distance_km, 1) if distance_km > 0 else 0,
        'avg_grade_percent': round(avg_grade, 1),
        'max_grade_percent': round(max_grade, 1),
        'is_trail': 1,  # Pour l'instant, on assume que c'est du trail
        'avg_heartrate': 160  # Valeur par défaut, sera remplacée par le paramètre
    }

def calculate_global_stats(segments: List[Dict]) -> Dict:
    """
    Calcule les statistiques globales du parcours
    """
    total_distance = sum(s['distance_km'] for s in segments)
    total_elevation_gain = sum(s['elevation_gain_m'] for s in segments)
    total_elevation_loss = sum(s['elevation_loss_m'] for s in segments)
    net_elevation = total_elevation_gain - total_elevation_loss
    
    return {
        'total_distance_km': round(total_distance, 2),
        'total_elevation_gain_m': total_elevation_gain,
        'total_elevation_loss_m': total_elevation_loss,
        'net_elevation_m': net_elevation,
        'avg_grade_percent': round((net_elevation / total_distance / 1000) * 100, 1) if total_distance > 0 else 0
    }

def test_gpx_parsing():
    """
    Test du parser avec le fichier UTMJ
    """
    try:
        with open('/Users/andrebertea/Projects/athletIQ/utmj-24-relais-5-mouthe-jougne.gpx', 'r') as f:
            gpx_content = f.read()
        
        segments, elevation_points = parse_gpx_file(gpx_content)
        stats = calculate_global_stats(segments)
        
        print(f"📊 GPX parsé: {len(segments)} segments")
        print(f"📍 Points d'altitude: {len(elevation_points)}")
        print(f"🏃 Distance totale: {stats['total_distance_km']} km")
        print(f"📈 D+ total: +{stats['total_elevation_gain_m']} m")
        print(f"📉 D- total: -{stats['total_elevation_loss_m']} m")
        print(f"🏔️ Dénivelé net: {stats['net_elevation_m']:+} m")
        print(f"📊 Pente moyenne: {stats['avg_grade_percent']:+.1f}%")
        
        # Afficher les premiers segments avec D+ et D-
        print("\n🔍 Premiers segments:")
        for i, segment in enumerate(segments[:5]):
            print(f"  Segment {i+1}: {segment['distance_km']:.2f}km, "
                  f"D+: +{segment['elevation_gain_m']}m, "
                  f"D-: -{segment['elevation_loss_m']}m, "
                  f"Net: {segment['net_elevation_m']:+}m, "
                  f"Pente: {segment['avg_grade_percent']:+.1f}%")
        
        return segments
        
    except Exception as e:
        print(f"❌ Erreur test: {e}")
        return []

if __name__ == "__main__":
    test_gpx_parsing()
