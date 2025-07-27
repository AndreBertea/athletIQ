#!/bin/bash
# ================================================
# start_etl.sh - Lancement du daemon ETL Strava
# ================================================

echo "🏃‍♂️ Démarrage du daemon ETL Strava"

# Charger les variables d'environnement depuis .env.sqlite
if [ -f ".env.sqlite" ]; then
    echo "📋 Chargement des paramètres depuis .env.sqlite"
    # Charger seulement les variables Strava et de base pour éviter les problèmes avec les arrays
    eval $(grep -E '^(STRAVA_|DATABASE_|JWT_|ENCRYPTION_|DEBUG|ENVIRONMENT)' .env.sqlite | grep -v '^#')
else
    echo "⚠️  Fichier .env.sqlite non trouvé !"
    exit 1
fi

# Configuration des bases de données
export STRIDELTA_DB="stridedelta.db"
export DETAIL_DB="activity_detail.db"
export POLL_INTERVAL="30"

# Vérifier que les credentials Strava sont présents
if [[ -z "$STRAVA_CLIENT_ID" || -z "$STRAVA_CLIENT_SECRET" || -z "$STRAVA_REFRESH_TOKEN" ]]; then
    echo "❌ ERREUR: Paramètres Strava manquants dans .env.sqlite"
    echo "   Vérifiez que ces variables sont définies :"
    echo "   - STRAVA_CLIENT_ID"
    echo "   - STRAVA_CLIENT_SECRET"
    echo "   - STRAVA_REFRESH_TOKEN"
    exit 1
fi

# Vérifier que la base source existe
if [[ ! -f "$STRIDELTA_DB" ]]; then
    echo "⚠️  Base source $STRIDELTA_DB n'existe pas !"
    echo "   Cette base doit contenir une table 'activity' avec des strava_id à traiter"
    echo "   Voulez-vous utiliser les données de test ? (y/N)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        echo "🧪 Création de la base de test..."
        sqlite3 "$STRIDELTA_DB" < create_test_stridelta.sql
        echo "✅ Base de test créée avec 4 activités"
    else
        exit 1
    fi
fi

# Vérifier que la base destination existe
if [[ ! -f "$DETAIL_DB" ]]; then
    echo "📊 Création de la base destination..."
    sqlite3 "$DETAIL_DB" < create_activity_detail_db.sql
    echo "✅ Base destination créée"
fi

# Activer l'environnement virtuel
source venv/bin/activate

# Afficher les paramètres
echo ""
echo "🚀 Lancement du daemon avec :"
echo "   - Client ID: ${STRAVA_CLIENT_ID}"
echo "   - Source DB: $STRIDELTA_DB"
echo "   - Detail DB: $DETAIL_DB"
echo "   - Intervalle: ${POLL_INTERVAL}s"

# Vérifier combien d'activités sont en attente
pending=$(sqlite3 "$STRIDELTA_DB" "SELECT COUNT(*) FROM activity WHERE strava_id IS NOT NULL AND strava_id NOT IN (SELECT COALESCE(activity_id, 0) FROM processed_activities)" 2>/dev/null || echo "0")
echo "   - Activités en attente: $pending"
echo ""
echo "   ⚡ Appuyez sur Ctrl+C pour arrêter"
echo ""

# Lancer le daemon ETL
python3 strava_activity_sync.py 