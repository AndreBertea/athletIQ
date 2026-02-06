#!/bin/bash
# ================================================
# start_backend_no_reload.sh - Backend sans surveillance fichiers
# ================================================

echo "🚀 Démarrage du backend AthlétIQ (mode production)"
echo "   - Pas de surveillance des fichiers"
echo "   - Pas de rechargement automatique" 
echo "   - Logs optimisés"

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
echo "🏃‍♂️ Lancement d'uvicorn..."
echo "   - Host: 0.0.0.0"
echo "   - Port: 8000"
echo "   - Mode: production"
echo ""

# Lancer uvicorn SANS --reload pour éviter watchfiles
uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level warning \
    --access-log \
    --no-use-colors 