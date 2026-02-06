#!/bin/bash
# ================================================
# start_frontend_local.sh - Frontend pour localhost uniquement
# ================================================

echo "🚀 Démarrage du frontend AthlétIQ (mode localhost)"
echo "   - Accès local uniquement"
echo "   - Mode développement avec hot reload"
echo "   - Sécurisé pour le développement local"

# Aller dans le répertoire frontend
cd "$(dirname "$0")"

# Vérifier que les dépendances sont installées
if [ ! -d "node_modules" ]; then
    echo "❌ node_modules non trouvé. Exécutez: npm install"
    exit 1
fi

echo ""
echo "🏃‍♂️ Lancement de Vite en mode localhost..."
echo "   - Host: localhost (accès local uniquement)"
echo "   - Port: 4000"
echo "   - Mode: développement"
echo ""

# Lancer Vite en mode localhost uniquement
npm run dev -- --port 4000 