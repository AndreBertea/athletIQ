#!/usr/bin/env python3
"""
Analyseur de segments multi-échelle pour AthletIQ
Analyse les données de streams pour extraire des métriques précises par segment
"""

import json
import sqlite3
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from pathlib import Path
import math

@dataclass
class SegmentMetrics:
    """Métriques d'un segment de course"""
    distance_km: float
    elevation_gain_m: float
    elevation_loss_m: float
    avg_grade_percent: float
    max_grade_percent: float
    pace_min_per_km: float
    avg_heartrate: float
    segment_type: str  # 'flat', 'uphill', 'downhill'
    effort_level: str  # 'easy', 'moderate', 'hard', 'very_hard'

class SegmentAnalyzer:
    """Analyseur de segments pour les données de course"""
    
    def __init__(self, db_path: str = "backend/activity_detail.db"):
        self.db_path = db_path
        self.segment_lengths = [50, 100, 500, 1000, 5000, 10000]  # mètres
        
    def get_enriched_activities(self, limit: int = 150) -> List[Dict]:
        """Récupère les activités enrichies des 6 derniers mois"""
        conn = sqlite3.connect(self.db_path)
        
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
        LIMIT ?
        """
        
        df = pd.read_sql_query(query, conn, params=[limit])
        conn.close()
        
        return df.to_dict('records')
    
    def get_activity_streams(self, activity_id: int) -> Optional[Dict]:
        """Récupère les streams d'une activité"""
        conn = sqlite3.connect(self.db_path)
        
        query = """
        SELECT stream_type, data
        FROM activity_streams
        WHERE activity_id = ?
        """
        
        cursor = conn.execute(query, (activity_id,))
        streams = {}
        
        for row in cursor.fetchall():
            try:
                streams[row[0]] = json.loads(row[1])
            except json.JSONDecodeError:
                continue
                
        conn.close()
        
        # Vérifier que nous avons les streams nécessaires
        required_streams = ['heartrate', 'time', 'distance', 'altitude']
        if not all(stream in streams for stream in required_streams):
            return None
            
        return streams
    
    def calculate_grade(self, distance: float, elevation: float) -> float:
        """Calcule le pourcentage de pente"""
        if distance <= 0:
            return 0.0
        return (elevation / distance) * 100
    
    def classify_segment_type(self, avg_grade: float) -> str:
        """Classifie le type de segment selon la pente"""
        if abs(avg_grade) < 2:
            return 'flat'
        elif avg_grade > 2:
            return 'uphill'
        else:
            return 'downhill'
    
    def classify_effort_level(self, pace: float, heartrate: float) -> str:
        """Classifie le niveau d'effort"""
        # Seuils basés sur l'expérience (à ajuster selon vos données)
        if pace > 7.0 or heartrate < 120:
            return 'easy'
        elif pace > 5.5 or heartrate < 150:
            return 'moderate'
        elif pace > 4.5 or heartrate < 170:
            return 'hard'
        else:
            return 'very_hard'
    
    def analyze_segments(self, streams: Dict, segment_length: int) -> List[SegmentMetrics]:
        """Analyse une activité en segments de longueur donnée"""
        heartrate = np.array(streams['heartrate'])
        time = np.array(streams['time'])
        distance = np.array(streams['distance'])
        altitude = np.array(streams['altitude'])
        
        segments = []
        current_segment_start = 0
        
        for i in range(len(distance)):
            current_distance = distance[i] - distance[current_segment_start]
            
            # Si on a atteint la longueur de segment ou fin de données
            if current_distance >= segment_length or i == len(distance) - 1:
                if i > current_segment_start:  # S'assurer qu'on a au moins 2 points
                    segment_data = self._extract_segment_metrics(
                        heartrate[current_segment_start:i+1],
                        time[current_segment_start:i+1],
                        distance[current_segment_start:i+1],
                        altitude[current_segment_start:i+1]
                    )
                    
                    if segment_data:
                        segments.append(segment_data)
                
                current_segment_start = i
        
        return segments
    
    def _extract_segment_metrics(self, hr_data: np.ndarray, time_data: np.ndarray, 
                                distance_data: np.ndarray, altitude_data: np.ndarray) -> Optional[SegmentMetrics]:
        """Extrait les métriques d'un segment"""
        if len(hr_data) < 2:
            return None
            
        # Distance du segment
        segment_distance = (distance_data[-1] - distance_data[0]) / 1000  # km
        
        if segment_distance <= 0:
            return None
            
        # Élévation
        elevation_gain = max(0, altitude_data[-1] - altitude_data[0])
        elevation_loss = max(0, altitude_data[0] - altitude_data[-1])
        
        # Pente moyenne
        avg_grade = self.calculate_grade(segment_distance * 1000, elevation_gain - elevation_loss)
        
        # Pente maximale
        max_grade = 0
        for i in range(1, len(altitude_data)):
            dist_diff = (distance_data[i] - distance_data[i-1]) / 1000  # km
            alt_diff = altitude_data[i] - altitude_data[i-1]  # m
            if dist_diff > 0:
                grade = self.calculate_grade(dist_diff * 1000, alt_diff)
                max_grade = max(max_grade, abs(grade))
        
        # Rythme (en min/km)
        time_diff = (time_data[-1] - time_data[0]) / 60  # minutes
        pace = time_diff / segment_distance if segment_distance > 0 else 0
        
        # FC moyenne
        avg_hr = np.mean(hr_data[hr_data > 0]) if np.any(hr_data > 0) else 0
        
        # Classification
        segment_type = self.classify_segment_type(avg_grade)
        effort_level = self.classify_effort_level(pace, avg_hr)
        
        return SegmentMetrics(
            distance_km=segment_distance,
            elevation_gain_m=elevation_gain,
            elevation_loss_m=elevation_loss,
            avg_grade_percent=avg_grade,
            max_grade_percent=max_grade,
            pace_min_per_km=pace,
            avg_heartrate=avg_hr,
            segment_type=segment_type,
            effort_level=effort_level
        )
    
    def analyze_all_activities(self) -> Dict[str, List[SegmentMetrics]]:
        """Analyse toutes les activités avec tous les types de segments"""
        activities = self.get_enriched_activities()
        results = {}
        
        print(f"📊 Analyse de {len(activities)} activités...")
        
        for i, activity in enumerate(activities):
            activity_id = activity['activity_id']
            sport_type = activity['sport_type']
            
            print(f"  {i+1}/{len(activities)} - {sport_type} #{activity_id}")
            
            streams = self.get_activity_streams(activity_id)
            if not streams:
                print(f"    ⚠️  Pas de streams pour l'activité {activity_id}")
                continue
            
            # Analyser pour chaque longueur de segment
            for segment_length in self.segment_lengths:
                key = f"{sport_type}_{segment_length}m"
                if key not in results:
                    results[key] = []
                
                segments = self.analyze_segments(streams, segment_length)
                results[key].extend(segments)
                
                print(f"    ✅ {len(segments)} segments de {segment_length}m")
        
        return results
    
    def generate_analysis_report(self, results: Dict[str, List[SegmentMetrics]]) -> str:
        """Génère un rapport d'analyse"""
        report = []
        report.append("📊 RAPPORT D'ANALYSE MULTI-ÉCHELLE")
        report.append("=" * 50)
        report.append("")
        
        for key, segments in results.items():
            if not segments:
                continue
                
            sport_type, segment_length = key.split('_')
            segment_length = segment_length.replace('m', '')
            
            report.append(f"🏃 {sport_type} - Segments de {segment_length}m")
            report.append(f"   Nombre de segments: {len(segments)}")
            
            if segments:
                # Statistiques générales
                distances = [s.distance_km for s in segments]
                paces = [s.pace_min_per_km for s in segments if s.pace_min_per_km > 0]
                grades = [s.avg_grade_percent for s in segments]
                heartrates = [s.avg_heartrate for s in segments if s.avg_heartrate > 0]
                
                if paces:
                    report.append(f"   Rythme: {np.mean(paces):.2f} ± {np.std(paces):.2f} min/km")
                if grades:
                    report.append(f"   Dénivelé: {np.mean(grades):.1f} ± {np.std(grades):.1f}%")
                if heartrates:
                    report.append(f"   FC: {np.mean(heartrates):.0f} ± {np.std(heartrates):.0f} BPM")
                
                # Distribution par type de terrain
                terrain_dist = {}
                effort_dist = {}
                for segment in segments:
                    terrain_dist[segment.segment_type] = terrain_dist.get(segment.segment_type, 0) + 1
                    effort_dist[segment.effort_level] = effort_dist.get(segment.effort_level, 0) + 1
                
                report.append(f"   Terrain: {dict(terrain_dist)}")
                report.append(f"   Effort: {dict(effort_dist)}")
            
            report.append("")
        
        return "\n".join(report)

