# Guide de Contribution - AthlétIQ

Merci de votre intérêt pour contribuer à AthlétIQ ! Ce guide vous aidera à démarrer.

## 🚀 Démarrage Rapide

### Setup de développement

1. **Fork et clone**
```bash
git clone https://github.com/AndreBertea/stridedelta.git
cd stridedelta
```

2. **Configuration automatique**
```bash
chmod +x scripts/dev-setup.sh
./scripts/dev-setup.sh
```

3. **Ou configuration manuelle**
```bash
# Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Frontend  
cd frontend
npm install
cp .env.example .env
```

## 🏗️ Structure du Projet

```
stridedelta/
├── frontend/          # React + TypeScript + Tailwind
├── backend/           # FastAPI + SQLModel + PostgreSQL
├── docs/              # Documentation
├── scripts/           # Scripts d'automatisation
├── .github/           # CI/CD workflows
└── archive/           # Code legacy
```

## 📝 Standards de Code

### Backend (Python)

#### Style de Code
- **Formatter :** `ruff format`
- **Linter :** `ruff check`
- **Type checker :** `mypy`
- **Ligne max :** 100 caractères

#### Conventions
```python
# Noms de classes en PascalCase
class ActivityService:
    pass

# Noms de fonctions en snake_case
def calculate_pace(distance: float, time: int) -> float:
    pass

# Constantes en UPPER_CASE
API_BASE_URL = "https://api.example.com"

# Docstrings Google style
def compare_activities(plan: WorkoutPlan, actual: Activity) -> PlanVsActual:
    """Compare un plan d'entraînement avec l'activité réelle.
    
    Args:
        plan: Plan d'entraînement prévu
        actual: Activité réellement effectuée
        
    Returns:
        Comparaison détaillée avec écarts et insights
        
    Raises:
        ValueError: Si les données sont invalides
    """
```

#### Architecture
- **Domain-Driven Design** - Entités dans `domain/entities/`
- **Services métier** - Logique dans `domain/services/`
- **Séparation des couches** - Domain / Application / Infrastructure

### Frontend (TypeScript + React)

#### Style de Code
- **Formatter :** `prettier`
- **Linter :** `eslint`
- **Ligne max :** 100 caractères

#### Conventions
```typescript
// Composants en PascalCase
const ActivityCard: React.FC<ActivityCardProps> = ({ activity }) => {
  return <div>...</div>
}

// Hooks en camelCase avec préfixe 'use'
const useAuth = () => {
  // ...
}

// Types en PascalCase avec suffixe descriptif
interface ActivityCardProps {
  activity: Activity
  onSelect?: (id: string) => void
}

// Constantes en UPPER_CASE
const API_ENDPOINTS = {
  ACTIVITIES: '/activities',
  PLANS: '/workout-plans'
} as const
```

#### Structure des Composants
```typescript
// 1. Imports externes
import React, { useState, useEffect } from 'react'
import { useQuery } from 'react-query'

// 2. Imports internes
import { useAuth } from '../hooks/useAuth'
import { ActivityCard } from '../components/ActivityCard'

// 3. Types
interface DashboardProps {
  // ...
}

// 4. Composant
export const Dashboard: React.FC<DashboardProps> = ({ }) => {
  // a. Hooks
  const { user } = useAuth()
  const [filter, setFilter] = useState('')
  
  // b. Queries/Effects
  const { data: activities } = useQuery(...)
  
  // c. Event handlers
  const handleFilterChange = (value: string) => {
    setFilter(value)
  }
  
  // d. Render
  return (
    <div>
      {/* JSX */}
    </div>
  )
}
```

## 🧪 Tests

### Backend (pytest)
```bash
cd backend
pytest tests/ -v --cov=app --cov-report=html
```

#### Structure des tests
```python
# tests/test_auth.py
class TestAuth:
    """Tests d'authentification"""
    
    def test_signup_success(self, client, test_user_data):
        """Test inscription réussie"""
        response = client.post("/api/v1/auth/signup", json=test_user_data)
        assert response.status_code == 200
        
    @pytest.mark.asyncio
    async def test_async_operation(self):
        """Test d'opération asynchrone"""
        result = await some_async_function()
        assert result is not None
```

### Frontend (vitest + testing-library)
```bash
cd frontend
npm test
```

#### Structure des tests
```typescript
// src/test/Login.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { Login } from '../pages/Login'

describe('Login Component', () => {
  test('renders login form', () => {
    render(<Login />)
    expect(screen.getByText('Se connecter')).toBeInTheDocument()
  })
  
  test('validates email format', async () => {
    render(<Login />)
    // Test logic...
  })
})
```

## 🔄 Workflow de Contribution

### 1. Préparation
```bash
# Créer une branche feature
git checkout -b feature/nom-de-la-fonctionnalite

# Ou une branche fix
git checkout -b fix/description-du-bug
```

### 2. Développement

#### Commits
- Messages en français, impératif présent
- Format : `type(scope): description`

```bash
git commit -m "feat(auth): ajouter l'authentification OAuth Strava"
git commit -m "fix(dashboard): corriger le calcul du pace moyen"
git commit -m "docs(api): mettre à jour la documentation des endpoints"
git commit -m "test(activities): ajouter tests pour la synchronisation"
```

