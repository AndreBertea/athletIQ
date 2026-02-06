# PLAN_GUIDE.md — Classification des taches

> Ce fichier classe chaque tache du `PRODUCTION_PLAN.md` selon deux criteres :
> 1. **Autonomie** : la tache peut-elle etre realisee entierement par un agent, ou necessite-t-elle une intervention humaine ?
> 2. **Cascades** : quelles taches bloquent quelles autres ?

---

## Legende

| Icone | Signification |
|-------|---------------|
| `AGENT` | Realisable a 100% par un agent (modification de code, generation de fichiers, refactoring) |
| `HUMAIN` | Necessite une action humaine (dashboard externe, achat, credentials, config cloud) |
| `→` | "bloque" (la tache a gauche doit etre terminee avant celle a droite) |

---

## 1. Classification par autonomie

### Taches AGENT (realisables sans intervention humaine)

Ces taches sont du code pur, du refactoring, de la configuration dans le codebase, ou de la generation locale.

#### Phase 1 — Securite

| ID | Tache | Notes |
|----|-------|-------|
| 1.1.3 | Generer une nouvelle `ENCRYPTION_KEY` Fernet | Commande locale |
| 1.1.4 | Generer un nouveau `JWT_SECRET_KEY` | Commande locale |
| 1.1.5 | Verifier `.gitignore` + historique git | Audit git local |
| 1.1.6 | Mettre a jour `.env.example` | Edition fichier |
| 1.2.3 | Supprimer secrets hardcodes de `docker-compose.dev.yml` | Edition fichier |
| 1.2.4 | Supprimer valeurs par defaut dangereuses dans `settings.py` | Edition fichier |
| 1.3.1 | Remplacer `ALLOWED_ORIGINS = ["*"]` par liste explicite | Edition `settings.py` |
| 1.3.2 | Configurer les origines dev | Inclus dans 1.3.1 |
| 1.3.3 | Configurer les origines prod | Inclus dans 1.3.1 |
| 1.3.4 | Supprimer `"*"` de `allow_origins` dans `main.py` | Edition `main.py` |
| 1.4.1 | Changer defaut DEBUG a False | Edition `settings.py` |
| 1.4.2 | ENVIRONMENT conditionne le comportement | Edition `settings.py` + `main.py` |
| 1.4.3 | Ne pas exposer stack traces en non-DEBUG | Edition `main.py` |
| 1.5.1 | Ajouter `FRONTEND_URL` et `BACKEND_URL` dans `settings.py` | Edition `settings.py` |
| 1.5.2 | Remplacer URLs hardcodees dans `routes.py` | Edition `routes.py` |
| 1.5.3 | Rendre `STRAVA_REDIRECT_URI` dynamique | Edition `strava_oauth.py` + `settings.py` |
| 1.5.4 | Rendre Google OAuth redirect URI dynamique | Edition `google_oauth.py` |

#### Phase 2 — Multi-utilisateur

| ID | Tache | Notes |
|----|-------|-------|
| 2.1.1 | Verifier connexion Redis | Code review + test |
| 2.1.2 | Creer `RedisQuotaManager` | Nouveau service |
| 2.1.3 | Implementer TTL 15min | Inclus dans 2.1.2 |
| 2.1.4 | Implementer reset daily | Inclus dans 2.1.2 |
| 2.1.5 | Remplacer `StravaQuotaManager` par Redis | Refactoring service |
| 2.1.6 | Endpoint `/strava/quota` temps reel | Nouveau endpoint |
| 2.2.1 | Creer table `enrichment_queue` | Modele + migration Alembic |
| 2.2.2 | Scheduler round-robin | Nouveau service |
| 2.2.3 | Worker background | Nouveau service (asyncio/Celery) |
| 2.2.4 | Endpoint position dans la queue | Nouveau endpoint |
| 2.2.5 | Gestion des retries | Extension du worker |
| 2.3.1 | Endpoint POST webhooks Strava | Nouveau endpoint |
| 2.3.2 | Endpoint GET webhooks (challenge) | Nouveau endpoint |
| 2.3.3 | Verification signature webhooks | Logique dans endpoint |
| 2.3.4 | Gestion types d'evenements | Logique dans endpoint |
| 2.3.5 | Auto-ajout dans queue sur activity.create | Liaison webhook → queue |
| 2.3.7 | Documenter procedure webhook | Edition README |