def main():
    """Fonction principale"""
    print("🚀 Démarrage de l'analyseur de segments...")
    
    analyzer = SegmentAnalyzer()
    
    # Analyser toutes les activités
    results = analyzer.analyze_all_activities()
    
    # Générer le rapport
    report = analyzer.generate_analysis_report(results)
    
    # Sauvegarder le rapport
    with open("logs/segment_analysis_report.txt", "w") as f:
        f.write(report)
    
    print("\n" + report)
    print(f"\n📄 Rapport sauvegardé dans: logs/segment_analysis_report.txt")
    
    # Sauvegarder les données structurées
    structured_data = {}
    for key, segments in results.items():
        structured_data[key] = [
            {
                'distance_km': s.distance_km,
                'elevation_gain_m': s.elevation_gain_m,
                'elevation_loss_m': s.elevation_loss_m,
                'avg_grade_percent': s.avg_grade_percent,
                'max_grade_percent': s.max_grade_percent,
                'pace_min_per_km': s.pace_min_per_km,
                'avg_heartrate': s.avg_heartrate,
                'segment_type': s.segment_type,
                'effort_level': s.effort_level
            }
            for s in segments
        ]
    
    with open("logs/segment_data.json", "w") as f:
        json.dump(structured_data, f, indent=2)
    
    print(f"💾 Données structurées sauvegardées dans: logs/segment_data.json")

if __name__ == "__main__":
    main()
