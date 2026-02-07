# athletIQ — Plan d'Acquisition de Donnees (Race Predictor v2)

> Ce document est le plan directeur pour le pipeline de donnees du Race Predictor v2.
> Il est lu par Claude a chaque iteration pour comprendre l'etat d'avancement.
> Chaque tache a un statut : `[ ]` (a faire), `[~]` (en cours), `[x]` (termine).

---

## Legende des statuts

- `[ ]` A faire
- `[~]` En cours
- `[x]` Termine
- `[!]` Bloque (voir notes)

---

## Contexte

L'ancien Race Predictor a ete archive (`archive/race-predictor-v1`). On construit maintenant le pipeline de donnees complet qui alimentera les futurs modeles de prediction. **Phase 1 = donnees uniquement, pas de modeles.**

- 3 sources de donnees : Strava (existant), Garmin Connect (nouveau), Open-Meteo meteo (nouveau)
- 4 groupes de features : terrain, etat du jour, dynamiques, derivees avancees
- Architecture multi-utilisateur des le depart

### Ordre d'implementation et dependances

```
Etape 1 (Segmentation)  <── aucune dependance
    |
Etape 2 (Meteo)         <── beneficie de l'etape 1 (GPS dans segments) mais peut tourner independamment
    |
Etape 4 (Features)      <── depend de l'etape 1 (segments), optionnellement etape 3 (Garmin pour RHR)

Etape 3 (Garmin)        <── aucune dependance, peut etre fait en parallele des etapes 1-2
    |
Etape 5 (FIT files)     <── depend de l'etape 3 (Garmin auth)
```

**Recommandation :** Etape 1 → Etape 2 → Etape 3 → Etape 4 → Etape 5.
L'etape 3 (Garmin) est la plus risquee (API non-officielle, auth complexe) donc pas en premier.

### Resume des fichiers

**18 fichiers a creer, 12 a modifier.**

| Etape | Creer | Modifier | Complexite |
|-------|-------|----------|------------|
| 1 — Segmentation | 5 | 4 | L |
| 2 — Meteo | 3 | 4 | M |
| 3 — Garmin | 7 | 6 | L |
| 4 — Features derivees | 3 | 3 | M |
| 5 — FIT files | 0 | 2 | S |

---

## Etape 1 — Segmentation des streams + Features dynamiques (L)

> But : Decouper les `streams_data` existants en segments de ~100m et calculer les features cumulatives.

### 1.1 Modeles et migration

