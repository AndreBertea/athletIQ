# PLAN_GUIDE_AQUI.md — Classification des taches

> Ce fichier classe chaque tache du `DATA_AQI_PLAN.md` selon deux criteres :
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

Toutes les taches de ce plan sont du code pur : creation de modeles, services, routes, tests. Aucune ne necessite d'acces a un dashboard externe, de credentials manuels, ni d'action humaine.

> **Note :** Open-Meteo est gratuit et sans cle API. Garmin Connect utilise `garminconnect` avec credentials utilisateur saisis a l'execution (jamais stockes). Aucune configuration cloud ou dashboard externe n'est requise.

#### Etape 1 — Segmentation

| ID | Tache | Notes |
|----|-------|-------|
| 1.1.1 | Creer modele Segment | Nouveau fichier entity |
| 1.1.2 | Creer modele SegmentFeatures | Nouveau fichier entity |
| 1.1.3 | Migration Alembic `add_segment_tables` | Auto-generee |
| 1.1.4 | Ajouter imports dans `__init__.py` et `env.py` | Edition fichiers existants |
| 1.2.1 | Creer `segmentation_service.py` | Nouveau service |
| 1.2.2 | Logique de decoupage 100m | Inclus dans 1.2.1 |
| 1.2.3 | Gerer bug `streams_data = "null"` | Inclus dans 1.2.1 |
| 1.2.4 | Calcul pace_min_per_km (variable cible) | Inclus dans 1.2.1 |
| 1.3.1 | Creer `segment_router.py` | Nouveau router |
| 1.3.2 | Inclure dans `routers/__init__.py` | Edition fichier |
| 1.4.1 | Integration dans auto_enrichment_service | Edition fichier |
| 1.5.1 | Tests avec mock streams_data | Nouveaux tests |
| 1.5.2 | Verifier race_completion_pct | Inclus dans 1.5.1 |
| 1.5.3 | Verifier nombre de segments | Inclus dans 1.5.1 |

#### Etape 2 — Meteo

| ID | Tache | Notes |
|----|-------|-------|
| 2.1.1 | Creer modele ActivityWeather | Nouveau fichier entity |
| 2.1.2 | Migration Alembic `add_activity_weather` | Auto-generee |
| 2.1.3 | Ajouter imports dans `__init__.py` et `env.py` | Edition fichiers |
| 2.2.1 | Creer `weather_service.py` | Nouveau service |
| 2.2.2 | API Historical vs Forecast selon age de l'activite | Inclus dans 2.2.1 |
| 2.2.3 | Delai 100ms entre appels | Inclus dans 2.2.1 |
| 2.2.4 | Methodes fetch/enrich/is_fetched | Inclus dans 2.2.1 |
| 2.3.1 | Routes weather dans segment_router | Edition router |
| 2.4.1 | Integration dans auto_enrichment_service | Edition fichier |
| 2.5.1 | Mock HTTP response Open-Meteo | Nouveaux tests |
| 2.5.2 | Test fallback si pas de GPS | Inclus dans 2.5.1 |
| 2.5.3 | Verifier interpolation horaire | Inclus dans 2.5.1 |

#### Etape 3 — Garmin

| ID | Tache | Notes |
|----|-------|-------|
| 3.1.1 | Creer `garmin_auth.py` | Nouveau fichier auth (pattern strava_oauth.py) |
| 3.1.2 | Ajouter GarminAuth dans `user.py` | Edition entity |
| 3.1.3 | Flow auth : login one-time, token chiffre | Inclus dans 3.1.1 |
| 3.2.1 | Creer modele GarminDaily | Nouveau fichier entity |
| 3.2.2 | Migration Alembic `add_garmin_tables` | Auto-generee |
| 3.2.3 | Ajouter imports dans `__init__.py` et `env.py` | Edition fichiers |
| 3.3.1 | Creer `garmin_sync_service.py` | Nouveau service |
| 3.3.2 | Ajouter handlers dans `auth_service.py` | Edition service |
| 3.4.1 | Creer `garmin_router.py` | Nouveau router |
| 3.4.2 | Inclure dans `routers/__init__.py` | Edition fichier |
| 3.4.3 | Ajouter `garminconnect>=0.2.0` dans requirements | Edition fichier |
| 3.5.1 | Creer `GarminConnect.tsx` | Nouvelle page frontend |
| 3.5.2 | Creer `garminService.ts` | Nouveau service frontend |
| 3.5.3 | Route + navigation dans `App.tsx` et `Layout.tsx` | Edition fichiers |
| 3.6.1 | Mock Garmin API responses | Nouveaux tests |
| 3.6.2 | Test serialisation token Garth roundtrip | Nouveaux tests |
| 3.6.3 | Test sync avec champs manquants | Nouveaux tests |
| 3.6.4 | Test rate limit endpoint login | Nouveaux tests |
| 3.6.5 | Test frontend form + status | Nouveaux tests |