#### Phase 3 — Robustesse

| ID | Tache | Notes |
|----|-------|-------|
| 3.1.1 | Installer `slowapi` | pip install + config |
| 3.1.2 | Rate limit `/auth/login` | Config slowapi |
| 3.1.3 | Rate limit `/auth/signup` | Config slowapi |
| 3.1.4 | Rate limit global | Config slowapi |
| 3.1.5 | Headers `Retry-After` + 429 | Config slowapi |
| 3.2.1 | Middleware redirect HTTP → HTTPS | Nouveau middleware |
| 3.2.2 | Cookies flag `Secure` | Config backend |
| 3.2.3 | Headers de securite (HSTS, X-Frame, etc.) | Nouveau middleware |
| 3.3.1 | Installer/configurer Sentry backend | pip install + init dans `main.py` |
| 3.3.2 | Installer/configurer Sentry frontend | npm install + init dans `main.tsx` |
| 3.3.4 | Structured logging JSON | Refactoring logging |
| 3.3.5 | Rotation des logs | Config RotatingFileHandler |
| 3.4.1 | ErrorBoundary global React | Nouveau composant |
| 3.4.2 | Error boundaries par section | Ajout dans `App.tsx` |
| 3.4.3 | Message utilisateur friendly + reload | UI dans ErrorBoundary |
| 3.4.4 | Remonter erreur a Sentry | Integration Sentry dans ErrorBoundary |
| 3.5.1 | `alembic upgrade head` dans Dockerfile | Edition Dockerfile |
| 3.5.2 | Etape migration dans CI/CD | Edition `ci-cd.yml` |
| 3.5.3 | Test migration base vierge | Edition CI pipeline |
| 3.6.1 | Configurer gunicorn multi-workers | Edition Dockerfile + config |
| 3.6.2 | Code splitting / lazy loading React | Refactoring `App.tsx` |
| 3.6.3 | Pagination reelle des activites | Backend + frontend |

#### Phase 4 — Qualite du code

| ID | Tache | Notes |
|----|-------|-------|
| 4.1.1 | Decouper `routes.py` en routers | Refactoring majeur |
| 4.1.2 | Creer `api/routers/__init__.py` | Nouveau fichier |
| 4.1.3 | Deplacer logique metier dans services | Refactoring |
| 4.2.1 | Tests integration OAuth (mock) | Nouveaux tests |
| 4.2.2 | Tests quota manager | Nouveaux tests |
| 4.2.3 | Tests webhooks | Nouveaux tests |
| 4.2.4 | Tests frontend | Nouveaux tests |
| 4.2.5 | Coverage frontend dans CI | Edition `ci-cd.yml` |
| 4.3.1 | Decouper `RacePredictor.tsx` | Refactoring composant |
| 4.3.2 | Migrer JWT vers cookies httpOnly | Backend + frontend |
| 4.3.3 | Systeme de notifications toast | Nouveau composant |

#### Phase 5 — Infrastructure

| ID | Tache | Notes |
|----|-------|-------|
| 5.1.1 | Creer `docker-compose.prod.yml` | Nouveau fichier |
| 5.1.2 | Creer `Dockerfile.prod` frontend | Nouveau fichier |
| 5.1.3 | Health checks tous services | Edition docker-compose |
| 5.2.1 | Connection pooling PostgreSQL | Edition `database.py` |
| 5.2.3 | Index sur colonnes filtrees | Migration Alembic |

---

### Taches HUMAIN (intervention humaine requise)

Ces taches necessitent un acces a un dashboard externe, des credentials manuels, un achat, ou une action physique.

