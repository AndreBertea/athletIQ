# Configuration de l'API - AthlétIQ

## Configuration de l'URL de Base

### Frontend Configuration

L'URL de base de l'API est configurée dans le frontend via la variable d'environnement `VITE_API_URL`.

**Fichier :** `frontend/src/services/authService.ts`
```typescript
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'
```

### Configuration par Défaut

Par défaut, l'application utilise `/api/v1` comme URL de base, ce qui fonctionne avec le proxy Vite configuré dans `vite.config.ts`.

### Proxy Vite

Le proxy Vite redirige automatiquement les requêtes `/api/*` vers le backend :

**Fichier :** `frontend/vite.config.ts`
```typescript
server: {
  port: 3000,
  strictPort: false, // Permet de chercher un port libre si 3000 est occupé
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  },
}
```

## Configuration des Variables d'Environnement

### Frontend (.env.local)

Créez un fichier `.env.local` dans le répertoire `frontend/` :

```bash
# Configuration de l'API
VITE_API_URL=/api/v1

# Configuration de développement
VITE_DEV_MODE=true
```

### Backend (.env)

Créez un fichier `.env` dans le répertoire `backend/` :

```bash
# Configuration Strava
STRAVA_CLIENT_ID=your_strava_client_id
STRAVA_CLIENT_SECRET=your_strava_client_secret

# Configuration JWT
JWT_SECRET_KEY=your_jwt_secret_key

# Configuration Base de Données
DATABASE_URL=sqlite:///./athletiq.db

# Configuration Serveur
HOST=0.0.0.0
PORT=8000
```

## Ports Utilisés

### Ports par Défaut

- **Backend :** 8000
- **Frontend :** 3000 (peut changer si occupé)

### Gestion des Ports Occupés

Le frontend utilise `strictPort: false` dans la configuration Vite, ce qui permet de chercher automatiquement un port libre si le port 3000 est occupé.

Les scripts de test et de démarrage vérifient automatiquement les ports 3000-3005 pour détecter le frontend.

## Configuration CORS

Le backend est configuré pour accepter les requêtes depuis plusieurs origines :

**Fichier :** `backend/app/main.py`
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", 
        "http://localhost:3001", 
        "http://localhost:3002", 
        "http://localhost:3003",
        "http://localhost:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Test de la Configuration

### Script de Test Automatique

Utilisez le script de test pour vérifier que tout fonctionne :

```bash
./scripts/test-connection.sh
```

Ce script teste :
- Accessibilité du backend
- Accessibilité du frontend (détection automatique du port)
- Endpoints API avec authentification
- Endpoints Strava

### Test Manuel

#### Test du Backend
```bash
curl http://localhost:8000/health
```

#### Test du Frontend
```bash
curl http://localhost:3000
# ou
curl http://localhost:3001
# ou
curl http://localhost:3002
# etc.
```

#### Test de l'API avec Authentification
```bash
# Créer un utilisateur
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "test123", "full_name": "Test User"}'

# Tester l'endpoint Strava
curl -X GET http://localhost:8000/api/v1/auth/strava/status \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

## Dépannage

### Problèmes Courants

1. **Port 8000 occupé**
   ```bash
   lsof -i:8000
   kill -9 PID
   ```

2. **Ports frontend occupés**
   ```bash
   lsof -i:3000-3005
   ./scripts/clean-dev.sh
   ```

3. **Problèmes de proxy**
   - Vérifier que le backend est démarré sur le port 8000
   - Vérifier la configuration CORS
   - Vérifier que le proxy Vite est configuré

4. **Variables d'environnement non chargées**
   - Vérifier que les fichiers `.env` sont dans les bons répertoires
   - Redémarrer les services après modification des variables

### Scripts Utiles

- **Nettoyage :** `./scripts/clean-dev.sh`
- **Démarrage :** `./scripts/start-app.sh`
- **Test :** `./scripts/test-connection.sh`

## URLs d'Accès

- **Frontend :** http://localhost:3000 (ou port détecté)
- **Backend API :** http://localhost:8000/api/v1
- **Documentation API :** http://localhost:8000/docs
- **Health Check :** http://localhost:8000/health 