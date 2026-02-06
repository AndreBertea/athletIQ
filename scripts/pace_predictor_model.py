#!/usr/bin/env python3
"""
Modèle de prédiction de rythme pour AthletIQ
Utilise scikit-learn pour prédire le rythme optimal selon le profil de course
"""

import json
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import joblib
from pathlib import Path
from typing import Dict, List, Tuple

class PacePredictorModel:
    """Modèle de prédiction de rythme de course"""
    
    def __init__(self):
        self.model = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42
        )
        self.scaler = StandardScaler()
        self.is_trained = False
        self.feature_importance = None
        
    def load_training_data(self, data_file: str = "logs/ml_training_dataset.json") -> pd.DataFrame:
        """Charge les données d'entraînement"""
        with open(data_file, 'r') as f:
            data = json.load(f)
        
        df = pd.DataFrame(data)
        print(f"📊 Dataset chargé: {len(df)} échantillons")
        return df
    
    def prepare_features(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """Prépare les features et targets pour l'entraînement"""
        
        # Features d'entrée
        feature_columns = [
            'distance_km',
            'elevation_gain_m',
            'elevation_loss_m',
            'net_elevation_m',
            'elevation_per_km',
            'avg_grade_percent',
            'is_trail',
            'avg_heartrate'
        ]
        
        # Target (rythme en min/km)
        target_column = 'pace_per_km'
        
        X = df[feature_columns].values
        y = df[target_column].values
        
        print(f"🎯 Features: {len(feature_columns)}")
        print(f"📊 Échantillons: {len(X)}")
        
        return X, y
    
    def train(self, data_file: str = "logs/ml_training_dataset.json") -> Dict:
        """Entraîne le modèle"""
        
        print("🚀 Entraînement du modèle de prédiction de rythme...")
        
        # Charger et préparer les données
        df = self.load_training_data(data_file)
        X, y = self.prepare_features(df)
        
        # Division train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        # Normalisation des features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Entraînement
        self.model.fit(X_train_scaled, y_train)
        
        # Prédictions
        y_pred = self.model.predict(X_test_scaled)
        
        # Métriques d'évaluation
        mae = mean_absolute_error(y_test, y_pred)
        mse = mean_squared_error(y_test, y_pred)
        rmse = np.sqrt(mse)
        r2 = r2_score(y_test, y_pred)
        
        # Cross-validation
        cv_scores = cross_val_score(
            self.model, X_train_scaled, y_train, 
            cv=5, scoring='neg_mean_absolute_error'
        )
        
        # Importance des features
        feature_names = [
            'distance_km', 'elevation_gain_m', 'elevation_loss_m',
            'net_elevation_m', 'elevation_per_km', 'avg_grade_percent',
            'is_trail', 'avg_heartrate'
        ]
        
        self.feature_importance = dict(zip(
            feature_names, 
            self.model.feature_importances_
        ))
        
        self.is_trained = True
        
        results = {
            'mae': mae,
            'mse': mse,
            'rmse': rmse,
            'r2': r2,
            'cv_mean': -cv_scores.mean(),
            'cv_std': cv_scores.std(),
            'feature_importance': self.feature_importance
        }
        
        print(f"✅ Modèle entraîné!")
        print(f"📊 MAE: {mae:.3f} min/km")
        print(f"📊 RMSE: {rmse:.3f} min/km")
        print(f"📊 R²: {r2:.3f}")
        print(f"📊 CV Score: {-cv_scores.mean():.3f} ± {cv_scores.std():.3f}")
        
        return results
    
    def predict_pace(self, features: Dict) -> float:
        """Prédit le rythme pour des features données"""
        
        if not self.is_trained:
            raise ValueError("Modèle non entraîné. Appelez train() d'abord.")
        
        # Préparer les features dans le bon ordre
        feature_values = [
            features.get('distance_km', 0.1),
            features.get('elevation_gain_m', 0),
            features.get('elevation_loss_m', 0),
            features.get('net_elevation_m', 0),
            features.get('elevation_per_km', 0),
            features.get('avg_grade_percent', 0),
            features.get('is_trail', 0),
            features.get('avg_heartrate', 150)
        ]
        
        X = np.array(feature_values).reshape(1, -1)
        X_scaled = self.scaler.transform(X)
        
        predicted_pace = self.model.predict(X_scaled)[0]
        
        return max(0.1, predicted_pace)  # Rythme minimum réaliste
    
    def save_model(self, model_path: str = "models/pace_predictor_model.joblib"):
        """Sauvegarde le modèle entraîné"""
        
        if not self.is_trained:
            raise ValueError("Modèle non entraîné.")
        
        # Créer le dossier si nécessaire
        Path(model_path).parent.mkdir(exist_ok=True)
        
        # Sauvegarder le modèle et le scaler
        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'feature_importance': self.feature_importance,
            'is_trained': self.is_trained
        }
        
        joblib.dump(model_data, model_path)
        print(f"💾 Modèle sauvegardé: {model_path}")
    
    def load_model(self, model_path: str = "models/pace_predictor_model.joblib"):
        """Charge un modèle pré-entraîné"""
        
        if not Path(model_path).exists():
            raise FileNotFoundError(f"Modèle non trouvé: {model_path}")
        
        model_data = joblib.load(model_path)
        
        self.model = model_data['model']
        self.scaler = model_data['scaler']
        self.feature_importance = model_data['feature_importance']
        self.is_trained = model_data['is_trained']
        
        print(f"📂 Modèle chargé: {model_path}")

