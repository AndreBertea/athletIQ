#!/usr/bin/env python3
"""
Analyse améliorée du dénivelé pour AthletIQ
Génère des données segmentées pour le graphique d'impact du dénivelé
"""

import json
import sqlite3
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from pathlib import Path

def get_activity_streams_for_elevation_analysis():
    """Récupère et analyse les streams pour l'analyse du dénivelé améliorée"""
    
    conn = sqlite3.connect("backend/activity_detail.db")
    
    # Récupérer les activités des 6 derniers mois
    query = """
    SELECT DISTINCT 
        a.activity_id,
        a.sport_type,
        a.start_date_utc,
        a.distance_m,
        a.moving_time_s,
        a.elev_gain_m,
        a.avg_heartrate_bpm,
        a.name
    FROM activities a
    WHERE a.sport_type IN ('Run', 'TrailRun')
    AND a.distance_m > 1000
    AND a.moving_time_s > 300
    AND a.start_date_utc >= datetime('now', '-6 months')
    ORDER BY a.start_date_utc DESC
    LIMIT 100
    """
    
    activities_df = pd.read_sql_query(query, conn)
    
    # Récupérer les streams pour chaque activité
    stream_query = """
    SELECT stream_type, data
    FROM activity_streams
    WHERE activity_id = ?
    """
    
    enhanced_data = []
    
    for _, activity in activities_df.iterrows():
        activity_id = activity['activity_id']
        
        cursor = conn.execute(stream_query, (activity_id,))
        streams = {}
        
        for row in cursor.fetchall():
            try:
                streams[row[0]] = json.loads(row[1])
            except json.JSONDecodeError:
                continue
        
        # Vérifier que nous avons les streams nécessaires
        if not all(stream in streams for stream in ['heartrate', 'time', 'distance', 'altitude']):
            continue
            
        # Analyser les segments de 100m pour plus de précision
        segments_data = analyze_activity_segments(
            streams, 
            activity_id, 
            activity['sport_type'],
            activity['name'],
            activity['start_date_utc']
        )
        
        enhanced_data.extend(segments_data)
    
    conn.close()
    
    return enhanced_data

def analyze_activity_segments(streams: Dict, activity_id: int, sport_type: str, 
                            activity_name: str, start_date: str) -> List[Dict]:
    """Analyse une activité en segments de 100m"""
    
    heartrate = np.array(streams['heartrate'])
    time = np.array(streams['time'])
    distance = np.array(streams['distance'])
    altitude = np.array(streams['altitude'])
    
    segments = []
    segment_length = 100  # 100m
    current_segment_start = 0
    
    for i in range(len(distance)):
        current_distance = distance[i] - distance[current_segment_start]
        
        # Si on a atteint 100m ou fin de données
        if current_distance >= segment_length or i == len(distance) - 1:
            if i > current_segment_start:
                segment_data = extract_segment_metrics(
                    heartrate[current_segment_start:i+1],
                    time[current_segment_start:i+1],
                    distance[current_segment_start:i+1],
                    altitude[current_segment_start:i+1],
                    activity_id,
                    sport_type,
                    activity_name,
                    start_date
                )
                
                if segment_data:
                    segments.append(segment_data)
            
            current_segment_start = i
    
    return segments

def extract_segment_metrics(hr_data: np.ndarray, time_data: np.ndarray, 
                          distance_data: np.ndarray, altitude_data: np.ndarray,
                          activity_id: int, sport_type: str, activity_name: str, 
                          start_date: str) -> Dict:
    """Extrait les métriques d'un segment de 100m"""
    
    if len(hr_data) < 2:
        return None
    
    # Distance du segment
    segment_distance = (distance_data[-1] - distance_data[0]) / 1000  # km
    
    if segment_distance <= 0:
        return None
    
    # Élévation
    elevation_gain = max(0, altitude_data[-1] - altitude_data[0])
    elevation_loss = max(0, altitude_data[0] - altitude_data[-1])
    net_elevation = elevation_gain - elevation_loss
    
    # Dénivelé par km
    elevation_per_km = net_elevation / segment_distance if segment_distance > 0 else 0
    
    # Pente moyenne
    avg_grade = (net_elevation / (segment_distance * 1000)) * 100 if segment_distance > 0 else 0
    
    # Rythme (en min/km)
    time_diff = (time_data[-1] - time_data[0]) / 60  # minutes
    pace_per_km = time_diff / segment_distance if segment_distance > 0 else 0
    
    # FC moyenne
    valid_hr = hr_data[hr_data > 0]
    avg_heartrate = np.mean(valid_hr) if len(valid_hr) > 0 else 0
    
    # Classification du terrain
    if abs(avg_grade) < 2:
        terrain_type = 'flat'
    elif avg_grade > 5:
        terrain_type = 'steep_uphill'
    elif avg_grade > 2:
        terrain_type = 'uphill'
    elif avg_grade < -5:
        terrain_type = 'steep_downhill'
    else:
        terrain_type = 'downhill'
    
    return {
        'activity_id': activity_id,
        'activity_type': sport_type,
        'activity_name': activity_name,
        'date': start_date,
        'segment_distance_km': segment_distance,
        'elevation_per_km': elevation_per_km,
        'elevation_gain_m': elevation_gain,
        'elevation_loss_m': elevation_loss,
        'net_elevation_m': net_elevation,
        'avg_grade_percent': avg_grade,
        'pace_per_km': pace_per_km,
        'avg_heartrate': avg_heartrate,
        'terrain_type': terrain_type,
        'fill': '#3b82f6' if sport_type == 'Run' else '#f59e0b'  # Couleurs pour le graphique
    }