#### Etape 4 — Features derivees

| ID | Tache | Notes |
|----|-------|-------|
| 4.1.1 | Creer modele TrainingLoad | Nouveau fichier entity |
| 4.1.2 | Migration Alembic `add_training_load` | Auto-generee |
| 4.1.3 | Ajouter imports dans `__init__.py` et `env.py` | Edition fichiers |
| 4.2.1 | Creer `derived_features_service.py` (per-segment + per-day) | Nouveau service |
| 4.3.1 | Implementer Minetti cost | Inclus dans 4.2.1 |
| 4.3.2 | Implementer CTL (EWMA 42j) | Inclus dans 4.2.1 |
| 4.3.3 | Implementer ATL (EWMA 7j) | Inclus dans 4.2.1 |
| 4.3.4 | Implementer TSB = CTL - ATL | Inclus dans 4.2.1 |
| 4.4.1 | Routes features/training-load dans segment_router | Edition router |
| 4.5.1 | Valider Minetti contre valeurs connues | Nouveaux tests |
| 4.5.2 | Tester TRIMP avec activite connue | Nouveaux tests |
| 4.5.3 | Tester CTL/ATL convergence sur 60 jours | Nouveaux tests |
| 4.5.4 | Tester cardiac drift avec mock HR | Nouveaux tests |

#### Etape 5 — FIT files

| ID | Tache | Notes |
|----|-------|-------|
| 5.1.1 | Ajouter `fitparse>=0.0.14` dans requirements | Edition fichier |
| 5.1.2 | Download + parse FIT dans garmin_sync_service | Edition service |
| 5.2.1 | Tester parsing fichier FIT sample | Nouveaux tests |

### Taches HUMAIN (intervention humaine requise)

**Aucune.** Toutes les taches de ce plan sont realisables a 100% par un agent. Il n'y a pas de dashboard externe, de credentials a generer manuellement, ni de configuration cloud a faire.

> L'intervention humaine se limitera a :
> - **Tester avec de vrais comptes Garmin** (apres que le code soit ecrit)
> - **Verifier visuellement les donnees** dans l'app
> - **Decider si l'etape 5 (FIT files)** est necessaire

---

## 2. Graphe de dependances (cascades)

### Etape 1 — Segmentation

```
BLOC A — Modeles + Migration (sequentiel strict)
  1.1.1 ─┐
  1.1.2 ─┼→ 1.1.3 → 1.1.4
         │
BLOC B — Service (depend de A)
  1.1.4 → 1.2.1 (inclut 1.2.2, 1.2.3, 1.2.4)

BLOC C — Routes (depend de B)
  1.2.1 → 1.3.1 → 1.3.2

BLOC D — Integration (depend de B)
  1.2.1 → 1.4.1

BLOC E — Tests (depend de B + C)
  1.2.1 + 1.3.1 → 1.5.1 (inclut 1.5.2, 1.5.3)
```

### Etape 2 — Meteo

```
BLOC F — Modeles + Migration (sequentiel strict)
  2.1.1 → 2.1.2 → 2.1.3

BLOC G — Service (depend de F, beneficie de Etape 1 pour GPS)
  2.1.3 → 2.2.1 (inclut 2.2.2, 2.2.3, 2.2.4)

BLOC H — Routes (depend de G)
  2.2.1 → 2.3.1

BLOC I — Integration (depend de G)
  2.2.1 → 2.4.1

BLOC J — Tests (depend de G + H)
  2.2.1 + 2.3.1 → 2.5.1 (inclut 2.5.2, 2.5.3)
```

### Etape 3 — Garmin (independant des etapes 1-2)

