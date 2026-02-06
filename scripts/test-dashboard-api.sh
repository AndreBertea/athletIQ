#!/bin/bash

echo "🧪 Test de l'API Dashboard AthlétIQ"
echo "==================================="

# Configuration
API_URL="http://localhost:8000/api/v1"
EMAIL="andre.bertea92@gmail.com"
PASSWORD="test123"

echo "🔐 Authentification..."
LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "email=$EMAIL&password=$PASSWORD")

if [ $? -ne 0 ]; then
    echo "❌ Erreur de connexion à l'API"
    exit 1
fi

# Extraire le token d'accès
ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

if [ -z "$ACCESS_TOKEN" ]; then
    echo "❌ Impossible d'extraire le token d'accès"
    echo "Réponse: $LOGIN_RESPONSE"
    exit 1
fi

echo "✅ Authentification réussie"

echo ""
echo "📊 Test des statistiques d'activités..."
STATS_RESPONSE=$(curl -s -X GET "$API_URL/activities/stats?period_days=30" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

if [ $? -eq 0 ]; then
    echo "✅ Statistiques récupérées"
    echo "Données: $(echo "$STATS_RESPONSE" | head -c 200)..."
else
    echo "❌ Erreur lors de la récupération des statistiques"
fi

echo ""
echo "🏃 Test de la liste des activités..."
ACTIVITIES_RESPONSE=$(curl -s -X GET "$API_URL/activities?limit=10" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

if [ $? -eq 0 ]; then
    ACTIVITIES_COUNT=$(echo "$ACTIVITIES_RESPONSE" | grep -o '"id"' | wc -l)
    echo "✅ Liste des activités récupérée"
    echo "Nombre d'activités: $ACTIVITIES_COUNT"
    echo "Première activité: $(echo "$ACTIVITIES_RESPONSE" | head -c 200)..."
else
    echo "❌ Erreur lors de la récupération des activités"
fi

echo ""
echo "📈 Test des statistiques enrichies..."
ENRICHED_STATS_RESPONSE=$(curl -s -X GET "$API_URL/activities/enriched/stats?period_days=30" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

if [ $? -eq 0 ]; then
    echo "✅ Statistiques enrichies récupérées"
    echo "Données: $(echo "$ENRICHED_STATS_RESPONSE" | head -c 200)..."
else
    echo "❌ Erreur lors de la récupération des statistiques enrichies"
fi

echo ""
echo "🎯 Test des plans d'entraînement..."
PLANS_RESPONSE=$(curl -s -X GET "$API_URL/workout-plans" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

if [ $? -eq 0 ]; then
    PLANS_COUNT=$(echo "$PLANS_RESPONSE" | grep -o '"id"' | wc -l)
    echo "✅ Plans d'entraînement récupérés"
    echo "Nombre de plans: $PLANS_COUNT"
else
    echo "❌ Erreur lors de la récupération des plans"
fi

echo ""
echo "✅ Tests terminés !" 