def create_gpx_analyzer():
    """Crée un analyseur de fichiers GPX pour la prédiction"""
    
    class GPXAnalyzer:
        """Analyseur de fichiers GPX pour extraction du profil de course"""
        
        def __init__(self, model_path: str = "models/pace_predictor_model.joblib"):
            self.predictor = PacePredictorModel()
            self.predictor.load_model(model_path)
        
        def parse_gpx(self, gpx_content: str) -> List[Dict]:
            """Parse un fichier GPX et extrait les segments"""
            
            # Pour l'instant, simulation d'un parsing GPX
            # En réalité, on utiliserait une librairie comme gpxpy
            
            segments = []
            
            # Simulation de segments extraits d'un GPX
            # Dans la vraie implémentation, on parserait les waypoints
            sample_segments = [
                {'distance_km': 1.0, 'elevation_gain_m': 50, 'elevation_loss_m': 0, 'avg_grade_percent': 5.0, 'is_trail': 1},
                {'distance_km': 1.0, 'elevation_gain_m': 0, 'elevation_loss_m': 30, 'avg_grade_percent': -3.0, 'is_trail': 1},
                {'distance_km': 2.0, 'elevation_gain_m': 100, 'elevation_loss_m': 0, 'avg_grade_percent': 5.0, 'is_trail': 1},
                {'distance_km': 1.0, 'elevation_gain_m': 0, 'elevation_loss_m': 80, 'avg_grade_percent': -8.0, 'is_trail': 1},
                {'distance_km': 2.0, 'elevation_gain_m': 20, 'elevation_loss_m': 0, 'avg_grade_percent': 1.0, 'is_trail': 1},
            ]
            
            return sample_segments
        
        def predict_race_strategy(self, gpx_content: str) -> Dict:
            """Prédit la stratégie de course pour un parcours GPX"""
            
            segments = self.parse_gpx(gpx_content)
            
            predictions = []
            total_time = 0
            
            for i, segment in enumerate(segments):
                # Prédire le rythme pour ce segment
                predicted_pace = self.predictor.predict_pace(segment)
                
                # Calculer le temps pour ce segment
                segment_time = predicted_pace * segment['distance_km']
                
                predictions.append({
                    'segment_id': i + 1,
                    'distance_km': segment['distance_km'],
                    'elevation_gain_m': segment['elevation_gain_m'],
                    'avg_grade_percent': segment['avg_grade_percent'],
                    'predicted_pace': predicted_pace,
                    'predicted_time_min': segment_time,
                    'cumulative_time_min': total_time + segment_time
                })
                
                total_time += segment_time
            
            # Calculer les temps de passage aux ravitos (tous les 5km)
            ravito_points = []
            cumulative_distance = 0
            cumulative_time = 0
            
            for prediction in predictions:
                cumulative_distance += prediction['distance_km']
                cumulative_time = prediction['cumulative_time_min']
                
                if cumulative_distance >= 5.0:  # Ravito tous les 5km
                    ravito_points.append({
                        'distance_km': cumulative_distance,
                        'time_min': cumulative_time,
                        'time_formatted': f"{int(cumulative_time//60)}h{int(cumulative_time%60):02d}"
                    })
                    cumulative_distance = 0  # Reset pour le prochain ravito
            
            return {
                'total_distance_km': sum(p['distance_km'] for p in predictions),
                'total_time_min': total_time,
                'total_time_formatted': f"{int(total_time//60)}h{int(total_time%60):02d}",
                'segments': predictions,
                'ravito_points': ravito_points,
                'avg_pace': total_time / sum(p['distance_km'] for p in predictions)
            }
    
    return GPXAnalyzer

def main():
    """Fonction principale pour entraîner le modèle"""
    
    print("🤖 Entraînement du modèle de prédiction de rythme...")
    
    # Créer et entraîner le modèle
    predictor = PacePredictorModel()
    
    try:
        # Entraîner le modèle
        results = predictor.train()
        
        # Sauvegarder le modèle
        predictor.save_model()
        
        # Afficher l'importance des features
        print("\n📊 Importance des features:")
        for feature, importance in sorted(
            results['feature_importance'].items(), 
            key=lambda x: x[1], 
            reverse=True
        ):
            print(f"  {feature}: {importance:.3f}")
        
        # Test avec un exemple
        print("\n🧪 Test de prédiction:")
        test_features = {
            'distance_km': 1.0,
            'elevation_gain_m': 50,
            'elevation_loss_m': 0,
            'net_elevation_m': 50,
            'elevation_per_km': 50,
            'avg_grade_percent': 5.0,
            'is_trail': 1,
            'avg_heartrate': 160
        }
        
        predicted_pace = predictor.predict_pace(test_features)
        print(f"  Segment test: {predicted_pace:.2f} min/km")
        
        print("\n🎯 Modèle prêt pour la prédiction de course!")
        
    except FileNotFoundError as e:
        print(f"❌ Erreur: {e}")
        print("💡 Assurez-vous d'avoir exécuté improved_elevation_analysis.py d'abord")

if __name__ == "__main__":
    main()
