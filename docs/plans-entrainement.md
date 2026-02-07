# Plans d'Entraînement - AthlétIQ

## 🎯 Vue d'ensemble

La fonctionnalité **Plans d'Entraînement** d'AthlétIQ permet aux utilisateurs de créer, planifier et suivre leurs entraînements sportifs, avec une comparaison précise entre les objectifs prévus et les performances réelles.

## ✨ Fonctionnalités Principales

### 📅 Gestion des Plans
- **Création de plans** avec objectifs détaillés (distance, durée, allure, dénivelé)
- **Types d'entraînement** : Course facile, Intervalles, Tempo, Sortie longue, Récupération, Fartlek, Côtes, Course
- **Zones d'intensité** : Zone 1-5 avec descriptions détaillées
- **Calendrier visuel** avec vue hebdomadaire
- **Filtres et recherche** pour organiser les plans



### 🎨 Interface Utilisateur
- **Dashboard intégré** avec aperçu des plans récents
- **Calendrier interactif** avec navigation par semaines
- **Modals de création/édition** avec formulaires complets
- **Statistiques visuelles** avec graphiques Plotly.js
- **Design responsive** mobile-first

## 🏗️ Architecture Technique

### Backend (FastAPI)

#### Entités
```python
# app/domain/entities/workout_plan.py
class WorkoutPlan:
    id: UUID
    user_id: UUID
    name: str
    workout_type: WorkoutType  # Enum avec 8 types
    planned_date: date
    planned_distance: float  # km
    planned_duration: Optional[int]  # secondes
    planned_pace: Optional[float]  # min/km
    intensity_zone: Optional[IntensityZone]  # Zone 1-5
    is_completed: bool
    completion_percentage: Optional[float]
    actual_activity_id: Optional[UUID]
```

#### Services
```python
# app/domain/services/analysis_service.py
class AnalysisService:
    def compare_plan_vs_actual(plan, activity) -> PlanVsActual
    def calculate_prediction_accuracy(comparisons) -> AccuracyReport
    def generate_insights(comparison) -> List[str]
```

#### API Routes
```
POST   /api/v1/workout-plans              # Créer un plan
GET    /api/v1/workout-plans              # Liste des plans (avec filtres)
GET    /api/v1/workout-plans/{id}         # Détail d'un plan
PATCH  /api/v1/workout-plans/{id}         # Modifier un plan
DELETE /api/v1/workout-plans/{id}         # Supprimer un plan
```

### Frontend (React + TypeScript)

#### Services
```typescript
// src/services/workoutPlanService.ts
export const workoutPlanService = {
  createWorkoutPlan(plan: WorkoutPlanCreate): Promise<WorkoutPlan>
  getWorkoutPlans(params?: FilterParams): Promise<WorkoutPlan[]>
  updateWorkoutPlan(id: string, updates: WorkoutPlanUpdate): Promise<WorkoutPlan>
  deleteWorkoutPlan(id: string): Promise<void>
}
```

#### Pages
- **`/plans`** - Gestion complète des plans d'entraînement
- **Dashboard** - Aperçu intégré des plans récents

#### Composants
- `WorkoutPlanCard` - Affichage d'un plan dans le calendrier
- `WorkoutPlanModal` - Formulaire de création/édition
- `ConfirmationModal` - Confirmations d'actions

## 🚀 Utilisation

### 1. Créer un Plan d'Entraînement

1. Naviguez vers **Plans d'Entraînement** dans le menu
2. Cliquez sur **"Nouveau Plan"**
3. Remplissez le formulaire :
   - **Nom** : Nom descriptif du plan
   - **Type** : Sélectionnez le type d'entraînement
   - **Date** : Date prévue pour l'entraînement
   - **Distance** : Objectif en kilomètres
   - **Durée** : Temps prévu (optionnel)
   - **Allure** : Pace cible en min/km (optionnel)
   - **Zone d'intensité** : Zone d'entraînement (optionnel)
   - **Description** : Notes détaillées
4. Cliquez sur **"Créer"**