def generate_enhanced_elevation_data():
    """Génère les données améliorées pour le graphique d'élévation"""
    
    print("🔄 Génération des données d'analyse améliorée du dénivelé...")
    
    # Récupérer les données segmentées
    enhanced_data = get_activity_streams_for_elevation_analysis()
    
    print(f"📊 {len(enhanced_data)} segments analysés")
    
    # Filtrer les données aberrantes
    filtered_data = []
    for segment in enhanced_data:
        # Filtres de qualité
        if (segment['pace_per_km'] > 0 and 
            segment['pace_per_km'] < 20 and  # Rythme réaliste
            segment['elevation_per_km'] > -100 and  # Pas de chute libre
            segment['elevation_per_km'] < 200 and  # Pas de montée impossible
            segment['avg_heartrate'] > 60 and  # FC réaliste
            segment['avg_heartrate'] < 220):
            filtered_data.append(segment)
    
    print(f"✅ {len(filtered_data)} segments valides après filtrage")
    
    # Statistiques par type d'activité
    run_segments = [s for s in filtered_data if s['activity_type'] == 'Run']
    trail_segments = [s for s in filtered_data if s['activity_type'] == 'TrailRun']
    
    print(f"🏃 Route: {len(run_segments)} segments")
    print(f"🥾 Trail: {len(trail_segments)} segments")
    
    # Statistiques par type de terrain
    terrain_stats = {}
    for segment in filtered_data:
        terrain = segment['terrain_type']
        if terrain not in terrain_stats:
            terrain_stats[terrain] = 0
        terrain_stats[terrain] += 1
    
    print(f"🏔️ Répartition terrain: {terrain_stats}")
    
    # Sauvegarder les données
    output_file = "logs/enhanced_elevation_data.json"
    with open(output_file, "w") as f:
        json.dump(filtered_data, f, indent=2)
    
    print(f"💾 Données sauvegardées: {output_file}")
    
    return filtered_data

def create_ml_features_dataset():
    """Crée un dataset pour l'entraînement du modèle ML"""
    
    print("🤖 Préparation du dataset pour l'IA...")
    
    enhanced_data = get_activity_streams_for_elevation_analysis()
    
    # Créer le dataset avec features et targets
    ml_data = []
    
    for segment in enhanced_data:
        if (segment['pace_per_km'] > 0 and 
            segment['pace_per_km'] < 20 and
            segment['elevation_per_km'] > -100 and
            segment['elevation_per_km'] < 200):
            
            ml_data.append({
                # Features
                'distance_km': segment['segment_distance_km'],
                'elevation_gain_m': segment['elevation_gain_m'],
                'elevation_loss_m': segment['elevation_loss_m'],
                'net_elevation_m': segment['net_elevation_m'],
                'elevation_per_km': segment['elevation_per_km'],
                'avg_grade_percent': segment['avg_grade_percent'],
                'is_trail': 1 if segment['activity_type'] == 'TrailRun' else 0,
                'avg_heartrate': segment['avg_heartrate'],
                
                # Target (ce qu'on veut prédire)
                'pace_per_km': segment['pace_per_km'],
                
                # Métadonnées
                'activity_id': segment['activity_id'],
                'terrain_type': segment['terrain_type']
            })
    
    # Sauvegarder le dataset ML
    ml_file = "logs/ml_training_dataset.json"
    with open(ml_file, "w") as f:
        json.dump(ml_data, f, indent=2)
    
    print(f"🤖 Dataset ML sauvegardé: {ml_file}")
    print(f"📊 {len(ml_data)} échantillons pour l'entraînement")
    
    return ml_data

if __name__ == "__main__":
    # Générer les données améliorées
    enhanced_data = generate_enhanced_elevation_data()
    
    # Créer le dataset ML
    ml_data = create_ml_features_dataset()
    
    print("\n🎯 Prochaines étapes:")
    print("1. Intégrer ces données dans le frontend")
    print("2. Entraîner le modèle ML avec scikit-learn")
    print("3. Ajouter l'upload GPX pour prédiction")