| ID | Tache | Raison |
|----|-------|--------|
| 1.1.1 | Regenerer `STRAVA_CLIENT_SECRET` | Acces au dashboard Strava |
| 1.1.2 | Regenerer `STRAVA_REFRESH_TOKEN` | Flow OAuth dans le navigateur |
| 1.2.1 | Configurer env vars sur Render.com | Acces au dashboard Render |
| 1.2.2 | Configurer env vars sur Vercel | Acces au dashboard Vercel |
| 1.5.5 | Mettre a jour URIs dans dashboards Strava + Google | Acces aux dashboards externes |
| 2.3.6 | Enregistrer subscription webhook Strava | Appel API Strava avec credentials + app deployee |
| 3.3.3 | Configurer alertes Sentry | Acces au dashboard Sentry |
| 5.2.2 | Backups automatiques DB | Config service manage ou cron serveur |
| 5.3.1 | Acheter/configurer nom de domaine | Achat + registrar |
| 5.3.2 | Configurer DNS | Acces au registrar DNS |
| 5.3.3 | Configurer certificat SSL | Acces au registrar / provider |

---

## 2. Graphe de dependances (cascades)

### Phase 1 — Securite

```
BLOC A — Rotation secrets (partiellement HUMAIN)
  1.1.1 (HUMAIN) ─┐
  1.1.2 (HUMAIN) ─┤
  1.1.3 (AGENT) ──┼→ 1.1.6 (AGENT) → 1.2.1 (HUMAIN)
  1.1.4 (AGENT) ──┘                 → 1.2.2 (HUMAIN)

  1.1.5 (AGENT) ── independant, peut etre fait a tout moment

BLOC B — Nettoyage code (100% AGENT, aucun bloquant)
  1.2.3 (AGENT) ── independant
  1.2.4 (AGENT) ── independant

BLOC C — CORS (100% AGENT, en parallele)
  1.3.1 → 1.3.2 ─┐
                   ├→ tous font partie d'un meme changement
  1.3.3 ──────────┘
  1.3.4 ── independant mais lie logiquement

BLOC D — DEBUG (100% AGENT, en parallele)
  1.4.1 ── independant
  1.4.2 ── independant
  1.4.3 ── depend de 1.4.2 (le comportement conditionne doit exister)

BLOC E — Redirects (AGENT puis HUMAIN)
  1.5.1 → 1.5.2 ── sequentiel (le setting doit exister avant d'etre utilise)
  1.5.1 → 1.5.3 ── sequentiel
  1.5.1 → 1.5.4 ── sequentiel
  1.5.3 ─┬→ 1.5.5 (HUMAIN) — mettre a jour les dashboards avec les nouvelles URIs
  1.5.4 ─┘
```

### Phase 2 — Multi-utilisateur

```
BLOC F — Redis Quota (100% AGENT, sequentiel strict)
  2.1.1 → 2.1.2 → 2.1.3 → 2.1.4 → 2.1.5 → 2.1.6
  (verifier Redis → creer manager → TTL → reset → remplacer → endpoint)

BLOC G — Queue d'enrichissement (100% AGENT, sequentiel strict)
  2.2.1 → 2.2.2 → 2.2.3 → 2.2.4
                         └→ 2.2.5
  (table → scheduler → worker → endpoint + retries)

  DEPENDANCE INTER-BLOC : 2.2.3 depend de 2.1.5
  (le worker utilise le RedisQuotaManager pour respecter les quotas)

BLOC H — Webhooks (AGENT puis HUMAIN)
  2.3.1 ── independant  ─┐
  2.3.2 ── independant   │
  2.3.3 ── depend de 2.3.1 (verification sur le POST endpoint)
  2.3.4 ── depend de 2.3.1 (event handling dans le POST endpoint)
  2.3.5 ── depend de 2.3.4 ET 2.2.1 (handler + table queue)
  2.3.6 (HUMAIN) ── depend de 2.3.1 + 2.3.2 deployes
  2.3.7 ── depend de 2.3.6

  Schema :
  2.3.1 → 2.3.3 → 2.3.4 → 2.3.5
  2.3.2 ─────────────────→ 2.3.6 (HUMAIN) → 2.3.7
  2.2.1 ─────────────────→ 2.3.5
```

### Phase 3 — Robustesse

