# API Documentation - AthlétIQ v2.0

## Base URL

- **Production :** `https://stridedelta-api.onrender.com/api/v1`
- **Development :** `http://localhost:8000/api/v1`

## Authentification

L'API utilise des **JWT (JSON Web Tokens)** avec le pattern Bearer :

```http
Authorization: Bearer <access_token>
```

### Tokens
- **Access Token** - Durée : 30 minutes
- **Refresh Token** - Durée : 7 jours

## Endpoints

### 🔐 Authentification

#### Inscription
```http
POST /auth/signup
```

**Body :**
```json
{
  "email": "user@example.com",
  "password": "securepassword123",
  "full_name": "John Doe"
}
```

**Response :**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

#### Connexion
```http
POST /auth/login
Content-Type: application/x-www-form-urlencoded
```

**Body :**
```
email=user@example.com&password=securepassword123
```

#### Profil Utilisateur
```http
GET /auth/me
Authorization: Bearer <token>
```

**Response :**
```json
{
  "id": "uuid-string",
  "email": "user@example.com",
  "full_name": "John Doe",
  "is_active": true,
  "created_at": "2024-01-01T10:00:00Z"
}
```

#### Refresh Token
```http
POST /auth/refresh
```

**Body :**
```json
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

### 🔗 OAuth Strava

#### Initier Connexion Strava
```http
GET /auth/strava/login
Authorization: Bearer <token>
```

**Response :**
```json
{
  "authorization_url": "https://www.strava.com/oauth/authorize?client_id=..."
}
```

#### Callback OAuth (automatique)
```http
GET /auth/strava/callback?code=<auth_code>&state=<user_id>
```

#### Statut Connexion Strava
```http
GET /auth/strava/status
Authorization: Bearer <token>
```

**Response :**
```json
{
  "connected": true,
  "athlete_id": 12345678,
  "scope": "read,activity:read_all",
  "expires_at": "2024-12-31T23:59:59Z",
  "is_expired": false
}
```

### 📊 Activités

#### Liste des Activités
```http
GET /activities?limit=50&offset=0&activity_type=Run
Authorization: Bearer <token>
```

**Paramètres :**
- `limit` (optional) - Nombre d'activités (max: 200, défaut: 50)
- `offset` (optional) - Décalage pour pagination (défaut: 0)
- `activity_type` (optional) - Filtrer par type (Run, TrailRun, Ride, etc.)

**Response :**
```json
[
  {
    "id": "uuid-string",
    "name": "Morning Run",
    "activity_type": "Run",
    "start_date": "2024-01-15T07:30:00Z",
    "distance": 5000.0,
    "moving_time": 1800,
    "average_pace": 6.0,
    "location_city": "Paris",
    "strava_id": 123456789,
    "created_at": "2024-01-15T08:00:00Z",
    "updated_at": "2024-01-15T08:00:00Z"
  }
]
```

#### Détail d'une Activité
```http
GET /activities/{activity_id}
Authorization: Bearer <token>
```

**Response :**
```json
{
  "id": "uuid-string",
  "name": "Morning Run",
  "activity_type": "Run",
  "start_date": "2024-01-15T07:30:00Z",
  "distance": 5000.0,
  "moving_time": 1800,
  "elapsed_time": 1850,
  "total_elevation_gain": 100.0,
  "average_speed": 2.78,
  "average_heartrate": 150.0,
  "average_pace": 6.0,
  "streams_data": {
    "time": [0, 30, 60, ...],
    "latlng": [[48.8566, 2.3522], ...],
    "altitude": [50.0, 52.0, ...],
    "distance": [0, 100, 200, ...]
  },
  "laps_data": [
    {
      "start_index": 0,
      "end_index": 120,
      "distance": 1000.0,
      "moving_time": 360
    }
  ]
}
```

#### Statistiques d'Activités
```http
GET /activities/stats?period_days=30
Authorization: Bearer <token>
```

**Response :**
```json
{
  "total_activities": 15,
  "total_distance": 75.5,
  "total_time": 18000,
  "average_pace": 6.2,
  "activities_by_type": {
    "Run": 12,
    "TrailRun": 3
  },
  "distance_by_month": {
    "2024-01": 45.2,
    "2024-02": 30.3
  }
}
```

### 🎯 Plans d'Entraînement

#### Créer un Plan
```http
POST /workout-plans
Authorization: Bearer <token>
```

**Body :**
```json
{
  "name": "Sortie longue dimanche",
  "workout_type": "long_run",
  "planned_date": "2024-01-21",
  "planned_distance": 15.0,
  "planned_duration": 5400,
  "planned_pace": 6.5,
  "intensity_zone": "zone_2",
  "description": "Course en endurance fondamentale"
}
```

#### Liste des Plans
```http
GET /workout-plans?start_date=2024-01-01&end_date=2024-01-31
Authorization: Bearer <token>
```

#### Comparaison Plan vs Réel
```http
GET /workout-plans/{plan_id}/comparison
Authorization: Bearer <token>
```

**Response :**
```json
{
  "plan": {
    "id": "uuid-string",
    "name": "Sortie longue dimanche",
    "planned_distance": 15.0,
    "planned_pace": 6.5,
    "is_completed": true
  },
  "actual": {
    "id": "uuid-string",
    "distance": 14500.0,
    "moving_time": 5220,
    "average_pace": 6.2
  },
  "variance_distance": -3.3,
  "variance_pace": -4.6,
  "completion_rate": 96.7,
  "insights": [
    "✅ Distance respectée avec précision",
    "🚀 Allure plus rapide que prévu (4.6%)",
    "✅ Type d'entraînement respecté"
  ],
  "performance_score": 94.5
}
```

#### Lier Activité à un Plan
```http
POST /workout-plans/{plan_id}/link-activity/{activity_id}
Authorization: Bearer <token>
```

### 🔄 Synchronisation

#### Synchroniser Strava
```http
POST /sync/strava
Authorization: Bearer <token>
```

**Response :**
```json
{
  "message": "Strava sync initiated",
  "status": "pending",
  "athlete_id": 12345678
}
```

## Codes d'Erreur

### Erreurs d'Authentification
```json
// 401 Unauthorized
{
  "detail": "Could not validate credentials"
}