- [x] **1.1.1** Creer `backend/app/domain/entities/segment.py` — Modele Segment (activity_id, user_id, segment_index, distance_m, elapsed_time_s, avg_grade_percent, elevation_gain/loss_m, altitude_m, avg_hr, avg_cadence, lat, lon, pace_min_per_km)
- [x] **1.1.2** Creer `backend/app/domain/entities/segment_features.py` — Modele SegmentFeatures (segment_id, activity_id, cumulative_distance_km, elapsed_time_min, cumulative_elev_gain/loss_m, race_completion_pct, intensity_proxy, + champs Minetti/drift/cadence_decay remplis a l'etape 4)
- [x] **1.1.3** Generer la migration Alembic `add_segment_tables`
- [x] **1.1.4** Ajouter les imports dans `backend/app/domain/entities/__init__.py` et `backend/alembic/env.py`

### 1.2 Service de segmentation

- [x] **1.2.1** Creer `backend/app/domain/services/segmentation_service.py` — Methodes : `segment_activity()`, `segment_all_enriched()`, `is_activity_segmented()`
- [x] **1.2.2** Logique cle : parcourir `distance.data`, couper a chaque 100m, moyenner HR/cadence/grade, sommer elevation, midpoint GPS
- [x] **1.2.3** Gerer le bug connu `streams_data = "null"` (string) → traiter comme None
- [x] **1.2.4** Variable cible : `pace_min_per_km = (elapsed_time_s / 60) / (distance_m / 1000)`

### 1.3 Routes API

- [x] **1.3.1** Creer `backend/app/api/routers/segment_router.py` — Routes : `POST /segments/process`, `POST /segments/process/{activity_id}`, `GET /segments/{activity_id}`, `GET /segments/status`
- [x] **1.3.2** Inclure segment_router dans `backend/app/api/routers/__init__.py`

### 1.4 Integration auto-enrichment

- [x] **1.4.1** Dans `auto_enrichment_service.py`, apres enrichissement Strava appeler `segmentation_service.segment_activity()` (try/except, non-bloquant)

### 1.5 Tests

- [x] **1.5.1** pytest avec mock streams_data (5-10 points GPS)
- [x] **1.5.2** Verifier que race_completion_pct va de 0 a ~100
- [x] **1.5.3** Verifier le nombre de segments ≈ distance_totale / 100

---

## Etape 2 — Enrichissement meteo (M)

> But : Pour chaque activite avec GPS, fetcher la meteo historique via Open-Meteo (gratuit, pas de cle API).

### 2.1 Modele et migration

- [x] **2.1.1** Creer `backend/app/domain/entities/activity_weather.py` — Modele ActivityWeather (activity_id unique, temperature_c, humidity_pct, wind_speed_kmh, wind_direction_deg, pressure_hpa, precipitation_mm, cloud_cover_pct, weather_code)
- [x] **2.1.2** Generer la migration Alembic `add_activity_weather`
- [x] **2.1.3** Ajouter les imports dans `__init__.py` et `env.py`

### 2.2 Service meteo

- [ ] **2.2.1** Creer `backend/app/domain/services/weather_service.py` — Extraire lat/lon du 1er point GPS dans streams_data, appeler Open-Meteo, trouver l'heure la plus proche du start_date
- [ ] **2.2.2** API : Historical (`archive-api.open-meteo.com`) si activite > 5 jours, Forecast (`api.open-meteo.com`) sinon
- [ ] **2.2.3** Delai 100ms entre appels. Rate limit genereux (~10k req/jour)
- [ ] **2.2.4** Methodes : `fetch_weather_for_activity()`, `enrich_all_weather()`, `is_weather_fetched()`

### 2.3 Routes API

- [ ] **2.3.1** Ajouter dans segment_router : `GET /weather/{activity_id}`, `POST /weather/enrich`, `GET /weather/status`

### 2.4 Integration auto-enrichment

- [ ] **2.4.1** Apres segmentation, appeler `weather_service.fetch_weather_for_activity()` (try/except, non-bloquant)

### 2.5 Tests

- [ ] **2.5.1** Mock HTTP response Open-Meteo
- [ ] **2.5.2** Tester fallback si pas de GPS
- [ ] **2.5.3** Verifier interpolation horaire correcte

---

## Etape 3 — Integration Garmin Connect (L)

> But : Connexion Garmin dans l'app, sync quotidien des donnees physiologiques (HRV, Training Readiness, sommeil, stress, etc.).

### 3.1 Backend Auth

- [ ] **3.1.1** Creer `backend/app/auth/garmin_auth.py` — GarminAuthManager : `login(email, password)` → serialise le token Garth, `get_client(encrypted_token)` → reconstruit sans re-login, `encrypt_token()` / `decrypt_token()` (Fernet, meme pattern que strava_oauth.py)
- [ ] **3.1.2** Ajouter GarminAuth dans `backend/app/domain/entities/user.py` (user_id unique FK, garmin_display_name, oauth_token_encrypted, token_created_at, last_sync_at)
- [ ] **3.1.3** **Email et mot de passe ne sont JAMAIS stockes** — login one-time, token Garth chiffre

### 3.2 Modele et migration

- [ ] **3.2.1** Creer `backend/app/domain/entities/garmin_daily.py` — Modele GarminDaily (user_id, date, training_readiness, hrv_rmssd, sleep_score, sleep_duration_min, resting_hr, stress_score, spo2, vo2max_estimated, weight_kg, body_battery_max/min, training_status). Contrainte unique (user_id, date).
- [ ] **3.2.2** Generer la migration Alembic `add_garmin_tables` (garminauth + garmin_daily)
- [ ] **3.2.3** Ajouter les imports dans `__init__.py` et `env.py`

### 3.3 Service de sync Garmin

- [ ] **3.3.1** Creer `backend/app/domain/services/garmin_sync_service.py` — `sync_daily_data(session, user_id, days_back=30)` : boucle sur chaque date, appelle les endpoints Garmin (get_training_readiness, get_hrv_data, get_sleep_data, get_rhr_day, get_stress_data, get_spo2_data, get_body_composition, get_body_battery), upsert dans garmin_daily. Delai 500ms entre dates.
- [ ] **3.3.2** Ajouter `handle_garmin_login()`, `get_garmin_status()`, `disconnect_garmin()` dans `auth_service.py`

### 3.4 Routes API

- [ ] **3.4.1** Creer `backend/app/api/routers/garmin_router.py` — Routes : `POST /auth/garmin/login` (rate limit 3/h), `GET /auth/garmin/status`, `DELETE /auth/garmin/disconnect`, `POST /sync/garmin?days_back=30`, `GET /garmin/daily?date_from=&date_to=`
- [ ] **3.4.2** Inclure garmin_router dans `__init__.py`
- [ ] **3.4.3** Ajouter `garminconnect>=0.2.0` dans `requirements.txt`

### 3.5 Frontend

- [ ] **3.5.1** Creer `frontend/src/pages/GarminConnect.tsx` — Si non connecte : formulaire email/password + notice "identifiants non stockes" ; si connecte : status, bouton sync, selecteur days_back, apercu 7 derniers jours (HRV, Training Readiness, Sleep), bouton deconnexion
- [ ] **3.5.2** Creer `frontend/src/services/garminService.ts` — `loginGarmin()`, `getGarminStatus()`, `disconnectGarmin()`, `syncGarminDaily()`, `getGarminDaily()`
- [ ] **3.5.3** Ajouter route `/garmin-connect` dans `App.tsx` (React.lazy) + lien navigation dans Layout

### 3.6 Tests

- [ ] **3.6.1** Mock Garmin API responses (garminconnect)
- [ ] **3.6.2** Tester serialisation/deserialisation token Garth roundtrip
- [ ] **3.6.3** Tester sync avec champs manquants (montre pas portee un jour → NULL)
- [ ] **3.6.4** Tester rate limit sur endpoint login
- [ ] **3.6.5** Tester frontend form + status display

---

## Etape 4 — Features derivees avancees (M)

> But : Calculer Minetti cost, grade variability, CTL/ATL/TSB (Banister), cardiac drift, efficiency factor, cadence decay.

### 4.1 Modele et migration

- [ ] **4.1.1** Creer `backend/app/domain/entities/training_load.py` — Modele TrainingLoad (user_id, date, ctl_42d, atl_7d, tsb, rhr_delta_7d). Contrainte unique (user_id, date).
- [ ] **4.1.2** Generer la migration Alembic `add_training_load`
- [ ] **4.1.3** Ajouter les imports dans `__init__.py` et `env.py`

### 4.2 Service de features derivees

- [ ] **4.2.1** Creer `backend/app/domain/services/derived_features_service.py` — Deux axes :
  - **A) Per-segment** (remplit les champs vides de segment_features) : minetti_cost, grade_variability, efficiency_factor, cardiac_drift, cadence_decay
  - **B) Per-day** (remplit training_load) : TRIMP, CTL (EWMA 42j), ATL (EWMA 7j), TSB = CTL - ATL, rhr_delta_7d (si Garmin dispo)

