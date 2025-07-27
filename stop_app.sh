#!/bin/bash
# ================================================
# stop_app.sh - Arrêt d'AthlétIQ
# ================================================

echo "🛑 Arrêt d'AthlétIQ..."

# Arrêter les processus uvicorn (backend)
echo "📡 Arrêt du backend..."
pkill -f "uvicorn.*app.main:app" 2>/dev/null || echo "   - Aucun processus backend trouvé"

# Arrêter les processus vite (frontend)
echo "🌐 Arrêt du frontend..."
pkill -f "vite.*--host" 2>/dev/null || echo "   - Aucun processus frontend trouvé"

# Attendre un peu pour que les processus se terminent
sleep 2

# Vérifier qu'il ne reste plus de processus
BACKEND_PROCESSES=$(pgrep -f "uvicorn.*app.main:app" | wc -l)
FRONTEND_PROCESSES=$(pgrep -f "vite.*--host" | wc -l)

if [ "$BACKEND_PROCESSES" -eq 0 ] && [ "$FRONTEND_PROCESSES" -eq 0 ]; then
    echo "✅ AthlétIQ arrêté avec succès"
else
    echo "⚠️  Certains processus pourraient encore être en cours d'exécution"
    echo "   - Backend: $BACKEND_PROCESSES processus"
    echo "   - Frontend: $FRONTEND_PROCESSES processus"
fi

echo "" 