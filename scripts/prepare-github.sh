#!/bin/bash

# Script de préparation pour GitHub
# Nettoie le projet et supprime les fichiers sensibles

echo "🧹 Nettoyage du projet pour GitHub..."

# Supprimer les fichiers sensibles
echo "📁 Suppression des fichiers sensibles..."
rm -f backend/.env
rm -f backend/.env.backup
rm -f backend/.env.sqlite
rm -f frontend/.env

# Supprimer les bases de données
echo "🗄️ Suppression des bases de données..."
rm -f backend/*.db
rm -f *.db

# Supprimer les logs
echo "📝 Suppression des logs..."
rm -f backend/*.log
rm -f frontend/*.log
rm -f *.log

# Supprimer les fichiers de processus
echo "🔄 Suppression des fichiers de processus..."
rm -f .backend_pid
rm -f .frontend_pid

# Supprimer les fichiers de données
echo "📊 Suppression des fichiers de données..."
rm -rf backend/data/
rm -rf backend/parsed_sessions/
rm -f backend/raw_calendar*.json
rm -f backend/imported_calendar*.json
rm -f backend/problematic_activities.csv

# Supprimer les fichiers de test
echo "🧪 Suppression des fichiers de test..."
rm -f test_import.csv
rm -f backend/test_*.py
rm -f backend/fix_*.py
rm -f backend/get_*.py
rm -f backend/update_*.py
rm -f backend/diagnose_*.py
rm -f backend/recreate_*.py
rm -f backend/create_*.py
rm -f backend/analyze_*.py
rm -f backend/normalize_*.py

# Supprimer les caches Python
echo "🐍 Suppression des caches Python..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

# Supprimer les environnements virtuels
echo "🔧 Suppression des environnements virtuels..."
rm -rf backend/venv/
rm -rf backend/.venv/
rm -rf .venv/

# Supprimer node_modules
echo "📦 Suppression de node_modules..."
rm -rf frontend/node_modules/

# Supprimer les builds
echo "🏗️ Suppression des builds..."
rm -rf frontend/dist/
rm -rf frontend/build/

# Supprimer les fichiers système
echo "💻 Suppression des fichiers système..."
find . -name ".DS_Store" -delete 2>/dev/null || true

echo "✅ Nettoyage terminé !"
echo ""
echo "📋 Prochaines étapes :"
echo "1. Vérifier que .gitignore est à jour"
echo "2. Ajouter les fichiers : git add ."
echo "3. Commiter : git commit -m 'Initial commit'"
echo "4. Créer le repository GitHub"
echo "5. Pousser : git push origin main"
echo ""
echo "⚠️  N'oubliez pas de :"
echo "- Configurer les variables d'environnement sur votre serveur"
echo "- Mettre à jour les URLs de callback dans vos applications OAuth"
echo "- Tester l'application après déploiement" 