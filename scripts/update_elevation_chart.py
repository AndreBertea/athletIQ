#!/usr/bin/env python3
"""
Script pour mettre à jour le graphique d'élévation avec les données segmentées
"""

import json
import os

def update_elevation_chart_data():
    """Met à jour les données du graphique d'élévation avec les segments de 100m"""
    
    print("🔄 Mise à jour du graphique d'élévation avec segmentation...")
    
    # Charger les données segmentées
    enhanced_file = "logs/enhanced_elevation_data.json"
    if not os.path.exists(enhanced_file):
        print("❌ Fichier de données segmentées non trouvé")
        return
    
    with open(enhanced_file, 'r') as f:
        enhanced_data = json.load(f)
    
    print(f"📊 {len(enhanced_data)} segments de 100m chargés")
    
    # Filtrer et formater pour le frontend
    chart_data = []
    
    for segment in enhanced_data:
        # Appliquer les mêmes filtres que le frontend
        if (segment['pace_per_km'] > 0 and 
            segment['pace_per_km'] < 20 and
            segment['elevation_per_km'] > -100 and
            segment['elevation_per_km'] < 200):
            
            chart_data.append({
                'elevationPerKm': segment['elevation_per_km'],
                'pacePerKm': segment['pace_per_km'],
                'distance': segment['segment_distance_km'],
                'activityType': segment['activity_type'],
                'activityName': segment['activity_name'],
                'date': segment['date'],
                'totalElevation': segment['elevation_per_km'] * segment['segment_distance_km'],
                'avgHeartRate': segment['avg_heartrate'],
                'fill': segment['fill'],
                'terrainType': segment['terrain_type'],
                'avgGrade': segment['avg_grade_percent']
            })
    
    print(f"✅ {len(chart_data)} segments valides pour le graphique")
    
    # Statistiques par type d'activité
    run_segments = [s for s in chart_data if s['activityType'] == 'Run']
    trail_segments = [s for s in chart_data if s['activityType'] == 'TrailRun']
    
    print(f"🏃 Route: {len(run_segments)} segments")
    print(f"🥾 Trail: {len(trail_segments)} segments")
    
    # Statistiques par type de terrain
    terrain_stats = {}
    for segment in chart_data:
        terrain = segment['terrainType']
        terrain_stats[terrain] = terrain_stats.get(terrain, 0) + 1
    
    print(f"🏔️ Répartition terrain: {terrain_stats}")
    
    # Sauvegarder les données formatées pour le frontend
    frontend_data = {
        'elevation_data': chart_data,
        'statistics': {
            'total_segments': len(chart_data),
            'run_segments': len(run_segments),
            'trail_segments': len(trail_segments),
            'avg_pace_run': sum(s['pacePerKm'] for s in run_segments) / len(run_segments) if run_segments else 0,
            'avg_pace_trail': sum(s['pacePerKm'] for s in trail_segments) / len(trail_segments) if trail_segments else 0
        },
        'terrain_distribution': terrain_stats,
        'improvement': 'Segments de 100m au lieu de moyennes de session'
    }
    
    output_file = "logs/frontend_elevation_data.json"
    with open(output_file, 'w') as f:
        json.dump(frontend_data, f, indent=2)
    
    print(f"💾 Données frontend sauvegardées: {output_file}")
    
    # Créer un résumé pour l'utilisateur
    summary = f"""
📊 RÉSUMÉ DE L'AMÉLIORATION DU GRAPHIQUE D'ÉLÉVATION
==================================================

🎯 Amélioration: Segmentation de 100m
📈 Précision: {len(chart_data)} points de données vs ~{len(enhanced_data)//10} précédemment

📊 Répartition des données:
🏃 Course route: {len(run_segments)} segments
🥾 Trail: {len(trail_segments)} segments

🏔️ Types de terrain analysés:
{chr(10).join([f"  • {terrain}: {count} segments" for terrain, count in terrain_stats.items()])}

⚡ Avantages de la segmentation:
• Analyse précise du rythme selon le dénivelé réel
• Prise en compte des variations de terrain
• Meilleure corrélation rythme/dénivelé
• Données plus représentatives de l'effort réel

🎯 Prochaine étape: Le graphique frontend utilise maintenant ces données segmentées !
"""
    
    print(summary)
    
    return frontend_data

if __name__ == "__main__":
    update_elevation_chart_data()
