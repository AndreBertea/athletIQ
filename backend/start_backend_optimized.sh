#!/bin/bash
# ================================================
# start_backend_optimized.sh - Backend optimisé pour accès réseau
# ================================================

echo "🚀 Démarrage du backend AthlétIQ (mode réseau)"
echo "   - Accès réseau autorisé (0.0.0.0)"
echo "   - Enrichissement automatique désactivé par défaut"
echo "   - Logs optimisés"
echo "   - Mode production réseau"

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
echo "🏃‍♂️ Lancement d'uvicorn en mode réseau..."
echo "   - Host: 0.0.0.0 (accès réseau autorisé)"
echo "   - Port: 8000"
echo "   - Mode: production (pas de reload)"
echo "   - Logs: warning uniquement"
echo ""

# Lancer uvicorn SANS --reload pour éviter watchfiles
# Utiliser --log-level warning pour réduire les logs
uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level warning \
    --no-access-log \
    --no-use-colors 