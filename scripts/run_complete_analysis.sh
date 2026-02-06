#!/bin/bash

# Script pour exécuter l'analyse complète des segments et l'entraînement du modèle
# AthletIQ - Analyse Multi-échelle et Prédiction de Rythme

echo "🚀 AthletIQ - Analyse Multi-échelle et Prédiction de Rythme"
echo "=========================================================="
echo ""

# Vérifier que nous sommes dans le bon répertoire
if [ ! -f "backend/activity_detail.db" ]; then
    echo "❌ Erreur: Base de données non trouvée"
    echo "   Assurez-vous d'être dans le répertoire racine d'AthletIQ"
    exit 1
fi

# Créer les dossiers nécessaires
echo "📁 Création des dossiers..."
mkdir -p logs
mkdir -p models
mkdir -p data

# Étape 1: Analyse des segments multi-échelle
echo ""
echo "🔍 Étape 1: Analyse des segments multi-échelle..."
python scripts/segment_analyzer.py

if [ $? -ne 0 ]; then
    echo "❌ Erreur lors de l'analyse des segments"
    exit 1
fi

# Étape 2: Analyse améliorée du dénivelé
echo ""
echo "🏔️ Étape 2: Analyse améliorée du dénivelé..."
python scripts/improved_elevation_analysis.py

if [ $? -ne 0 ]; then
    echo "❌ Erreur lors de l'analyse du dénivelé"
    exit 1
fi

# Étape 3: Entraînement du modèle ML
echo ""
echo "🤖 Étape 3: Entraînement du modèle de prédiction..."
python scripts/pace_predictor_model.py

if [ $? -ne 0 ]; then
    echo "❌ Erreur lors de l'entraînement du modèle"
    exit 1
fi

# Résumé des fichiers générés
echo ""
echo "📊 Résumé des fichiers générés:"
echo "==============================="
echo ""

if [ -f "logs/segment_analysis_report.txt" ]; then
    echo "✅ Rapport d'analyse des segments: logs/segment_analysis_report.txt"
fi

if [ -f "logs/segment_data.json" ]; then
    echo "✅ Données segmentées: logs/segment_data.json"
fi

if [ -f "logs/enhanced_elevation_data.json" ]; then
    echo "✅ Données d'élévation améliorées: logs/enhanced_elevation_data.json"
fi

if [ -f "logs/ml_training_dataset.json" ]; then
    echo "✅ Dataset ML: logs/ml_training_dataset.json"
fi

if [ -f "models/pace_predictor_model.joblib" ]; then
    echo "✅ Modèle de prédiction: models/pace_predictor_model.joblib"
fi

echo ""
echo "🎯 Analyse terminée avec succès!"
echo ""
echo "📋 Prochaines étapes:"
echo "1. Redémarrer le backend pour charger les nouveaux endpoints"
echo "2. Utiliser l'upload GPX dans le frontend"
echo "3. Tester les prédictions de rythme"
echo ""
echo "🔗 Endpoints API disponibles:"
echo "- GET /api/analysis/segment-analysis"
echo "- GET /api/analysis/enhanced-elevation"
echo "- POST /api/prediction/gpx-pace-prediction"
echo ""