**Types de commits :**
- `feat` - Nouvelle fonctionnalité
- `fix` - Correction de bug
- `docs` - Documentation
- `test` - Tests
- `refactor` - Refactoring
- `style` - Formatage, style
- `perf` - Amélioration performance
- `ci` - CI/CD

### 3. Validation
```bash
# Linter + formateur
cd backend && ruff check . && ruff format .
cd frontend && npm run lint && npm run format

# Tests
cd backend && pytest tests/ -v
cd frontend && npm test

# Build
cd frontend && npm run build
```

### 4. Pull Request

#### Template de PR
```markdown
## 📋 Description
Brève description des changements

## 🎯 Type de changement
- [ ] Bug fix
- [ ] Nouvelle fonctionnalité
- [ ] Breaking change
- [ ] Documentation

## 🧪 Tests
- [ ] Tests unitaires ajoutés/mis à jour
- [ ] Tests d'intégration validés
- [ ] Tests manuels effectués

## 📸 Screenshots (si applicable)

## 📝 Checklist
- [ ] Code review auto-effectué
- [ ] Code bien documenté
- [ ] Tests passent
- [ ] Build réussit
```

## 🚨 Issues et Bugs

### Créer une Issue

#### Template Bug Report
```markdown
## 🐛 Description du Bug
Description claire et concise du problème

## 🔄 Étapes pour Reproduire
1. Aller à '...'
2. Cliquer sur '...'
3. Faire défiler jusqu'à '...'
4. Voir l'erreur

## ✅ Comportement Attendu
Ce qui devrait se passer

## 📸 Screenshots
Si applicable

## 💻 Environnement
- OS: [e.g. macOS 14.0]
- Navigateur: [e.g. Chrome 120]
- Version: [e.g. v2.0.0]
```

#### Template Feature Request
```markdown
## 🚀 Feature Request

### 📋 Description
Description claire de la fonctionnalité souhaitée

### 💡 Motivation
Pourquoi cette fonctionnalité serait utile ?

### 📝 Solution Proposée
Comment vous imaginez que cela fonctionne ?

### 🔄 Alternatives
Autres solutions considérées ?
```

## 📚 Documentation

### Mise à jour
- **README.md** - Pour changements majeurs
- **docs/api.md** - Pour nouveaux endpoints
- **docs/architecture.md** - Pour changements d'architecture

### Docstrings/JSDoc
```python
# Python
def calculate_variance(planned: float, actual: float) -> float:
    """Calcule l'écart en pourcentage entre prévu et réel.
    
    Args:
        planned: Valeur planifiée
        actual: Valeur réelle
        
    Returns:
        Écart en pourcentage (positif si actual > planned)
        
    Example:
        >>> calculate_variance(100, 110)
        10.0
    """
```

```typescript
// TypeScript
/**
 * Calcule les métriques d'une activité
 * @param activity - Activité à analyser
 * @param segments - Segments optionnels pour analyse détaillée
 * @returns Métriques calculées avec pace, distance, etc.
 * @example
 * ```ts
 * const metrics = calculateMetrics(activity)
 * console.log(metrics.averagePace) // 6.2
 * ```
 */
function calculateMetrics(activity: Activity, segments?: Segment[]): ActivityMetrics
```

## 🏆 Bonnes Pratiques

### Performance
- **Backend :** Utiliser `async/await`, pagination, index DB
- **Frontend :** Lazy loading, React.memo, code splitting

### Sécurité
- Jamais de secrets en dur dans le code
- Validation côté client ET serveur
- Sanitisation des entrées utilisateur

### UX/UI
- Mobile-first design
- Messages d'erreur clairs
- États de chargement
- Confirmation pour actions destructives

### Accessibilité
- Attributs ARIA appropriés
- Navigation clavier
- Contraste suffisant
- Textes alternatifs pour images

## 🎯 Roadmap

### Sprint 2 (En cours)
- [ ] Interface création plans d'entraînement
- [ ] Calendrier des entraînements
- [ ] Comparaisons visuelles prévision vs réel

### Sprint 3 (À venir)
- [ ] Analytics avancées
- [ ] Prédictions ML
- [ ] Export de données

### Sprint 4 (Futur)
- [ ] Support autres plateformes (Garmin, Polar)
- [ ] Mode équipe
- [ ] Application mobile

## 💬 Communication

- **Discussions :** GitHub Discussions pour questions
- **Issues :** GitHub Issues pour bugs/features
- **Discord :** [Lien Discord] pour discussions en temps réel

## 📜 Code de Conduite

### Notre Engagement
Nous nous engageons à maintenir un environnement ouvert et accueillant pour tous.

### Standards
- Utiliser un langage accueillant et inclusif
- Respecter les différents points de vue
- Accepter les critiques constructives
- Se concentrer sur ce qui est le mieux pour la communauté

### Application
Les comportements inacceptables peuvent être signalés à [email].

---

**Merci de contribuer à AthlétIQ ! 🏃‍♂️💪** 