## 🎨 Types d'Entraînement

| Type | Description | Zone d'Intensité | Objectif |
|------|-------------|------------------|----------|
| **Course facile** | Endurance fondamentale | Zone 1-2 | Récupération active |
| **Intervalles** | Alternance effort/récupération | Zone 4-5 | VO2 Max |
| **Tempo** | Allure soutenue | Zone 3-4 | Seuil lactique |
| **Sortie longue** | Endurance prolongée | Zone 2-3 | Endurance de base |
| **Récupération** | Activité légère | Zone 1 | Récupération |
| **Fartlek** | Jeu d'allures | Zone 2-4 | Variabilité |
| **Côtes** | Montées répétées | Zone 4-5 | Force |
| **Course** | Compétition | Zone 3-5 | Performance |

## 🔧 Configuration

### Variables d'Environnement

```env
# Backend
DATABASE_URL=postgresql://...
JWT_SECRET_KEY=...
STRAVA_CLIENT_ID=...
STRAVA_CLIENT_SECRET=...

# Frontend
VITE_API_URL=http://localhost:8000/api/v1
```

### Base de Données

La table `workoutplan` est créée automatiquement via Alembic :

```sql
CREATE TABLE workoutplan (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES user(id),
    name VARCHAR NOT NULL,
    workout_type workouttype NOT NULL,
    planned_date DATE NOT NULL,
    planned_distance FLOAT NOT NULL,
    planned_duration INTEGER,
    planned_pace FLOAT,
    intensity_zone intensityzone,
    is_completed BOOLEAN DEFAULT FALSE,
    completion_percentage FLOAT,
    actual_activity_id UUID REFERENCES activity(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

## 🧪 Tests

### Backend
```bash
cd backend
pytest tests/test_workout_plans.py
```

### Frontend
```bash
cd frontend
npm test -- --testPathPattern=WorkoutPlans
```

## 🚀 Déploiement

### Développement Local
```bash
# Backend
cd backend
uvicorn app.main:app --reload

# Frontend
cd frontend
npm run dev
```

### Production
```bash
# Backend (Render)
git push origin main  # Déploiement automatique

# Frontend (Vercel)
npm run build
vercel --prod
```

## 📊 Statistiques d'Utilisation

- **Plans créés** : Nombre total de plans d'entraînement
- **Taux de réalisation** : Moyenne des pourcentages de réalisation
- **Plans avec comparaison** : Plans liés à des activités Strava
- **Types préférés** : Répartition par type d'entraînement

## 🔮 Évolutions Futures

### Sprint 2
- [ ] **Templates de plans** prédéfinis
- [ ] **Planification automatique** basée sur l'historique
- [ ] **Notifications** et rappels
- [ ] **Partage de plans** entre utilisateurs

### Sprint 3
- [ ] **IA prédictive** pour les objectifs
- [ ] **Recommandations personnalisées**
- [ ] **Analyse de tendances** avancée
- [ ] **Intégration multi-sources** (Garmin, Polar)

### Sprint 4
- [ ] **Application mobile** React Native
- [ ] **Mode hors-ligne**
- [ ] **Synchronisation cloud**
- [ ] **API publique** pour intégrations

## 📝 Notes de Développement

### Bonnes Pratiques
- ✅ **Validation des données** côté client et serveur
- ✅ **Gestion d'erreurs** complète avec messages utilisateur
- ✅ **Optimistic updates** pour une UX fluide
- ✅ **Cache intelligent** avec React Query
- ✅ **Tests unitaires** et d'intégration

### Performance
- **Lazy loading** des comparaisons
- **Pagination** pour les listes longues
- **Cache Redis** pour les statistiques
- **Indexation** optimisée en base de données

### Sécurité
- **Authentification** JWT obligatoire
- **Validation** des permissions utilisateur
- **Sanitisation** des données d'entrée
- **Rate limiting** sur les API critiques

---

**Version :** 2.0.0  
**Dernière mise à jour :** Décembre 2024  
**Auteur :** Équipe AthlétIQ 