```
BLOC K — Auth backend (sequentiel)
  3.1.1 → 3.1.2 → 3.1.3 (inclus dans 3.1.1)

BLOC L — Modeles + Migration (depend de K)
  3.1.2 → 3.2.1 → 3.2.2 → 3.2.3

BLOC M — Service (depend de K + L)
  3.2.3 → 3.3.1
  3.1.1 → 3.3.2

BLOC N — Routes (depend de M)
  3.3.1 + 3.3.2 → 3.4.1 → 3.4.2
  3.4.3 ── independant (requirements.txt)

BLOC O — Frontend (depend de N)
  3.4.1 → 3.5.1
  3.4.1 → 3.5.2
  3.5.1 + 3.5.2 → 3.5.3

BLOC P — Tests (depend de M + N + O)
  3.3.1 → 3.6.1, 3.6.2, 3.6.3
  3.4.1 → 3.6.4
  3.5.1 → 3.6.5
```

### Etape 4 — Features derivees (depend de Etape 1, optionnellement Etape 3)

```
BLOC Q — Modeles + Migration (sequentiel strict)
  4.1.1 → 4.1.2 → 4.1.3

BLOC R — Service (depend de Q + Etape 1 segments)
  4.1.3 → 4.2.1 (inclut 4.3.1, 4.3.2, 4.3.3, 4.3.4)

BLOC S — Routes (depend de R)
  4.2.1 → 4.4.1

BLOC T — Tests (depend de R)
  4.2.1 → 4.5.1, 4.5.2, 4.5.3, 4.5.4
```

### Etape 5 — FIT files (depend de Etape 3 Garmin auth)

```
BLOC U — Implementation (depend de 3.3.1)
  5.1.1 ── independant (requirements.txt)
  3.3.1 → 5.1.2

BLOC V — Tests (depend de U)
  5.1.2 → 5.2.1
```

### Dependances inter-etapes

```
Etape 1 ←── aucune dependance
    ↓
Etape 2 ←── beneficie de Etape 1 (GPS dans segments) mais peut tourner independamment
    ↓
Etape 4 ←── DEPEND de Etape 1 (segments obligatoires), optionnellement Etape 3 (RHR Garmin)

Etape 3 ←── aucune dependance, parallelisable avec Etapes 1-2

Etape 5 ←── DEPEND de Etape 3 (Garmin auth obligatoire)
```

---

## 3. Ordre d'execution optimal

> Toutes les taches sont AGENT. La loop Ralph s'execute en continu.
> Les pauses humaines ne se produisent qu'en cas d'echec ou de besoin de validation.

### Vague 1 — Etape 1 : Modeles et migration (fondations)

| ID | Tache | Bloc |
|----|-------|------|
| 1.1.1 | Creer modele Segment | A |
| 1.1.2 | Creer modele SegmentFeatures | A |
| 1.1.3 | Migration Alembic add_segment_tables | A |
| 1.1.4 | Imports dans __init__.py et env.py | A |

### Vague 2 — Etape 1 : Service, routes, integration, tests

| ID | Tache | Depend de | Bloc |
|----|-------|-----------|------|
| 1.2.1 | Creer segmentation_service.py | 1.1.4 | B |
| 1.2.2 | Logique decoupage 100m | 1.2.1 | B |
| 1.2.3 | Gerer bug streams_data "null" | 1.2.1 | B |
| 1.2.4 | Calcul pace_min_per_km | 1.2.1 | B |
| 1.3.1 | Creer segment_router.py | 1.2.1 | C |
| 1.3.2 | Inclure dans routers/__init__.py | 1.3.1 | C |
| 1.4.1 | Integration auto_enrichment_service | 1.2.1 | D |
| 1.5.1 | Tests avec mock streams_data | 1.2.1 | E |
| 1.5.2 | Verifier race_completion_pct | 1.5.1 | E |
| 1.5.3 | Verifier nombre de segments | 1.5.1 | E |

### Vague 3 — Etape 2 : Meteo (complet)

| ID | Tache | Depend de | Bloc |
|----|-------|-----------|------|
| 2.1.1 | Creer modele ActivityWeather | — | F |
| 2.1.2 | Migration Alembic add_activity_weather | 2.1.1 | F |
| 2.1.3 | Imports dans __init__.py et env.py | 2.1.2 | F |
| 2.2.1 | Creer weather_service.py | 2.1.3 | G |
| 2.2.2 | API Historical vs Forecast | 2.2.1 | G |
| 2.2.3 | Delai 100ms entre appels | 2.2.1 | G |
| 2.2.4 | Methodes fetch/enrich/is_fetched | 2.2.1 | G |
| 2.3.1 | Routes weather dans segment_router | 2.2.1 | H |
| 2.4.1 | Integration auto_enrichment_service | 2.2.1 | I |
| 2.5.1 | Mock HTTP response Open-Meteo | 2.2.1 | J |
| 2.5.2 | Test fallback si pas de GPS | 2.5.1 | J |
| 2.5.3 | Verifier interpolation horaire | 2.5.1 | J |

