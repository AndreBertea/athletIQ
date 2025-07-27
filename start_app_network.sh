#!/bin/bash
# ================================================
# start_app_network.sh - Démarrage AthlétIQ (mode réseau)
# ================================================

echo "🌐 Démarrage AthlétIQ (mode réseau)"
echo "=================================="
echo "   - Accès réseau autorisé"
echo "   - Accessible depuis tous les appareils"
echo "   - Mode développement avec hot reload"
echo ""

# Arrêter les processus existants
echo "🛑 Arrêt des processus existants..."
pkill -f uvicorn 2>/dev/null
pkill -f vite 2>/dev/null
sleep 2

# Obtenir l'adresse IP du réseau
NETWORK_IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -1)
if [ -z "$NETWORK_IP" ]; then
    NETWORK_IP="192.168.1.188"  # Fallback
fi

echo "📱 Configuration réseau :"
echo "   - IP réseau: $NETWORK_IP"
echo "   - Frontend: http://$NETWORK_IP:3000"
echo "   - Backend: http://$NETWORK_IP:8000"
echo ""

# Démarrer le backend (accès réseau)
echo "🚀 Démarrage du backend..."
cd backend
source venv/bin/activate
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level warning > backend.log 2>&1 &
BACKEND_PID=$!
cd ..

# Attendre que le backend démarre
echo "⏳ Attente du démarrage du backend..."
sleep 3

# Vérifier que le backend répond
if curl -s http://$NETWORK_IP:8000/health > /dev/null; then
    echo "✅ Backend démarré avec succès"
else
    echo "❌ Erreur: Backend non accessible"
    exit 1
fi

# Démarrer le frontend (accès réseau)
echo "🚀 Démarrage du frontend..."
cd frontend
export VITE_API_URL="http://$NETWORK_IP:8000"
nohup bash -c "VITE_API_URL='$VITE_API_URL' npm run dev -- --host" > frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..

# Attendre que le frontend démarre
echo "⏳ Attente du démarrage du frontend..."
sleep 5

# Vérifier que le frontend répond
if curl -s http://$NETWORK_IP:3000 > /dev/null; then
    echo "✅ Frontend démarré avec succès"
else
    echo "❌ Erreur: Frontend non accessible"
    exit 1
fi

# Test CORS rapide
echo "🔍 Test CORS..."
CORS_TEST=$(curl -s -X POST http://$NETWORK_IP:8000/api/v1/auth/login \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -H "Origin: http://$NETWORK_IP:3000" \
    -d "email=test@test.com&password=test" \
    -w "%{http_code}" \
    -o /dev/null)

if [ "$CORS_TEST" = "401" ]; then
    echo "✅ CORS fonctionne correctement"
else
    echo "⚠️ CORS: code $CORS_TEST (vérifiez la configuration)"
fi

echo ""
echo "🎉 Application AthlétIQ démarrée en mode réseau !"
echo "================================================"
echo ""
echo "🌐 URLs d'accès :"
echo "   - Frontend: http://$NETWORK_IP:3000"
echo "   - Backend API: http://$NETWORK_IP:8000"
echo ""
echo "📱 Accessible depuis :"
echo "   - Votre iPhone/iPad: http://$NETWORK_IP:3000"
echo "   - Autres appareils sur le même réseau"
echo ""
echo "📋 Commandes utiles :"
echo "   - Arrêter l'app: ./stop_app.sh"
echo "   - Mode localhost: ./start_app_local.sh"
echo "   - Test réseau: ./test_network_access.sh"
echo "   - Logs backend: tail -f backend/backend.log"
echo "   - Logs frontend: tail -f frontend/frontend.log"
echo ""

# Sauvegarder les PIDs pour l'arrêt
echo $BACKEND_PID > .backend_pid
echo $FRONTEND_PID > .frontend_pid

echo "✅ Application prête ! Accédez depuis n'importe quel appareil sur http://$NETWORK_IP:3000" 