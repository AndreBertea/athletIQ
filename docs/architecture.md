# Architecture AthlétIQ v2.0

## Vue d'ensemble

AthlétIQ suit une architecture moderne **3-tiers** avec séparation claire des responsabilités :

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FRONTEND      │    │    BACKEND      │    │   DATABASE      │
│   React + TS    │◄──►│  FastAPI + DDD  │◄──►│  PostgreSQL     │
│   Tailwind CSS  │    │   SQLModel      │    │   Supabase      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Frontend Architecture

### Structure des Composants

```
src/
├── pages/              # Pages principales (routing)
├── components/         # Composants réutilisables
├── contexts/           # React contexts (état global)
├── hooks/              # Custom hooks
├── services/           # API calls et logique métier
├── types/              # Types TypeScript
└── utils/              # Fonctions utilitaires
```

### Patterns Utilisés

- **Component Composition** - Composants modulaires et réutilisables
- **Custom Hooks** - Logique métier extraite (useAuth, useActivities)
- **Context API** - État d'authentification global
- **React Query** - Cache et synchronisation des données serveur

## Backend Architecture (DDD)

### Couches et Responsabilités

```
app/
├── domain/             # 🏛️ DOMAIN LAYER
│   ├── entities/       # Entités métier (User, Activity, WorkoutPlan)
│   └── services/       # Services métier (AnalysisService, SegmentService)
├── api/                # 🌐 APPLICATION LAYER  
│   └── routes/         # Endpoints REST + validation
├── core/               # ⚙️ INFRASTRUCTURE LAYER
│   ├── database.py     # Configuration ORM
│   └── settings.py     # Configuration app
└── auth/               # 🔐 INFRASTRUCTURE LAYER
    ├── jwt.py          # Gestion JWT
    └── strava_oauth.py # OAuth Strava
```

### Domain-Driven Design

#### Entités Métier
- **User** - Utilisateur avec authentification
- **Activity** - Activité sportive réelle (données Strava)
- **WorkoutPlan** - Plan d'entraînement (prévision)
- **StravaAuth** - Tokens OAuth chiffrés

#### Services Métier
- **AnalysisService** - Comparaison prévision vs réel
- **SegmentService** - Logique de segmentation unifiée

## Flux de Données

### Authentification
```
1. Frontend → POST /auth/login → Backend
2. Backend → JWT + Refresh Token → Frontend
3. Frontend → localStorage → Auto-refresh
4. Backend → Middleware JWT → Protection routes
```

### Synchronisation Strava
```
1. Frontend → OAuth Strava → Autorisation
2. Backend → Exchange code → Tokens chiffrés
3. Backend → Fetch activities → Base de données
4. Frontend → React Query → Cache local
```

### Prévision vs Réel
```
1. Utilisateur → Créer WorkoutPlan → Backend
2. Activité réelle → Strava → Synchronisation
3. AnalysisService → Comparaison → Insights
4. Frontend → Visualisation → Dashboard
```

## Patterns Architecturaux

### Repository Pattern
```python
# Abstraction accès données
class ActivityRepository:
    async def get_by_user(self, user_id: UUID) -> List[Activity]
    async def create(self, activity: ActivityCreate) -> Activity
```

### Service Layer Pattern
```python
# Logique métier centralisée
class AnalysisService:
    def compare_plan_vs_actual(self, plan, activity) -> PlanVsActual
```

### Factory Pattern
```python
# Configuration centralisée
def create_app() -> FastAPI:
    app = FastAPI(...)
    configure_middleware(app)
    return app
```

## Sécurité

### Authentification
- **JWT** avec access/refresh tokens
- **OAuth 2.0** pour Strava (scopes limités)
- **Chiffrement AES** des tokens stockés

### Protection
- **CORS** configuré pour domaines autorisés
- **Rate limiting** sur endpoints sensibles
- **Validation** Pydantic sur toutes les entrées
- **SQL injection** protection via SQLModel

## Performance

### Frontend
- **Code splitting** automatique (Vite)
- **Lazy loading** des composants
- **React Query** pour cache intelligent
- **Bundle optimization** avec tree-shaking

### Backend
- **Connection pooling** PostgreSQL
- **Pagination** sur listes d'activités
- **Index** sur colonnes fréquemment requêtées
- **Async/await** pour I/O non-bloquant

## Monitoring & Observabilité

### Health Checks
```
GET /health → Status application
GET /api/v1/* → Documentation automatique
```

### Logging
```python
# Logging structuré
logger.info("User authenticated", extra={"user_id": user.id})
```

### Métriques
- **GitHub Actions** - CI/CD status
- **Vercel Analytics** - Web vitals
- **Render Metrics** - API performance

## Déploiement

### Environnements
```
Development  → Local (Docker Compose)
Staging      → Pull Request previews
Production   → Render + Vercel
```

### CI/CD Pipeline
```
Commit → Tests → Lint → Build → Deploy
   ↓        ↓      ↓       ↓       ↓
  Git   → pytest → ruff → Docker → Render
        → vitest → eslint → build → Vercel
```

## Extensibilité

### Ajout Nouvelles Sources
```python
# Interface pour autres APIs (Garmin, Polar)
class ActivityProvider:
    async def fetch_activities(self) -> List[Activity]
    
class GarminProvider(ActivityProvider):
    async def fetch_activities(self) -> List[Activity]
```

### Nouveaux Types d'Analyse
```python
# Service extensible
class AnalysisService:
    def register_analyzer(self, analyzer: ActivityAnalyzer)
    def analyze(self, activity: Activity) -> AnalysisResult
```

## Bonnes Pratiques Appliquées

### Code Quality
- **Type safety** - TypeScript + Pydantic
- **Linting** - ESLint + Ruff
- **Testing** - Vitest + Pytest
- **Documentation** - JSDoc + Docstrings

### Architecture
- **Single Responsibility** - Une classe, une responsabilité
- **Dependency Injection** - FastAPI dependencies
- **Interface Segregation** - Petites interfaces spécialisées
- **Open/Closed** - Extension sans modification

Cette architecture garantit **maintenabilité**, **scalabilité** et **testabilité** pour l'évolution future d'AthlétIQ. 