// 403 Forbidden  
{
  "detail": "Not enough permissions"
}
```

### Erreurs de Validation
```json
// 422 Validation Error
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### Erreurs Métier
```json
// 400 Bad Request
{
  "detail": "Email already registered"
}

// 404 Not Found
{
  "detail": "Activity not found"
}
```

## Rate Limiting

- **Authentification :** 5 tentatives/minute
- **API générale :** 1000 requêtes/heure/utilisateur
- **Sync Strava :** 1 requête/minute

## Pagination

Les listes utilisent une pagination par offset/limit :

```http
GET /activities?limit=20&offset=40
```

**Headers de réponse :**
```http
X-Total-Count: 150
X-Page-Size: 20
X-Current-Page: 3
```

## Webhooks (à venir)

Support planifié pour les webhooks Strava pour synchronisation temps réel.

## SDK et Clients

### JavaScript/TypeScript
```bash
npm install @stridedelta/api-client
```

```javascript
import { StrideDeltaClient } from '@stridedelta/api-client'

const client = new StrideDeltaClient({
  baseURL: 'https://stridedelta-api.onrender.com/api/v1',
  token: 'your-jwt-token'
})

const activities = await client.activities.list()
```

## Exemples d'Intégration

### Curl
```bash
# Connexion
curl -X POST https://stridedelta-api.onrender.com/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "email=user@example.com&password=password123"

# Récupérer activités
curl -X GET https://stridedelta-api.onrender.com/api/v1/activities \
  -H "Authorization: Bearer <token>"
```

### Python
```python
import requests

# Authentification
response = requests.post(
    'https://stridedelta-api.onrender.com/api/v1/auth/login',
    data={'email': 'user@example.com', 'password': 'password123'}
)
token = response.json()['access_token']

# API call
headers = {'Authorization': f'Bearer {token}'}
activities = requests.get(
    'https://stridedelta-api.onrender.com/api/v1/activities',
    headers=headers
).json()
```

## Documentation Interactive

La documentation interactive Swagger UI est disponible à :
**https://stridedelta-api.onrender.com/docs** 