### 4.3 Formules cles

- [ ] **4.3.1** Minetti : `C(i) = 155.4*i^5 - 30.4*i^4 - 43.3*i^3 + 46.3*i^2 + 19.5*i + 3.6` (cout metabolique J/(kg·m), grade i en fraction)
- [ ] **4.3.2** CTL : `CTL_today = CTL_yesterday * (1 - 1/42) + TRIMP_today * (1/42)` (EWMA 42 jours)
- [ ] **4.3.3** ATL : `ATL_today = ATL_yesterday * (1 - 1/7) + TRIMP_today * (1/7)` (EWMA 7 jours)
- [ ] **4.3.4** TSB : `TSB = CTL - ATL` (positif = frais, negatif = fatigue)

### 4.4 Routes API

- [ ] **4.4.1** Ajouter dans segment_router : `POST /features/compute`, `POST /features/compute/{activity_id}`, `GET /training-load?date_from=&date_to=`, `POST /training-load/compute`

### 4.5 Tests

- [ ] **4.5.1** Valider Minetti contre valeurs connues (grade 0 → ~3.6 J/(kg·m), grade -0.1 → minimum)
- [ ] **4.5.2** Tester TRIMP avec activite connue
- [ ] **4.5.3** Tester CTL/ATL convergence sur 60 jours
- [ ] **4.5.4** Tester cardiac drift avec mock HR croissant

---

## Etape 5 — FIT Files Garmin (S, optionnel)

> But : Telecharger les FIT files Garmin pour extraire Running Dynamics (ground contact time, vertical oscillation, balance G/D), puissance estimee, Training Effect.

### 5.1 Parsing FIT

- [ ] **5.1.1** Ajouter `fitparse>=0.0.14` dans `requirements.txt`
- [ ] **5.1.2** Dans `garmin_sync_service.py`, ajouter `download_fit_file(garmin_activity_id)` et `parse_fit_file(fit_bytes)` → extraire Running Dynamics, power, Training Effect

### 5.2 Tests

- [ ] **5.2.1** Tester parsing d'un fichier FIT sample

---

## Gestion des erreurs

| Scenario | Traitement |
|----------|-----------|
| streams_data manquant ou "null" | Skip, log warning, continuer |
| Pas de GPS pour meteo | Skip meteo pour cette activite |
| Open-Meteo down / 429 | Delai 100ms, retry, skip si persistant |
| Login Garmin echoue | Retourner 401 + message clair |
| Token Garth expire | Reporter status, demander re-login |
| Garmin API 429 | Delai 500ms, backoff exponentiel |
| Champ Garmin manquant (pas de HRV un jour) | Stocker NULL, continuer |
| HR manquant pour features derivees | Skip cardiac_drift/efficiency_factor, calculer le reste |

---

## Journal des modifications

