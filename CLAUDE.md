# CLAUDE.md — Instructions pour Claude Code

## Contexte du projet

athletIQ est une application d'analyse sportive connectee a Strava.
- **Backend** : FastAPI (Python 3.12) + SQLModel + PostgreSQL 15 + Redis 7
- **Frontend** : React 18 + TypeScript + Vite + Tailwind CSS
- **Auth** : JWT + OAuth 2.0 (Strava, Google)
- **Deploiement** : Docker Compose (dev), Render.com + Vercel (prod)
- **Ancien nom** : StrideDelta (les conteneurs Docker utilisent encore ce nom)

## Instruction obligatoire

**A CHAQUE DEBUT D'ITERATION ou de nouvelle session, tu DOIS :**

1. Lire le plan actif :
   - **UX/UI frontend** : `/Users/andrebertea/Projects/athletIQ/UX_UI_PLAN.md` (**focus actuel**)
   - Pipeline de donnees : `/Users/andrebertea/Projects/athletIQ/DATA_AQI_PLAN.md` (termine)
2. Identifier les taches `[ ]` (a faire) et `[~]` (en cours)
3. Ne travailler QUE sur la tache assignee ou la prochaine tache non terminee dans l'ordre des etapes
4. Mettre a jour le statut de la tache dans le plan actif :
   - `[~]` quand tu commences a travailler dessus
   - `[x]` quand c'est termine et verifie
5. Ajouter une ligne dans le "Journal des modifications" en bas du fichier

> **Note :** Le plan de production (`PRODUCTION_PLAN.md`) et le pipeline de donnees (`DATA_AQI_PLAN.md`) sont termines. Le focus est desormais sur la refonte frontend (`UX_UI_PLAN.md`).

## Fichiers cles du projet

| Fichier | Role |
|---------|------|
| `backend/app/api/routers/` | Routes API decoupees : auth, activity, plan, sync, data |
| `backend/app/core/settings.py` | Configuration backend (env vars, valeurs par defaut) |
| `backend/app/core/database.py` | Connexion SQLModel/SQLAlchemy |
| `backend/app/auth/jwt.py` | Gestion JWT + hashing mots de passe |
| `backend/app/auth/strava_oauth.py` | OAuth Strava + chiffrement tokens |
| `backend/app/auth/google_oauth.py` | OAuth Google Calendar |
| `backend/app/domain/entities/user.py` | Modeles User, StravaAuth, GoogleAuth |
| `backend/app/domain/entities/activity.py` | Modele Activity |
| `backend/app/domain/entities/workout_plan.py` | Modele WorkoutPlan |
| `backend/app/domain/services/strava_sync_service.py` | Sync des activites Strava |
| `backend/app/domain/services/detailed_strava_service.py` | Enrichissement (streams, laps, segments) |
| `backend/app/main.py` | Point d'entree FastAPI, CORS, middleware |
| `frontend/src/App.tsx` | Routes React |
| `frontend/src/contexts/AuthContext.tsx` | Gestion de l'auth cote frontend |
| `frontend/src/services/` | Couche d'appels API (axios) |
| `docker-compose.dev.yml` | Orchestration Docker dev |
| `.github/workflows/ci-cd.yml` | Pipeline CI/CD |
| `UX_UI_PLAN.md` | **Plan de refonte frontend (LIRE EN PREMIER — focus actuel)** |
| `PLAN_GUIDE_UXUI.md` | Guide de classification des taches UX/UI |
| `DATA_AQI_PLAN.md` | Plan d'acquisition de donnees (termine) |
| `PRODUCTION_PLAN.md` | Plan de mise en production (Phases 1-4 terminees) |

## Problemes connus et pieges

- **bcrypt/passlib** : bcrypt 5.x casse passlib 1.7.4 → garder `bcrypt>=4.0.0,<4.1.0`
- **Strava IDs overflow** : utiliser `BigInteger` pour `strava_id` (valeurs > 2.1B)
- **streams_data "null"** : le sync initial stocke `"null"` en string au lieu de SQL NULL
- **Double /api/v1** : le frontend ajoute `/api/v1`, donc `VITE_API_URL` ne doit PAS l'inclure
- **Ports par defaut** : backend=8000, frontend=3000, postgres=5432, redis=6379
- **Quotas Strava** : 100 req/15min, 1000 req/jour. Chaque enrichissement = 3 appels API

## Tache prioritaire : Audit des metriques (Agent Team)

**A executer en priorite au demarrage de la session si l'utilisateur le demande.**

Creer une **agent team de 3 teammates** pour auditer les ~130+ metriques du projet.
Le catalogue de reference est : `/Users/andrebertea/Projects/athletIQ/metrics_audit.md`

### Teammate 1 : "db-auditor" — Audit Base de Donnees & Migrations
- Lire `metrics_audit.md` (section 8 : Schema de stockage) pour les 7 tables attendues :
  `activities`, `segment`, `segmentfeatures`, `activityweather`, `garmindaily`, `trainingload`, `garminauth`
- Verifier dans `backend/app/domain/entities/` que chaque modele SQLModel existe et que
  TOUTES les colonnes listees dans metrics_audit.md sont definies (types, contraintes)
- Verifier dans `backend/alembic/versions/` que toutes les migrations sont presentes et coherentes
- Lister les metriques du catalogue qui n'ont PAS de colonne correspondante en BDD
- Rapport : metriques presentes / manquantes / differences de type

### Teammate 2 : "api-auditor" — Audit Routes API & Services
- Lire `metrics_audit.md` pour la liste complete des metriques
- Scanner `backend/app/api/routers/` pour identifier toutes les routes qui exposent des metriques
- Scanner `backend/app/domain/services/` pour voir comment les metriques sont calculees et requetees
- Pour chaque metrique : quelle route l'expose, quel service la calcule, requete individuelle ou bulk
- Rapport : metriques exposees via API / non exposees

### Teammate 3 : "frontend-auditor" — Audit Interface Utilisateur
- Lire `metrics_audit.md` pour la liste complete des metriques
- Scanner `frontend/src/` (composants React, services, types) pour trouver chaque endroit
  ou une metrique est affichee, utilisee ou referencee
- Pour chaque metrique trouvee : fichier, composant, contexte d'affichage (dashboard, detail activite, graphique, tableau)
- Produire la liste des metriques du catalogue qui n'apparaissent NULLE PART dans le frontend
- Identifier les metriques fetchees par l'API mais jamais rendues visuellement

### Instructions pour le lead
- Attendre que les 3 teammates terminent avant de synthetiser
- Produire un rapport final consolide :
  1. Tableau croise : metrique x presence BDD x presence API x presence Frontend
  2. Liste des "trous" : metriques en BDD mais pas dans le frontend
  3. Liste des incoherences : metriques dans le frontend qui n'existent pas en BDD
  4. Recommandations : metriques a forte valeur (3 etoiles dans metrics_audit.md) non exploitees dans l'UI

## Regles de travail

- **Langue** : repondre en francais
- **Commits** : ne commiter que quand l'utilisateur le demande explicitement
- **Securite** : ne jamais exposer de secrets dans le code. Utiliser les variables d'environnement
- **Scope** : ne pas sur-ingenierer. Faire le minimum necessaire pour la tache en cours
- **Tests** : verifier que les tests passent apres chaque modification (`pytest` backend, `npm test` frontend)
- **Mise a jour du plan** : toujours mettre a jour UX_UI_PLAN.md apres avoir termine une tache
