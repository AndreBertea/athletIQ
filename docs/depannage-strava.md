# Guide de Dépannage - Connexion Strava

## Problèmes Courants et Solutions

### 1. Erreur : `TypeError: can't access property "get", this.api is undefined`

**Cause :** Problème de contexte `this` dans les méthodes des services.

**Solution :** Les méthodes doivent être appelées avec le bon contexte.

**Code corrigé :**
```typescript
// ❌ Incorrect
const { data: stravaStatus } = useQuery({
  queryKey: ['strava-status'],
  queryFn: authService.getStravaStatus, // Problème de contexte
})

// ✅ Correct
const { data: stravaStatus } = useQuery({
  queryKey: ['strava-status'],
  queryFn: () => authService.getStravaStatus(), // Appel avec fonction wrapper
})
```

### 2. Erreur : `ModuleNotFoundError: No module named 'app'`

**Cause :** Tentative de lancement du backend depuis le mauvais répertoire.

**Solution :** Toujours lancer le backend depuis le répertoire `backend/`.

```bash
# ❌ Incorrect
cd /path/to/athletIQ
python -m uvicorn app.main:app --port 8000

# ✅ Correct
cd /path/to/athletIQ/backend
python -m uvicorn app.main:app --port 8000
```

### 3. Erreur : `403 Forbidden - Not authenticated`

**Cause :** L'utilisateur n'est pas connecté ou le token est invalide.

**Solution :**
1. Vérifier que l'utilisateur est connecté
2. Vérifier que le token d'accès est présent dans le localStorage
3. Vérifier que le token n'est pas expiré

### 4. Erreur : `Connection refused`

**Cause :** Le backend n'est pas démarré ou n'écoute pas sur le bon port.

**Solution :**
1. Vérifier que le backend est démarré : `curl http://localhost:8000/health`
2. Vérifier les logs du backend pour les erreurs
3. S'assurer qu'aucun autre service n'utilise le port 8000

## Scripts de Diagnostic

### Test de Connexion Complet
```bash
./scripts/test-connection.sh
```

Ce script teste :
- Accessibilité du backend
- Accessibilité du frontend
- Création d'un utilisateur de test
- Endpoints Strava avec authentification

### Démarrage Automatique
```bash
./scripts/start-app.sh
```

Ce script :
- Nettoie les processus existants
- Démarre le backend
- Démarre le frontend
- Attend que les services soient prêts
- Affiche les URLs d'accès

## Vérification Manuelle

### 1. Vérifier le Backend
```bash
curl http://localhost:8000/health
```
**Réponse attendue :** `{"status":"healthy","version":"2.0.0"}`

### 2. Vérifier l'Authentification
```bash
# Créer un utilisateur de test
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "test123", "full_name": "Test User"}'

# Tester l'endpoint Strava avec le token
curl -X GET http://localhost:8000/api/v1/auth/strava/status \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### 3. Vérifier le Frontend
```bash
curl http://localhost:3000
```
**Réponse attendue :** Page HTML du frontend

## Configuration Requise

### Variables d'Environnement Backend
```bash
# backend/.env
STRAVA_CLIENT_ID=your_strava_client_id
STRAVA_CLIENT_SECRET=your_strava_client_secret
JWT_SECRET_KEY=your_jwt_secret
DATABASE_URL=sqlite:///./athletiq.db
```

### Variables d'Environnement Frontend
```bash
# frontend/.env
VITE_API_URL=http://localhost:8000/api/v1
```

## Logs Utiles

### Backend
```bash
cd backend
python -m uvicorn app.main:app --port 8000 --log-level debug
```

### Frontend
```bash
cd frontend
npm run dev
```

## Problèmes de CORS

Si vous rencontrez des erreurs CORS :

1. Vérifier la configuration CORS dans `backend/app/main.py`
2. S'assurer que le frontend fait des requêtes vers le bon port
3. Vérifier que le proxy Vite est configuré correctement

## Support

Si les problèmes persistent :
1. Vérifier les logs complets du backend et frontend
2. Utiliser le script de test de connexion
3. Vérifier la configuration des variables d'environnement
4. S'assurer que tous les services sont démarrés dans le bon ordre 