```
BLOC I — Rate limiting (100% AGENT, sequentiel)
  3.1.1 → 3.1.2 ─┐
       → 3.1.3 ──┤ (tous dependent de l'installation de slowapi)
       → 3.1.4 ──┤
       → 3.1.5 ──┘

BLOC J — HTTPS (100% AGENT, parallele)
  3.2.1 ── independant
  3.2.2 ── independant
  3.2.3 ── independant

BLOC K — Monitoring (AGENT + HUMAIN)
  3.3.1 (AGENT) → 3.3.3 (HUMAIN) (installer Sentry → configurer alertes)
  3.3.2 (AGENT) ── independant
  3.3.4 (AGENT) ── independant
  3.3.5 (AGENT) ── independant

BLOC L — Error boundaries (100% AGENT, sequentiel)
  3.4.1 → 3.4.2 → 3.4.3
  3.4.1 → 3.4.4 (depend aussi de 3.3.2 pour l'envoi a Sentry)

  DEPENDANCE INTER-BLOC : 3.4.4 depend de 3.3.2

BLOC M — Migrations auto (100% AGENT, sequentiel)
  3.5.1 → 3.5.2 → 3.5.3

BLOC N — Performance (100% AGENT, parallele)
  3.6.1 ── independant
  3.6.2 ── independant
  3.6.3 ── independant (mais touche backend + frontend)
```

### Phase 4 — Qualite

```
BLOC O — Refactoring backend (100% AGENT, sequentiel strict)
  4.1.1 → 4.1.2 → 4.1.3

BLOC P — Tests (100% AGENT, parallele mais avec pre-requis inter-phases)
  4.2.1 ── independant (mock, pas besoin du vrai OAuth)
  4.2.2 ── depend de 2.1.2 (le RedisQuotaManager doit exister)
  4.2.3 ── depend de 2.3.1-2.3.4 (les endpoints webhook doivent exister)
  4.2.4 ── independant
  4.2.5 ── independant

BLOC Q — Refactoring frontend (100% AGENT, parallele)
  4.3.1 ── independant
  4.3.2 ── independant (mais implique aussi le backend)
  4.3.3 ── independant
```

### Phase 5 — Infrastructure

```
BLOC R — Docker prod (100% AGENT, sequentiel)
  5.1.1 → 5.1.2 → 5.1.3

BLOC S — Base de donnees (AGENT + HUMAIN)
  5.2.1 (AGENT) ── independant
  5.2.2 (HUMAIN) ── independant
  5.2.3 (AGENT) ── independant

BLOC T — Domaine (100% HUMAIN, sequentiel strict)
  5.3.1 → 5.3.2 → 5.3.3
```

---

## 3. Ordre d'execution optimal

> En tenant compte des deux criteres : autonomie et cascades.
> Les taches AGENT peuvent etre lancees immediatement.
> Les taches HUMAIN sont signalees pour action manuelle.

### Vague 1 — Lancement immediat (100% AGENT, aucun bloquant)

Toutes ces taches sont independantes et peuvent etre executees **en parallele** par des agents :

| ID | Tache | Bloc |
|----|-------|------|
| 1.1.3 | Generer ENCRYPTION_KEY | A |
| 1.1.4 | Generer JWT_SECRET_KEY | A |
| 1.1.5 | Verifier .gitignore + historique | A |
| 1.2.3 | Nettoyer secrets docker-compose.dev.yml | B |
| 1.2.4 | Nettoyer defaults settings.py | B |
| 1.3.1-1.3.4 | Verrouiller CORS (un seul agent, tout le bloc) | C |
| 1.4.1-1.4.3 | Desactiver DEBUG (un seul agent, tout le bloc) | D |
| 1.5.1 | Ajouter FRONTEND_URL/BACKEND_URL dans settings | E |

**En parallele, demander au HUMAIN :**
- 1.1.1 : Regenerer STRAVA_CLIENT_SECRET
- 1.1.2 : Regenerer STRAVA_REFRESH_TOKEN

### Vague 2 — Apres Vague 1

| ID | Tache | Depend de | Type |
|----|-------|-----------|------|
| 1.1.6 | Mettre a jour .env.example | 1.1.3, 1.1.4 | AGENT |
| 1.5.2 | Remplacer URLs hardcodees routes.py | 1.5.1 | AGENT |
| 1.5.3 | STRAVA_REDIRECT_URI dynamique | 1.5.1 | AGENT |
| 1.5.4 | Google OAuth redirect dynamique | 1.5.1 | AGENT |

**En parallele, demander au HUMAIN :**
- 1.2.1 : Configurer env vars Render (apres 1.1.1-1.1.4)
- 1.2.2 : Configurer env vars Vercel