### Vague 4 — Etape 3 : Garmin backend (auth + modeles + service + routes)

| ID | Tache | Depend de | Bloc |
|----|-------|-----------|------|
| 3.1.1 | Creer garmin_auth.py | — | K |
| 3.1.2 | GarminAuth dans user.py | 3.1.1 | K |
| 3.1.3 | Flow auth one-time | 3.1.1 | K |
| 3.2.1 | Creer modele GarminDaily | 3.1.2 | L |
| 3.2.2 | Migration Alembic add_garmin_tables | 3.2.1 | L |
| 3.2.3 | Imports dans __init__.py et env.py | 3.2.2 | L |
| 3.3.1 | Creer garmin_sync_service.py | 3.2.3 | M |
| 3.3.2 | Handlers dans auth_service.py | 3.1.1 | M |
| 3.4.1 | Creer garmin_router.py | 3.3.1 | N |
| 3.4.2 | Inclure dans routers/__init__.py | 3.4.1 | N |
| 3.4.3 | garminconnect dans requirements.txt | — | N |

### Vague 5 — Etape 3 : Garmin frontend + tests

| ID | Tache | Depend de | Bloc |
|----|-------|-----------|------|
| 3.5.1 | Creer GarminConnect.tsx | 3.4.1 | O |
| 3.5.2 | Creer garminService.ts | 3.4.1 | O |
| 3.5.3 | Route + navigation App.tsx/Layout | 3.5.1, 3.5.2 | O |
| 3.6.1 | Mock Garmin API responses | 3.3.1 | P |
| 3.6.2 | Test serialisation token Garth | 3.1.1 | P |
| 3.6.3 | Test sync champs manquants | 3.3.1 | P |
| 3.6.4 | Test rate limit endpoint login | 3.4.1 | P |
| 3.6.5 | Test frontend form + status | 3.5.1 | P |

### Vague 6 — Etape 4 : Features derivees (complet)

| ID | Tache | Depend de | Bloc |
|----|-------|-----------|------|
| 4.1.1 | Creer modele TrainingLoad | — | Q |
| 4.1.2 | Migration Alembic add_training_load | 4.1.1 | Q |
| 4.1.3 | Imports dans __init__.py et env.py | 4.1.2 | Q |
| 4.2.1 | Creer derived_features_service.py | 4.1.3, Etape 1 | R |
| 4.3.1 | Implementer Minetti cost | 4.2.1 | R |
| 4.3.2 | Implementer CTL (EWMA 42j) | 4.2.1 | R |
| 4.3.3 | Implementer ATL (EWMA 7j) | 4.2.1 | R |
| 4.3.4 | Implementer TSB | 4.2.1 | R |
| 4.4.1 | Routes features/training-load | 4.2.1 | S |
| 4.5.1 | Valider Minetti | 4.2.1 | T |
| 4.5.2 | Tester TRIMP | 4.2.1 | T |
| 4.5.3 | Tester CTL/ATL convergence | 4.2.1 | T |
| 4.5.4 | Tester cardiac drift | 4.2.1 | T |

### Vague 7 — Etape 5 : FIT files (optionnel)

| ID | Tache | Depend de | Bloc |
|----|-------|-----------|------|
| 5.1.1 | fitparse dans requirements.txt | — | U |
| 5.1.2 | Download + parse FIT dans garmin_sync_service | Etape 3 | U |
| 5.2.1 | Tester parsing fichier FIT sample | 5.1.2 | V |

---

## 4. Resume chiffre

| Categorie | Nombre de taches |
|-----------|-----------------|
| **Total** | **~50** |
| **AGENT (autonome)** | **50** |
| **HUMAIN (intervention requise)** | **0** |
| **Nombre de vagues** | **7** |
| **Chemin critique le plus long** | Etape 1 → Etape 4 : `1.1.1 → ... → 1.5.3 → 4.1.1 → ... → 4.5.4` |
| **Etapes parallelisables** | Etapes 1-2 en parallele de Etape 3 |
