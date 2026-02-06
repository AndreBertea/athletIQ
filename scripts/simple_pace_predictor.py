#!/usr/bin/env python3
"""
Modèle de prédiction de rythme simple basé sur les performances réelles
"""

import json
import sqlite3
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import joblib
import os

def load_real_activities():
    """Charge les activités réelles depuis la base de données"""
    conn = sqlite3.connect("backend/activity_detail.db")
    
    query = """
    SELECT 
        distance_m / 1000.0 as distance_km,
        elev_gain_m / (distance_m / 1000.0) as elevation_per_km,
        (moving_time_s / 60.0) / (distance_m / 1000.0) as pace_per_km,
        sport_type,
        start_date_utc
    FROM activities 
    WHERE sport_type IN ('Run', 'TrailRun')
    AND start_date_utc >= date('now', '-6 months')
    AND distance_m > 0
    AND moving_time_s > 0
    AND (moving_time_s / 60.0) / (distance_m / 1000.0) > 0
    AND (moving_time_s / 60.0) / (distance_m / 1000.0) < 20  -- Filtrer les rythmes aberrants
    ORDER BY start_date_utc DESC
    """
    
    cursor = conn.execute(query)
    activities = cursor.fetchall()
    conn.close()
    
    return activities

def prepare_training_data(activities):
    """Prépare les données d'entraînement"""
    X = []
    y = []
    
    for activity in activities:
        distance_km, elevation_per_km, pace_per_km, sport_type, start_date = activity
        
        # Features
        is_trail = 1 if sport_type == 'TrailRun' else 0
        elevation_gain_m = elevation_per_km * distance_km
        net_elevation = elevation_gain_m  # Simplification
        elevation_per_km_feature = elevation_per_km
        
        features = [
            distance_km,
            elevation_gain_m,
            0,  # elevation_loss_m (pas disponible dans les données)
            net_elevation,
            elevation_per_km_feature,
            (elevation_per_km / 10),  # avg_grade_percent approximatif
            is_trail,
            150  # FC moyenne par défaut
        ]
        
        X.append(features)
        y.append(pace_per_km)
    
    return np.array(X), np.array(y)

def train_simple_model():
    """Entraîne un modèle simple basé sur les performances réelles"""
    print("🔄 Chargement des activités réelles...")
    activities = load_real_activities()
    
    if len(activities) < 10:
        print(f"❌ Pas assez d'activités: {len(activities)}")
        return None
    
    print(f"✅ {len(activities)} activités chargées")
    
    # Préparer les données
    X, y = prepare_training_data(activities)
    
    print(f"📊 Données d'entraînement: {X.shape[0]} échantillons, {X.shape[1]} features")
    print(f"📈 Rythme moyen: {np.mean(y):.2f} min/km")
    print(f"📈 Rythme min: {np.min(y):.2f} min/km")
    print(f"📈 Rythme max: {np.max(y):.2f} min/km")
    
    # Entraîner le modèle
    model = RandomForestRegressor(
        n_estimators=100,
        max_depth=10,
        random_state=42,
        n_jobs=-1
    )
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    print("🤖 Entraînement du modèle...")
    model.fit(X_scaled, y)
    
    # Évaluer
    train_score = model.score(X_scaled, y)
    print(f"📊 Score d'entraînement: {train_score:.3f}")
    
    # Importance des features
    feature_names = [
        'distance_km', 'elevation_gain_m', 'elevation_loss_m', 
        'net_elevation', 'elevation_per_km', 'avg_grade_percent', 
        'is_trail', 'avg_heartrate'
    ]
    
    importances = model.feature_importances_
    print("\n🎯 Importance des features:")
    for name, importance in zip(feature_names, importances):
        print(f"  {name}: {importance:.3f}")
    
    # Sauvegarder
    model_data = {
        'model': model,
        'scaler': scaler,
        'feature_names': feature_names,
        'training_score': train_score,
        'n_samples': len(activities)
    }
    
    os.makedirs('models', exist_ok=True)
    model_path = 'models/simple_pace_predictor_model.joblib'
    joblib.dump(model_data, model_path)
    
    print(f"💾 Modèle sauvegardé: {model_path}")
    
    return model_data

if __name__ == "__main__":
    train_simple_model()