### Vague 3 — Apres Vague 2

| ID | Tache | Depend de | Type |
|----|-------|-----------|------|
| 1.5.5 | Mettre a jour dashboards Strava + Google | 1.5.3, 1.5.4 | HUMAIN |

→ **Fin de la Phase 1**

### Vague 4 — Phase 2 debut (parallelisable)

Trois blocs AGENT lancables en parallele :

**Agent A — Redis Quota :**
`2.1.1 → 2.1.2 → 2.1.3 → 2.1.4 → 2.1.5 → 2.1.6`

**Agent B — Queue d'enrichissement (debut) :**
`2.2.1 → 2.2.2`
(puis ATTENDRE 2.1.5 pour continuer avec 2.2.3)

**Agent C — Webhooks (debut) :**
`2.3.1 → 2.3.3 → 2.3.4`
`2.3.2` (en parallele de 2.3.1)

### Vague 5 — Phase 2 fin (apres convergence)

| ID | Tache | Depend de | Type |
|----|-------|-----------|------|
| 2.2.3 | Worker background | 2.1.5, 2.2.2 | AGENT |
| 2.2.4 | Endpoint position queue | 2.2.3 | AGENT |
| 2.2.5 | Retries avec backoff | 2.2.3 | AGENT |
| 2.3.5 | Auto-ajout queue sur event | 2.3.4, 2.2.1 | AGENT |
| 2.3.6 | Enregistrer webhook Strava | 2.3.1, 2.3.2 deployes | HUMAIN |
| 2.3.7 | Documenter webhook | 2.3.6 | AGENT |

### Vague 6 — Phase 3 (hautement parallelisable)

Cinq blocs AGENT lancables en parallele :

| Bloc | Taches | Agent dedie |
|------|--------|-------------|
| Rate limiting | 3.1.1 → 3.1.2/3.1.3/3.1.4/3.1.5 | Agent D |
| HTTPS | 3.2.1, 3.2.2, 3.2.3 | Agent E |
| Sentry backend + logging | 3.3.1, 3.3.4, 3.3.5 | Agent F |
| Sentry frontend + ErrorBoundary | 3.3.2 → 3.4.1 → 3.4.2 → 3.4.3 → 3.4.4 | Agent G |
| Migrations auto | 3.5.1 → 3.5.2 → 3.5.3 | Agent H |

**En parallele (AGENT independants) :** 3.6.1, 3.6.2, 3.6.3

**HUMAIN apres Agent F :** 3.3.3 (alertes Sentry)

### Vague 7 — Phase 4 (parallelisable)

| Bloc | Taches | Pre-requis |
|------|--------|------------|
| Refactoring backend | 4.1.1 → 4.1.2 → 4.1.3 | Aucun |
| Tests OAuth | 4.2.1 | Aucun |
| Tests quota | 4.2.2 | 2.1.2 (Phase 2) |
| Tests webhooks | 4.2.3 | 2.3.1-2.3.4 (Phase 2) |
| Tests frontend | 4.2.4, 4.2.5 | Aucun |
| Refactoring frontend | 4.3.1, 4.3.2, 4.3.3 | Aucun (4.3.2 touche aussi le backend) |

### Vague 8 — Phase 5 (optionnelle)

| Bloc | Taches | Type |
|------|--------|------|
| Docker prod | 5.1.1 → 5.1.2 → 5.1.3 | AGENT |
| DB pooling + index | 5.2.1, 5.2.3 | AGENT |
| DB backups | 5.2.2 | HUMAIN |
| Domaine | 5.3.1 → 5.3.2 → 5.3.3 | HUMAIN |

---

## 4. Resume chiffre

| Categorie | Nombre de taches |
|-----------|-----------------|
| **Total** | **~60** |
| **AGENT (autonome)** | **49** |
| **HUMAIN (intervention requise)** | **11** |
| **Blocs parallelisables en Vague 1** | **8 agents simultanes** |
| **Nombre de vagues** | **8** |
| **Chemin critique le plus long** | Phase 2 : `2.1.1 → ... → 2.1.5 → 2.2.3 → 2.2.4/2.2.5` (9 taches sequentielles) |