| Date | Etape | Tache | Statut | Notes |
|------|-------|-------|--------|-------|
| 2026-02-07 | — | — | [x] | Creation du plan DATA_AQI_PLAN.md |
| 2026-02-07 | 1 | 1.1.1 | [x] | Cree `segment.py` : modele Segment (16 champs) + schema SegmentRead. Import verifie OK. |
| 2026-02-07 | 1 | 1.1.2 | [x] | Cree `segment_features.py` : modele SegmentFeatures (15 champs) + schema SegmentFeaturesRead. Champs etape 4 (minetti_cost, cardiac_drift, cadence_decay, grade_variability, efficiency_factor) presents mais Optional. Import verifie OK. |
| 2026-02-07 | 1 | 1.1.3 | [x] | Cree migration `b3f4a5c6d7e8_add_segment_tables.py` : tables `segment` (16 cols, FK activity+user, index activity_id+user_id) et `segmentfeatures` (15 cols, FK segment+activity, unique segment_id, index segment_id+activity_id). down_revision = add_parsing_fields. |
| 2026-02-07 | 1 | 1.1.4 | [x] | Ajout imports Segment, SegmentRead dans `__init__.py` et `env.py`. Ajout imports SegmentFeatures, SegmentFeaturesRead dans `__init__.py` et `env.py`. Import verifie OK. |
| 2026-02-07 | 1 | 1.2.1-1.2.4 | [x] | Cree `segmentation_service.py` : 3 fonctions publiques (segment_activity, segment_all_enriched, is_activity_segmented). Decoupage 100m sur distance.data, moyennes HR/cadence/grade, somme elevation, midpoint GPS, pace_min_per_km. Bug "null" string gere via _parse_streams(). SegmentFeatures crees en meme temps (cumulatifs, race_completion_pct, intensity_proxy). |
| 2026-02-07 | 1 | 1.3.1 | [x] | Cree `segment_router.py` : 4 routes (POST /segments/process, POST /segments/process/{activity_id}, GET /segments/{activity_id}, GET /segments/status). Pattern identique aux autres routers (security, get_session, get_current_user_id). Verification ownership activite sur toutes les routes. Status inclut total/enriched/segmented/pending/total_segments. |
| 2026-02-07 | 1 | 1.3.2 | [x] | Ajout import + include de segment_router dans `__init__.py`. 50 routes totales enregistrees, import verifie OK. |
| 2026-02-07 | 1 | 1.4.1 | [x] | Dans `_enrich_single_activity()`, apres enrichissement Strava reussi, appel `segment_activity(session, activity)` dans try/except non-bloquant. Log info si segments crees, log warning si echec. Import ajoute en haut du fichier. |
| 2026-02-07 | 1 | 1.5.1 | [x] | Cree `tests/test_segmentation_service.py` : 32 tests avec mock streams_data (5 et 10 points GPS). Couvre _parse_streams (bug "null"), _get_data, _mean, segment_activity (nombre segments, distances, indices, pace, HR/cadence, GPS, elevation, features cumulatifs, intensity_proxy, re-segmentation), is_activity_segmented. Tous les tests passent. |
| 2026-02-07 | 1 | 1.5.2 | [x] | Ajoute 4 tests dans `TestRaceCompletionPct` : range 0→100 (10 pts), monotonically increasing, range 0→100 (5 pts), valeurs attendues exactes. 36/36 tests passent. |
| 2026-02-07 | 1 | 1.5.3 | [x] | Ajoute 5 tests dans `TestSegmentCountApprox` : verifie nb segments ≈ distance/100 pour 900m, 400m, 2km, espacement irregulier (600m), et courte distance (150m). 41/41 tests passent. |
| 2026-02-07 | 2 | 2.1.1 | [x] | Cree `activity_weather.py` : modele ActivityWeather (11 cols : id, activity_id unique+indexe FK activity, temperature_c, humidity_pct, wind_speed_kmh, wind_direction_deg, pressure_hpa, precipitation_mm, cloud_cover_pct, weather_code, created_at) + schema ActivityWeatherRead. Import verifie OK. |
| 2026-02-07 | 2 | 2.1.2 | [x] | Cree migration `c4e5f6a7b8d9_add_activity_weather.py` : table `activityweather` (11 cols : id PK, activity_id unique+indexe FK activity, temperature_c, humidity_pct, wind_speed_kmh, wind_direction_deg, pressure_hpa, precipitation_mm, cloud_cover_pct, weather_code, created_at). down_revision = b3f4a5c6d7e8. |
| 2026-02-07 | 2 | 2.1.3 | [x] | Ajout imports ActivityWeather, ActivityWeatherRead dans `__init__.py` et import ActivityWeather dans `env.py`. Import verifie OK. |
| _A remplir au fur et a mesure_ | | | | |
