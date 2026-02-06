# athletIQ — Plan de mise en production

> Ce document est le plan directeur pour passer athletIQ en production.
> Il est lu par Claude a chaque iteration pour comprendre l'etat d'avancement.
> Chaque tache a un statut : `[ ]` (a faire), `[~]` (en cours), `[x]` (termine).

---

## Legende des statuts

- `[ ]` A faire
- `[~]` En cours
- `[x]` Termine
- `[!]` Bloque (voir notes)

---

## Phase 1 — Securite (CRITIQUE — avant tout deploiement)

> Aucun deploiement public ne doit avoir lieu tant que cette phase n'est pas terminee.

### 1.1 Rotation des secrets

- [x] **1.1.1** Regenerer le `STRAVA_CLIENT_SECRET` depuis le dashboard Strava (https://www.strava.com/settings/api)
- [x] **1.1.2** Regenerer le `STRAVA_REFRESH_TOKEN` via un nouveau flow OAuth
- [x] **1.1.3** Generer une nouvelle `ENCRYPTION_KEY` Fernet (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
- [x] **1.1.4** Generer un nouveau `JWT_SECRET_KEY` fort (`openssl rand -hex 64`)
- [x] **1.1.5** Verifier que `.env` est dans `.gitignore` et n'a jamais ete commite (sinon : `git filter-branch` ou `bfg`)
- [x] **1.1.6** Mettre a jour `backend/.env.example` avec des placeholders clairs (jamais de vraies valeurs)

### 1.2 Gestion des secrets en production

- [ ] **1.2.1** Configurer les variables d'environnement sur Render.com (backend) via le dashboard
- [ ] **1.2.2** Configurer les variables d'environnement sur Vercel (frontend) : `VITE_API_URL`
- [x] **1.2.3** Supprimer tous les secrets hardcodes de `docker-compose.dev.yml` — utiliser `${VAR:-default}` avec un `.env` local
- [x] **1.2.4** Supprimer les valeurs par defaut dangereuses dans `backend/app/core/settings.py` (JWT_SECRET_KEY, STRAVA_CLIENT_ID)

### 1.3 Verrouillage CORS

- [x] **1.3.1** Dans `settings.py` : remplacer `ALLOWED_ORIGINS = ["*"]` par une liste explicite basee sur `ENVIRONMENT`
- [x] **1.3.2** En dev : `["http://localhost:3000", "http://localhost:4000"]`
- [x] **1.3.3** En prod : `["https://athletiq.vercel.app"]` (ou le domaine final)
- [x] **1.3.4** Supprimer `"*"` de `allow_origins` dans `main.py`

### 1.4 Desactivation du mode DEBUG

- [x] **1.4.1** Changer le defaut de `DEBUG` a `False` dans `settings.py`
- [x] **1.4.2** S'assurer que `ENVIRONMENT` est lu depuis les env vars et conditionne le comportement (logging, error detail)
- [x] **1.4.3** En mode non-DEBUG : ne pas exposer les stack traces dans les reponses HTTP 500

### 1.5 Redirect URIs configurables

- [x] **1.5.1** Ajouter `FRONTEND_URL` et `BACKEND_URL` dans `settings.py` (defaut : `http://localhost:3000` et `http://localhost:8000`)
- [x] **1.5.2** Remplacer tous les `http://localhost:3000` et `http://localhost:4000` hardcodes dans `routes.py` par `settings.FRONTEND_URL`
- [x] **1.5.3** Rendre `STRAVA_REDIRECT_URI` dynamique base sur `BACKEND_URL` + `/api/v1/auth/strava/callback`
- [x] **1.5.4** Faire de meme pour Google OAuth redirect URI
- [ ] **1.5.5** Mettre a jour les URIs de callback dans le dashboard Strava et Google Cloud Console

---

## Phase 2 — Multi-utilisateur viable

> Objectif : permettre a plusieurs utilisateurs d'utiliser l'app simultanement sans se bloquer mutuellement.

### 2.1 Quota Strava distribue (Redis)

- [x] **2.1.1** Verifier que Redis est bien connecte et fonctionnel dans le backend (actuellement configure mais sous-utilise)
- [x] **2.1.2** Creer un `RedisQuotaManager` qui stocke les compteurs dans Redis (`strava:quota:daily`, `strava:quota:15min`)
- [x] **2.1.3** Implementer un TTL automatique sur le compteur 15min (expire apres 15 minutes)
- [x] **2.1.4** Implementer un reset quotidien du compteur daily (TTL a minuit UTC)
- [x] **2.1.5** Remplacer le `StravaQuotaManager` in-memory par le `RedisQuotaManager`
- [x] **2.1.6** Ajouter un endpoint `/strava/quota` qui retourne le statut en temps reel depuis Redis

### 2.2 File d'attente d'enrichissement (fair scheduling)

- [x] **2.2.1** Creer une table `enrichment_queue` (activity_id, user_id, priority, status, created_at)
- [x] **2.2.2** Implementer un scheduler round-robin : chaque utilisateur a droit a N enrichissements par cycle
- [x] **2.2.3** Creer un worker background (asyncio task ou Celery) qui depile la queue en respectant les quotas
- [x] **2.2.4** Ajouter un endpoint pour que l'utilisateur puisse voir sa position dans la queue
- [x] **2.2.5** Gerer les retries en cas d'echec (max 3 tentatives, backoff exponentiel)

### 2.3 Webhooks Strava

- [x] **2.3.1** Creer un endpoint `POST /api/v1/webhooks/strava` pour recevoir les evenements
- [x] **2.3.2** Creer un endpoint `GET /api/v1/webhooks/strava` pour la validation du challenge Strava
- [x] **2.3.3** Implementer la verification de signature des webhooks
- [x] **2.3.4** Gerer les types d'evenements : `activity.create`, `activity.update`, `activity.delete`
- [x] **2.3.5** Sur `activity.create` : ajouter automatiquement l'activite dans la queue d'enrichissement
- [ ] **2.3.6** Enregistrer la subscription webhook via l'API Strava (one-time setup)
- [ ] **2.3.7** Documenter la procedure d'enregistrement du webhook dans le README

---

## Phase 3 — Robustesse et qualite de service

> Objectif : rendre l'application fiable et observable en production.

### 3.1 Rate limiting

- [ ] **3.1.1** Installer `slowapi` (wrapper de `limits` pour FastAPI)
- [ ] **3.1.2** Configurer un rate limit sur `/auth/login` : 5 tentatives / minute par IP
- [ ] **3.1.3** Configurer un rate limit sur `/auth/signup` : 3 inscriptions / heure par IP
- [ ] **3.1.4** Configurer un rate limit global : 100 requetes / minute par utilisateur authentifie
- [ ] **3.1.5** Retourner des headers `Retry-After` et status 429 propres

### 3.2 HTTPS en production

- [ ] **3.2.1** Ajouter un middleware de redirection HTTP → HTTPS en production (ou verifier que Render le fait)
- [ ] **3.2.2** S'assurer que tous les cookies ont le flag `Secure`
- [ ] **3.2.3** Ajouter les headers de securite : `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options`

### 3.3 Monitoring et error tracking

- [ ] **3.3.1** Installer et configurer Sentry (`sentry-sdk[fastapi]`) sur le backend
- [ ] **3.3.2** Installer et configurer Sentry (`@sentry/react`) sur le frontend
- [ ] **3.3.3** Configurer les alertes Sentry (email sur nouvelle erreur)
- [ ] **3.3.4** Ajouter du structured logging (JSON) pour les logs backend en production
- [ ] **3.3.5** Configurer la rotation des logs (ne plus ecrire dans `app.log` sans limite)

### 3.4 Error boundaries (frontend)

- [ ] **3.4.1** Creer un composant `ErrorBoundary` global qui catch les erreurs React
- [ ] **3.4.2** Ajouter des error boundaries par section (Dashboard, Activities, Plans)
- [ ] **3.4.3** Afficher un message utilisateur friendly avec option de reload
- [ ] **3.4.4** Remonter l'erreur a Sentry automatiquement

### 3.5 Migrations automatiques

- [ ] **3.5.1** Ajouter `alembic upgrade head` dans le script de demarrage du backend (ou dans le `Dockerfile`)
- [ ] **3.5.2** Ajouter une etape de migration dans le pipeline CI/CD avant le deploy
- [ ] **3.5.3** Tester la migration sur une base vierge dans la CI

### 3.6 Workers et performance

- [ ] **3.6.1** Configurer gunicorn avec uvicorn workers pour la production (`gunicorn -w 4 -k uvicorn.workers.UvicornWorker`)
- [ ] **3.6.2** Ajouter du code splitting / lazy loading sur les grosses pages React (Dashboard, RacePredictor)
- [ ] **3.6.3** Implementer la pagination reelle des activites (remplacer le `limit: 1000` hardcode)

---

## Phase 4 — Qualite du code et tests

> Objectif : assurer la maintenabilite et la non-regression.

### 4.1 Refactoring backend

- [ ] **4.1.1** Decouper `routes.py` (1350 lignes) en routers separes : `auth_router`, `activity_router`, `plan_router`, `sync_router`, `data_router`
- [ ] **4.1.2** Creer un fichier `api/routers/__init__.py` qui inclut tous les routers
- [ ] **4.1.3** Deplacer la logique metier restante dans les services (routes = validation + delegation uniquement)

### 4.2 Tests

- [ ] **4.2.1** Ajouter des tests d'integration pour le flow OAuth Strava (mock des appels API)
- [ ] **4.2.2** Ajouter des tests pour le quota manager
- [ ] **4.2.3** Ajouter des tests pour les webhooks
- [ ] **4.2.4** Creer les premiers tests frontend (au minimum : AuthContext, services, composants critiques)
- [ ] **4.2.5** Configurer le coverage frontend dans la CI

### 4.3 Refactoring frontend

- [ ] **4.3.1** Decouper `RacePredictor.tsx` (1675 lignes) en sous-composants
- [ ] **4.3.2** Migrer le stockage JWT de localStorage vers des cookies httpOnly (necessite changement backend aussi)
- [ ] **4.3.3** Ajouter un systeme de notifications toast pour le feedback utilisateur

---

## Phase 5 — Infrastructure de production (optionnel / evolutif)

> Ces elements ne sont pas bloquants pour un premier deploiement mais importants pour scaler.

### 5.1 Docker production

- [ ] **5.1.1** Creer un `docker-compose.prod.yml` avec : PostgreSQL, Redis, Backend (multi-worker), Frontend (Nginx)
- [ ] **5.1.2** Creer un `Dockerfile.prod` pour le frontend (build React + Nginx)
- [ ] **5.1.3** Configurer les health checks pour tous les services

### 5.2 Base de donnees

- [ ] **5.2.1** Configurer le connection pooling PostgreSQL (SQLAlchemy pool_size, max_overflow)
- [ ] **5.2.2** Mettre en place des backups automatiques (pg_dump ou service manage)
- [ ] **5.2.3** Ajouter des index sur les colonnes frequemment filtrees (user_id, start_date, activity_type)

### 5.3 Domaine et DNS

- [ ] **5.3.1** Acheter/configurer un nom de domaine
- [ ] **5.3.2** Configurer le DNS pour pointer vers Render (API) et Vercel (frontend)
- [ ] **5.3.3** Configurer le certificat SSL (Let's Encrypt ou managed)

---

## Journal des modifications

| Date | Phase | Tache | Statut | Notes |
|------|-------|-------|--------|-------|
| 2026-02-06 | Phase 1 | 1.1.3 | [x] | Nouvelle ENCRYPTION_KEY Fernet generee et mise a jour dans backend/.env |
| 2026-02-06 | Phase 1 | 1.1.4 | [x] | Nouveau JWT_SECRET_KEY fort genere (openssl rand -hex 64, 128 chars) et mis a jour dans backend/.env. Creation et verification de tokens testees avec succes. |
| 2026-02-06 | Phase 1 | 1.1.1 | [x] | Nouveau STRAVA_CLIENT_SECRET genere depuis le dashboard Strava et mis a jour dans backend/.env |
| 2026-02-06 | Phase 1 | 1.1.2 | [x] | Re-connexion OAuth Strava reussie avec le nouveau secret. Correction docker-compose.dev.yml : ajout env_file ./backend/.env, suppression secrets hardcodes du bloc environment |
| 2026-02-06 | Phase 1 | 1.1.5 | [x] | Audit .gitignore + fichiers sensibles. Pas de repo git existant (pas d'historique a nettoyer). .env/.env.local/backend/.env/frontend/.env deja ignores. Ajout au .gitignore de : backend/reset_*.py (contenait email+mdp en clair), configure_strava_secret.sh, fix_strava_auth.sh, check_services.sh (contenaient STRAVA_CLIENT_ID hardcode et affichaient le contenu du .env). Fichier archive/legacy-config/strava_config.json (vrais tokens Strava) deja ignore par archive/**/*. |
| 2026-02-06 | Phase 1 | 1.2.3 | [x] | Suppression des secrets hardcodes de docker-compose.dev.yml. POSTGRES_DB/USER/PASSWORD et DATABASE_URL utilisent desormais ${VAR:-default}. VITE_API_URL parametrise. Fichier .env racine cree (ignore par git) pour les valeurs de dev Docker. Healthcheck postgres dynamise. Syntaxe validee via docker compose config. |
| 2026-02-06 | Phase 1 | 1.2.4 | [x] | Suppression des valeurs par defaut dangereuses dans settings.py : DATABASE_URL (sqlite fallback), JWT_SECRET_KEY ("your-secret-key-change-in-production"), STRAVA_CLIENT_ID (158144 hardcode), ENCRYPTION_KEY (chaine vide). Ces 4 champs sont desormais obligatoires — l'app refuse de demarrer si non definis dans .env ou env vars. Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 1 | 1.3.1-1.3.4 | [x] | Verrouillage CORS complet. settings.py : ALLOWED_ORIGINS vide par defaut, model_validator definit les origines selon ENVIRONMENT (dev: localhost:3000/4000, prod: athletiq.vercel.app). Override possible via env var. main.py : allow_origins utilise settings.ALLOWED_ORIGINS au lieu de "*". Suppression du handler OPTIONS custom qui renvoyait "*" en dur. |
| 2026-02-06 | Phase 1 | 1.4.1 | [x] | Defaut de DEBUG change de True a False dans settings.py (ligne 65). En production, DEBUG sera desactive par defaut sauf si explicitement active via variable d'environnement. Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 1 | 1.4.2 | [x] | ENVIRONMENT conditionne desormais le comportement : settings.py ajoute LOG_LEVEL (WARNING en prod, INFO en dev) et force DEBUG=False en prod. main.py conditionne le niveau de logging, la visibilite de /docs et /redoc (masques en prod), le fichier app.log (desactive en prod), et le log_level uvicorn selon ENVIRONMENT. Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 1 | 1.4.3 | [x] | global_exception_handler dans main.py : en mode non-DEBUG, le champ `type` (nom de classe de l'exception) n'est plus expose dans la reponse HTTP 500. Seuls `detail` et `message` generiques sont renvoyes. En mode DEBUG, `type` et le vrai message d'erreur restent visibles pour faciliter le debogage. Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 1 | 1.5.1 | [x] | Ajout de FRONTEND_URL (defaut http://localhost:3000) et BACKEND_URL (defaut http://localhost:8000) dans settings.py. Ces champs seront utilises par les taches 1.5.2-1.5.4 pour remplacer les URLs hardcodees. Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 1 | 1.1.6 | [x] | Mise a jour de backend/.env.example et frontend/.env.example. Backend : suppression de l'ancien DATABASE_URL sqlite, placeholders clairs avec chevrons (<generer-...>), instructions de generation pour JWT_SECRET_KEY et ENCRYPTION_KEY, ajout des variables manquantes (FRONTEND_URL, BACKEND_URL, REDIS_URL, LOG_LEVEL, ALLOWED_ORIGINS). Frontend : ajout d'un avertissement que VITE_API_URL ne doit pas inclure /api/v1. Aucune vraie valeur dans les fichiers. |
| 2026-02-06 | Phase 1 | 1.5.2 | [x] | Remplacement de 8 URLs localhost hardcodees (http://localhost:3000 et http://localhost:4000) dans routes.py par settings.FRONTEND_URL via get_settings(). Import de get_settings ajoute. Concerne les callbacks OAuth Google (1 occurrence) et Strava (7 occurrences : erreur OAuth, code manquant, state manquant, state invalide, user non trouve, succes, exception). Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 1 | 1.5.3 | [x] | STRAVA_REDIRECT_URI rendu dynamique : default vide dans settings.py, model_validator le construit depuis BACKEND_URL + /api/v1/auth/strava/callback si non defini. Override toujours possible via env var. Suppression de la valeur hardcodee dans backend/.env et .env.example mis a jour. strava_oauth.py inchange (lit deja settings.STRAVA_REDIRECT_URI). Tests manuels : 4 cas valides (defaut, custom BACKEND_URL, trailing slash, override explicite). |
| 2026-02-06 | Phase 1 | 1.5.4 | [x] | GOOGLE_REDIRECT_URI rendu dynamique : default vide dans settings.py, model_validator le construit depuis BACKEND_URL + /api/v1/auth/google/callback si non defini. Override toujours possible via env var. Suppression de la valeur hardcodee dans backend/.env et .env.example mis a jour. Tests manuels : 4 cas valides (defaut, custom BACKEND_URL, trailing slash, override explicite). Tests pytest : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 2 | 2.1.1 | [x] | Redis verifie et integre au backend. Ajout de `redis>=5.0.0` dans requirements.txt, REDIS_URL dans settings.py (defaut redis://localhost:6379), creation de `app/core/redis.py` (get_redis_client singleton + check_redis_health). Verification Redis au demarrage dans lifespan (log warning si indisponible). Endpoint /health enrichi avec statut Redis (connected/disconnected, status degraded si Redis down). Tests : imports OK, health check gere correctement Redis absent. Erreur test pre-existante (starlette/httpx incompatibilite) non liee. |
| 2026-02-06 | Phase 2 | 2.1.2 | [x] | Creation de `RedisQuotaManager` dans `backend/app/domain/services/redis_quota_manager.py`. Meme interface que `StravaQuotaManager` (check_and_wait_if_needed, increment_usage, get_status, daily_count/per_15min_count). Compteurs Redis avec TTL automatiques : `strava:quota:15min` (TTL 900s), `strava:quota:daily` (TTL = secondes jusqu'a minuit UTC). INCR atomique + EXPIRE uniquement a la creation de la cle. Resilient si Redis down (retourne 0, log warning). |
| 2026-02-06 | Phase 2 | 2.1.3 | [x] | TTL automatique 15min rendu robuste dans RedisQuotaManager. Le TTL 900s etait deja pose a la creation de la cle (new_val==1), mais pas protege contre les cles orphelines (crash entre INCR et EXPIRE). Ajout d'un filet de securite dans `_safe_incr` et `_safe_get` : si une cle existe sans TTL (ttl == -1), le TTL est reapplique automatiquement (900s pour 15min, secondes-jusqu-a-minuit pour daily). Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 2 | 2.1.4 | [x] | Reset quotidien du compteur daily deja fonctionnel via TTL Redis (pose a la creation de la cle = secondes jusqu'a minuit UTC, expiration automatique par Redis). Ajout d'un garde-fou `max(..., 1)` dans `_seconds_until_midnight_utc()` pour eviter un TTL de 0 si l'appel tombe pile a minuit (suppression immediate de la cle). Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 2 | 2.1.5 | [x] | Remplacement de `StravaQuotaManager` (in-memory) par `RedisQuotaManager` dans `DetailedStravaService.__init__()` (detailed_strava_service.py:88). Import ajoute, ancien constructeur remplace. La classe `StravaQuotaManager` reste dans le fichier (dead code) pour reference mais n'est plus instanciee. L'instance globale `detailed_strava_service.quota_manager` est desormais un `RedisQuotaManager`. Tous les consommateurs (routes.py, auto_enrichment_service.py) fonctionnent sans changement grace a l'interface identique. Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 2 | 2.1.6 | [x] | Endpoint `GET /strava/quota` deja present dans routes.py (lignes 1315-1323). Protege par JWT, appelle `RedisQuotaManager.get_status()` qui retourne en temps reel depuis Redis : daily_used, daily_limit, per_15min_used, per_15min_limit, next_15min_reset, daily_reset. Aucune modification necessaire — l'endpoint avait ete cree lors des taches precedentes (2.1.2/2.1.5). Bloc Redis Quota complet. |
| 2026-02-06 | Phase 2 | 2.2.1 | [x] | Creation de la table `enrichment_queue` : modele SQLModel dans `backend/app/domain/entities/enrichment_queue.py` avec colonnes id (UUID PK), activity_id (FK activity.id), user_id (FK user.id), priority (int, default 0), status (enum PENDING/IN_PROGRESS/COMPLETED/FAILED), attempts (int, default 0), last_error (nullable), created_at, updated_at. Index sur activity_id, user_id, priority, status. Migration Alembic `f8a1b2c3d4e5`. Modele enregistre dans entities/__init__.py et alembic/env.py. Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 2 | 2.2.2 | [x] | Creation de `RoundRobinScheduler` dans `backend/app/domain/services/round_robin_scheduler.py`. Le scheduler utilise la table `enrichment_queue` en base (persistante) et alterne entre les utilisateurs : chaque user a droit a 2 enrichissements par cycle (configurable via `items_per_user`). Curseur circulaire `_last_user_index` pour garantir la fairness entre cycles. Tri par priorite puis anciennete au sein de chaque utilisateur. `auto_enrichment_service.py` refactorise : queue in-memory remplacee par `RoundRobinScheduler`, methodes `add_to_queue`/`mark_completed`/`mark_failed` persistent en base. Interface publique inchangee (add_user_activities_to_queue, prioritize_activity, get_queue_status, is_running). Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 2 | 2.3.1 | [x] | Endpoint `POST /api/v1/webhooks/strava` cree dans routes.py. Recoit les evenements webhook Strava (payload JSON), log object_type/aspect_type/object_id/owner_id, retourne HTTP 200 systematiquement (requis par Strava pour accuser reception sous 2s). Pas d'auth JWT (endpoint public, verification de signature prevue en 2.3.3). Ajout de `STRAVA_WEBHOOK_VERIFY_TOKEN` dans settings.py (utilise pour la subscription webhook). Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 2 | 2.3.2 | [x] | Endpoint `GET /api/v1/webhooks/strava` cree dans routes.py. Recoit les query params `hub.mode`, `hub.challenge`, `hub.verify_token` envoyes par Strava lors de la creation d'une subscription webhook. Verifie que `hub.verify_token` correspond a `STRAVA_WEBHOOK_VERIFY_TOKEN` (settings.py), retourne HTTP 403 si invalide, sinon retourne `{"hub.challenge": "<valeur>"}` avec HTTP 200. Pas d'auth JWT (endpoint public). Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 2 | 2.3.3 | [x] | Verification de signature des webhooks Strava. Strava ne fournit pas de header HMAC/X-Hub-Signature — verification implementee via : (1) validation de la structure du payload (5 champs requis : object_type, object_id, aspect_type, owner_id, subscription_id), (2) verification du subscription_id contre STRAVA_WEBHOOK_SUBSCRIPTION_ID (configurable dans settings.py, si vide la verification est ignoree). Ajout de STRAVA_WEBHOOK_SUBSCRIPTION_ID dans settings.py et .env.example. Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 2 | 2.3.4 | [x] | Gestion des types d'evenements webhook Strava. Creation de `strava_webhook_handler.py` avec handlers pour activity.create (fetch depuis API Strava + sauvegarde DB), activity.update (re-sync des champs depuis Strava), activity.delete (suppression en DB). Ajout de `fetch_single_activity` dans `strava_sync_service.py` pour recuperer une activite par ID. Endpoint POST webhook dispatch les evenements via `run_in_executor` (fire-and-forget) pour repondre HTTP 200 sous 2s. Les object_type != "activity" sont ignores. Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 2 | 2.2.3 | [x] | Worker background asyncio cree dans `auto_enrichment_service.py`. Boucle `_run_loop` tourne comme `asyncio.Task` dans le lifespan FastAPI. Verification non-bloquante des quotas (daily + 15min) via `RedisQuotaManager` avant chaque batch et chaque enrichissement. `asyncio.Event` (`_wake_event`) reveille le worker immediatement quand des items sont ajoutes (`add_user_activities_to_queue`, `prioritize_activity`). En idle, le worker attend 5 min ou un signal. Methodes `start_worker`/`stop_worker` pour lifecycle propre. `main.py` demarre le worker au startup et l'arrete au shutdown. Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 2 | 2.2.4 | [x] | Endpoint `GET /enrichment/queue-position` cree dans routes.py. Protege par JWT. Retourne pour l'utilisateur courant : user_pending, user_in_progress, user_completed, user_failed, ahead_in_queue (items d'autres utilisateurs avant lui), estimated_position, plus le queue_status global. Methode `get_user_queue_position` ajoutee dans RoundRobinScheduler et exposee via AutoEnrichmentService. Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| 2026-02-06 | Phase 2 | 2.2.5 | [x] | Gestion des retries avec backoff exponentiel. Ajout de `max_attempts` (default 3) et `next_retry_at` dans le modele EnrichmentQueue. `mark_failed` remet l'item en PENDING avec backoff (30s, 60s, 120s) si tentatives < max_attempts, sinon FAILED definitif. `get_next_batch` et `get_pending_count` filtrent les items dont le backoff n'est pas ecoule (`next_retry_at IS NULL OR <= now`). Migration Alembic `a1b2c3d4e5f6`. Tests : aucune regression (echecs pre-existants inchanges). |
| 2026-02-06 | Phase 2 | 2.3.5 | [x] | Ajout automatique dans la queue d'enrichissement sur activity.create. Dans `strava_webhook_handler.py`, apres le commit de l'activite en DB, appel a `auto_enrichment_service.scheduler.add_to_queue()` + `notify_new_items()` pour reveiller le worker. Entoure d'un try/except pour ne pas bloquer le webhook en cas d'erreur queue. Tests : aucune regression (7 passed, echecs pre-existants inchanges). |
| _A remplir au fur et a mesure_ | | | | |
