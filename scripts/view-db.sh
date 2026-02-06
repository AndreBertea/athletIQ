#!/bin/bash

# Script de visualisation de la base de données AthletIQ
# Utilise les bonnes colonnes selon la structure réelle de la DB

echo "🗄️ Visualisation de la base de données AthletIQ"
echo "================================================"

# Configuration de la base de données
DB_PATH="backend/stridedelta.db"

# Vérifier si la base de données existe
if [ ! -f "$DB_PATH" ]; then
    echo "❌ Base de données non trouvée à $DB_PATH"
    echo "Assurez-vous que le backend est démarré et que la base de données est créée."
    exit 1
fi

echo ""
echo "📊 Tables disponibles:"
echo "---------------------"
sqlite3 "$DB_PATH" ".tables"

echo ""
echo "👥 Utilisateurs:"
echo "---------------"
sqlite3 "$DB_PATH" "SELECT id, email, created_at FROM user LIMIT 10;"

echo ""
echo "🏃 Activités:"
echo "-------------"
sqlite3 "$DB_PATH" "SELECT id, name, activity_type, distance, moving_time, user_id FROM activity LIMIT 10;"

echo ""
echo "📅 Plans d'entraînement:"
echo "----------------------"
sqlite3 "$DB_PATH" "SELECT id, name, description, user_id FROM workoutplan LIMIT 10;"

echo ""
echo "🔐 Tokens OAuth Strava:"
echo "----------------------"
sqlite3 "$DB_PATH" "SELECT user_id, strava_athlete_id, created_at FROM stravaauth LIMIT 10;"

echo ""
echo "🔐 Tokens OAuth Google:"
echo "----------------------"
sqlite3 "$DB_PATH" "SELECT user_id, google_user_id, created_at FROM googleauth LIMIT 10;"

echo ""
echo "📈 Statistiques:"
echo "---------------"
echo "Nombre total d'utilisateurs:"
sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM user;"

echo "Nombre total d'activités:"
sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM activity;"

echo "Nombre total de plans d'entraînement:"
sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM workoutplan;"

echo "Nombre de connexions Strava:"
sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM stravaauth;"

echo "Nombre de connexions Google:"
sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM googleauth;"

echo ""
echo "✅ Visualisation terminée"
