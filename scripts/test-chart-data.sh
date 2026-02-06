#!/bin/bash

echo "📊 Test des données du graphique AthlétIQ"
echo "========================================="

# Configuration
API_URL="http://localhost:8000/api/v1"
EMAIL="andre.bertea92@gmail.com"
PASSWORD="test123"

echo "🔐 Authentification..."
LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "email=$EMAIL&password=$PASSWORD")

# Extraire le token d'accès
ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

if [ -z "$ACCESS_TOKEN" ]; then
    echo "❌ Impossible d'extraire le token d'accès"
    exit 1
fi

echo "✅ Authentification réussie"

echo ""
echo "🏃 Récupération des activités pour le graphique..."
ACTIVITIES_RESPONSE=$(curl -s -X GET "$API_URL/activities?limit=50" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

if [ $? -eq 0 ]; then
    echo "✅ Activités récupérées"
    
    # Compter les activités de course
    RUNNING_ACTIVITIES=$(echo "$ACTIVITIES_RESPONSE" | grep -o '"activity_type":"Run"' | wc -l)
    TRAIL_ACTIVITIES=$(echo "$ACTIVITIES_RESPONSE" | grep -o '"activity_type":"TrailRun"' | wc -l)
    TOTAL_RUNNING=$((RUNNING_ACTIVITIES + TRAIL_ACTIVITIES))
    
    echo "📈 Statistiques des activités de course :"
    echo "   - Activités Run: $RUNNING_ACTIVITIES"
    echo "   - Activités TrailRun: $TRAIL_ACTIVITIES"
    echo "   - Total course à pied: $TOTAL_RUNNING"
    
    if [ $TOTAL_RUNNING -gt 0 ]; then
        echo "✅ Données disponibles pour le graphique"
        
        # Extraire quelques exemples d'activités
        echo ""
        echo "📅 Exemples d'activités de course :"
        echo "$ACTIVITIES_RESPONSE" | grep -A 5 -B 5 '"activity_type":"Run"' | head -20
        
    else
        echo "⚠️  Aucune activité de course trouvée"
        echo "   Le graphique ne s'affichera pas sans données de course"
    fi
    
else
    echo "❌ Erreur lors de la récupération des activités"
fi

echo ""
echo "📊 Test des statistiques enrichies..."
ENRICHED_STATS_RESPONSE=$(curl -s -X GET "$API_URL/activities/enriched/stats?period_days=30" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

if [ $? -eq 0 ]; then
    echo "✅ Statistiques enrichies récupérées"
    
    # Extraire les données importantes
    TOTAL_ACTIVITIES=$(echo "$ENRICHED_STATS_RESPONSE" | grep -o '"total_activities":[0-9]*' | cut -d':' -f2)
    TOTAL_DISTANCE=$(echo "$ENRICHED_STATS_RESPONSE" | grep -o '"total_distance_km":[0-9.]*' | cut -d':' -f2)
    
    echo "📈 Données enrichies :"
    echo "   - Total activités: $TOTAL_ACTIVITIES"
    echo "   - Distance totale: $TOTAL_DISTANCE km"
    
else
    echo "❌ Erreur lors de la récupération des statistiques enrichies"
fi

echo ""
echo "🎯 Vérification de la structure des données..."
echo "Structure attendue pour le graphique :"
echo "  - date: string (format français)"
echo "  - distance: number (km)"
echo "  - duration: number (secondes)"
echo "  - pace: number (min/km)"
echo "  - elevation: number (mètres)"

echo ""
echo "✅ Test terminé !"
echo ""
echo "💡 Pour tester le graphique :"
echo "   1. Ouvrez http://localhost:3000"
echo "   2. Connectez-vous avec $EMAIL / $PASSWORD"
echo "   3. Allez sur le Dashboard"
echo "   4. Vérifiez que le graphique 'Évolution des performances' s'affiche" 