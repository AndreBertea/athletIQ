#!/bin/bash
# ================================================
# start_backend_local.sh - Backend pour localhost uniquement
# ================================================

echo "🚀 Démarrage du backend AthlétIQ (mode localhost)"
echo "   - Accès local uniquement (127.0.0.1)"
echo "   - Enrichissement automatique désactivé par défaut"
echo "   - Logs optimisés"
echo "   - Mode développement local"

# Aller dans le répertoire backend
cd "$(dirname "$0")"

# Activer l'environnement virtuel
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✅ Environnement virtuel activé"
else
    echo "⚠️  Environnement virtuel non trouvé, utilisation de l'environnement système"
fi

# Vérifier que les dépendances sont installées
python -c "import fastapi" 2>/dev/null || {
    echo "❌ FastAPI non installé. Exécutez: pip install -r requirements.txt"
    exit 1
}

echo ""
echo "🏃‍♂️ Lancement d'uvicorn en mode localhost..."
echo "   - Host: 127.0.0.1 (localhost uniquement)"
echo "   - Port: 4100"
echo "   - Mode: production (pas de reload)"
echo "   - Logs: warning uniquement"
echo ""

# Lancer uvicorn en mode localhost uniquement
uvicorn app.main:app \
    --host 127.0.0.1 \
    --port 4100 \
    --log-level warning \
    --no-access-log \
    --no-use-colors 