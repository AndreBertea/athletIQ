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

- [x] **2.2.1** Creer `backend/app/domain/services/weather_service.py` — Extraire lat/lon du 1er point GPS dans streams_data, appeler Open-Meteo, trouver l'heure la plus proche du start_date
- [x] **2.2.2** API : Historical (`archive-api.open-meteo.com`) si activite > 5 jours, Forecast (`api.open-meteo.com`) sinon
- [x] **2.2.3** Delai 100ms entre appels. Rate limit genereux (~10k req/jour)
- [x] **2.2.4** Methodes : `fetch_weather_for_activity()`, `enrich_all_weather()`, `is_weather_fetched()`

### 2.3 Routes API

- [x] **2.3.1** Ajouter dans segment_router : `GET /weather/{activity_id}`, `POST /weather/enrich`, `GET /weather/status`

### 2.4 Integration auto-enrichment

- [x] **2.4.1** Apres segmentation, appeler `weather_service.fetch_weather_for_activity()` (try/except, non-bloquant)

### 2.5 Tests

- [x] **2.5.1** Mock HTTP response Open-Meteo
- [x] **2.5.2** Tester fallback si pas de GPS
- [x] **2.5.3** Verifier interpolation horaire correcte

---

## Etape 3 — Integration Garmin Connect (L)

> But : Connexion Garmin dans l'app, sync quotidien des donnees physiologiques (HRV, Training Readiness, sommeil, stress, etc.).

### 3.1 Backend Auth

- [x] **3.1.1** Creer `backend/app/auth/garmin_auth.py` — GarminAuthManager : `login(email, password)` → serialise le token Garth, `get_client(encrypted_token)` → reconstruit sans re-login, `encrypt_token()` / `decrypt_token()` (Fernet, meme pattern que strava_oauth.py)
- [x] **3.1.2** Ajouter GarminAuth dans `backend/app/domain/entities/user.py` (user_id unique FK, garmin_display_name, oauth_token_encrypted, token_created_at, last_sync_at)
- [x] **3.1.3** **Email et mot de passe ne sont JAMAIS stockes** — login one-time, token Garth chiffre

### 3.2 Modele et migration

- [x] **3.2.1** Creer `backend/app/domain/entities/garmin_daily.py` — Modele GarminDaily (user_id, date, training_readiness, hrv_rmssd, sleep_score, sleep_duration_min, resting_hr, stress_score, spo2, vo2max_estimated, weight_kg, body_battery_max/min, training_status). Contrainte unique (user_id, date).
- [x] **3.2.2** Generer la migration Alembic `add_garmin_tables` (garminauth + garmin_daily)
- [x] **3.2.3** Ajouter les imports dans `__init__.py` et `env.py`

### 3.3 Service de sync Garmin

- [x] **3.3.1** Creer `backend/app/domain/services/garmin_sync_service.py` — `sync_daily_data(session, user_id, days_back=30)` : boucle sur chaque date, appelle les endpoints Garmin (get_training_readiness, get_hrv_data, get_sleep_data, get_rhr_day, get_stress_data, get_spo2_data, get_body_composition, get_body_battery), upsert dans garmin_daily. Delai 500ms entre dates.
- [x] **3.3.2** Ajouter `handle_garmin_login()`, `get_garmin_status()`, `disconnect_garmin()` dans `auth_service.py`

### 3.4 Routes API

- [x] **3.4.1** Creer `backend/app/api/routers/garmin_router.py` — Routes : `POST /auth/garmin/login` (rate limit 3/h), `GET /auth/garmin/status`, `DELETE /auth/garmin/disconnect`, `POST /sync/garmin?days_back=30`, `GET /garmin/daily?date_from=&date_to=`
- [x] **3.4.2** Inclure garmin_router dans `__init__.py`
- [x] **3.4.3** Ajouter `garminconnect>=0.2.0` dans `requirements.txt`

### 3.5 Frontend

- [x] **3.5.1** Creer `frontend/src/pages/GarminConnect.tsx` — Si non connecte : formulaire email/password + notice "identifiants non stockes" ; si connecte : status, bouton sync, selecteur days_back, apercu 7 derniers jours (HRV, Training Readiness, Sleep), bouton deconnexion
- [x] **3.5.2** Creer `frontend/src/services/garminService.ts` — `loginGarmin()`, `getGarminStatus()`, `disconnectGarmin()`, `syncGarminDaily()`, `getGarminDaily()`
- [x] **3.5.3** Ajouter route `/garmin-connect` dans `App.tsx` (React.lazy) + lien navigation dans Layout

### 3.6 Tests

- [x] **3.6.1** Mock Garmin API responses (garminconnect)
- [x] **3.6.2** Tester serialisation/deserialisation token Garth roundtrip
- [x] **3.6.3** Tester sync avec champs manquants (montre pas portee un jour → NULL)
- [x] **3.6.4** Tester rate limit sur endpoint login
- [x] **3.6.5** Tester frontend form + status display

---

## Etape 4 — Features derivees avancees (M)

> But : Calculer Minetti cost, grade variability, CTL/ATL/TSB (Banister), cardiac drift, efficiency factor, cadence decay.

### 4.1 Modele et migration

- [x] **4.1.1** Creer `backend/app/domain/entities/training_load.py` — Modele TrainingLoad (user_id, date, ctl_42d, atl_7d, tsb, rhr_delta_7d). Contrainte unique (user_id, date).
- [x] **4.1.2** Generer la migration Alembic `add_training_load`
- [x] **4.1.3** Ajouter les imports dans `__init__.py` et `env.py`

### 4.2 Service de features derivees

- [x] **4.2.1** Creer `backend/app/domain/services/derived_features_service.py` — Deux axes :
  - **A) Per-segment** (remplit les champs vides de segment_features) : minetti_cost, grade_variability, efficiency_factor, cardiac_drift, cadence_decay
  - **B) Per-day** (remplit training_load) : TRIMP, CTL (EWMA 42j), ATL (EWMA 7j), TSB = CTL - ATL, rhr_delta_7d (si Garmin dispo)

### 4.3 Formules cles

- [x] **4.3.1** Minetti : `C(i) = 155.4*i^5 - 30.4*i^4 - 43.3*i^3 + 46.3*i^2 + 19.5*i + 3.6` (cout metabolique J/(kg·m), grade i en fraction)
- [x] **4.3.2** CTL : `CTL_today = CTL_yesterday * (1 - 1/42) + TRIMP_today * (1/42)` (EWMA 42 jours)
- [x] **4.3.3** ATL : `ATL_today = ATL_yesterday * (1 - 1/7) + TRIMP_today * (1/7)` (EWMA 7 jours)
- [x] **4.3.4** TSB : `TSB = CTL - ATL` (positif = frais, negatif = fatigue)

### 4.4 Routes API

- [x] **4.4.1** Ajouter dans segment_router : `POST /features/compute`, `POST /features/compute/{activity_id}`, `GET /training-load?date_from=&date_to=`, `POST /training-load/compute`

### 4.5 Tests

- [x] **4.5.1** Valider Minetti contre valeurs connues (grade 0 → ~3.6 J/(kg·m), grade -0.1 → minimum)
- [x] **4.5.2** Tester TRIMP avec activite connue
- [x] **4.5.3** Tester CTL/ATL convergence sur 60 jours
- [x] **4.5.4** Tester cardiac drift avec mock HR croissant

---

## Etape 5 — FIT Files Garmin (S, optionnel)

> But : Telecharger les FIT files Garmin pour extraire Running Dynamics (ground contact time, vertical oscillation, balance G/D), puissance estimee, Training Effect.

### 5.1 Parsing FIT

- [x] **5.1.1** Ajouter `fitparse>=0.0.14` dans `requirements.txt`
- [x] **5.1.2** Dans `garmin_sync_service.py`, ajouter `download_fit_file(garmin_activity_id)` et `parse_fit_file(fit_bytes)` → extraire Running Dynamics, power, Training Effect

### 5.2 Tests

- [x] **5.2.1** Tester parsing d'un fichier FIT sample

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
| 2026-02-07 | 2 | 2.2.1 | [x] | Cree `weather_service.py` : 3 fonctions publiques (fetch_weather_for_activity, enrich_all_weather, is_weather_fetched). Extraction lat/lon du 1er point GPS via _extract_first_gps(). Appel Open-Meteo Historical (>5j) ou Forecast (<=5j) via httpx async. Interpolation horaire via _find_closest_hour_index(). Delai 100ms entre appels. Gestion bug "null" string. Syntax + imports verifies OK. |
| 2026-02-07 | 2 | 2.2.2 | [x] | Deja implemente dans weather_service.py lors de 2.2.1 : `_call_open_meteo()` choisit `HISTORICAL_BASE_URL` (archive-api) si `days_ago > 5`, sinon `FORECAST_BASE_URL` (api.open-meteo.com). Seuil defini via `HISTORICAL_THRESHOLD_DAYS = 5`. Verifie et marque complete. |
| 2026-02-07 | 2 | 2.2.3 | [x] | Delai 100ms deja implemente : constante `REQUEST_DELAY_S = 0.1` (ligne 32) + `await asyncio.sleep(REQUEST_DELAY_S)` dans `enrich_all_weather()` (ligne 238). Verifie et marque complete. |
| 2026-02-07 | 2 | 2.2.4 | [x] | Verifie que les 3 methodes publiques (fetch_weather_for_activity, enrich_all_weather, is_weather_fetched) sont deja implementees dans weather_service.py (fait lors de 2.2.1). Syntax + imports verifies OK. Marque complete. |
| 2026-02-07 | 2 | 2.3.1 | [x] | Ajout 3 routes meteo dans `segment_router.py` : GET /weather/{activity_id} (retourne ActivityWeatherRead), POST /weather/enrich (appelle enrich_all_weather avec user_id), GET /weather/status (total/with_streams/with_weather/pending). Imports ActivityWeather, ActivityWeatherRead, weather_service ajoutes. 7 routes totales dans le router. Syntax + import + 41 tests OK. |
| 2026-02-07 | 2 | 2.4.1 | [x] | Dans `auto_enrichment_service.py`, apres segmentation, ajout appel `await fetch_weather_for_activity(session, activity)` dans try/except non-bloquant. Import ajoute. Pattern identique a la segmentation (log info si OK, log warning si echec). Syntaxe + 41 tests OK. |
| 2026-02-07 | 2 | 2.5.1 | [x] | Cree `tests/test_weather_service.py` : 29 tests avec mock HTTP Open-Meteo. Couvre _extract_first_gps (7 tests : dict/list format, no key, empty, None, invalid points, single value), _find_closest_hour_index (5 tests : exact/closest match, single/empty hours), _build_weather_from_response (4 tests : mapping correct, no hourly, empty time, weather_code int), _call_open_meteo (5 tests : historical vs forecast URL, HTTP/network error → None, params corrects), fetch_weather_for_activity (6 tests : success + stockage DB, already fetched skip, no streams/GPS/null string → False, API failure), is_weather_fetched (2 tests). 29/29 passent. |
| 2026-02-07 | 2 | 2.5.2 | [x] | Ajout classe `TestFallbackNoGps` dans `test_weather_service.py` : 7 tests couvrant latlng vide, points GPS invalides (None), points a 1 element, JSON string sans GPS, latlng=None, latlng type inattendu (string), et `enrich_all_weather` skip sans GPS. Verifie que `fetch_weather_for_activity` retourne False et qu'aucune ecriture DB n'a lieu. 36/36 tests passent. |
| 2026-02-07 | 2 | 2.5.3 | [x] | Ajout classe `TestHourlyInterpolation` dans `test_weather_service.py` : 11 tests couvrant activite avant/apres toutes les heures, ecarts asymetriques (09:10→09:00, 09:50→10:00), target avec timezone, journee complete 24h, _build_weather_from_response avec verification des donnees a l'index interpole, et test bout-en-bout fetch_weather_for_activity. 46/46 tests passent. |
| 2026-02-07 | 3 | 3.1.1 | [x] | Cree `garmin_auth.py` : GarminAuthManager avec login(email, password) via garth.Client, serialisation token avec dumps(), restauration avec get_client(encrypted_token) via loads(), encrypt_token/decrypt_token (Fernet, meme pattern que strava_oauth.py). Email/password jamais stockes. Ajout `garth>=0.4.0` dans requirements.txt. Import + roundtrip chiffrement verifies OK. |
| 2026-02-07 | 3 | 3.1.2 | [x] | Ajout modele `GarminAuth` dans `user.py` : id PK, user_id unique FK indexe, garmin_display_name (Optional), oauth_token_encrypted, token_created_at, last_sync_at (Optional), created_at, updated_at. Schema `GarminAuthRead` (sans token). Relation `user.garmin_auth` ajoutee dans User. Imports ajoutes dans `__init__.py`. 87/87 tests passent. |
| 2026-02-07 | 3 | 3.1.3 | [x] | Verification design one-time login : `login()` prend email/password en params locaux, appelle `garth.Client().login()`, serialise via `dumps()`, chiffre via Fernet, retourne le token. Identifiants jamais stockes (ni en attribut, ni en DB). `get_client()` reconstruit via `loads()` sans re-login. Modele `GarminAuth` n'a aucun champ email/password. Grep confirme zero reference a un stockage de credentials Garmin dans le codebase. |
| 2026-02-07 | 3 | 3.2.1 | [x] | Cree `garmin_daily.py` : modele GarminDaily (17 cols : id PK, user_id FK indexe, date indexe, training_readiness, hrv_rmssd, sleep_score, sleep_duration_min, resting_hr, stress_score, spo2, vo2max_estimated, weight_kg, body_battery_max, body_battery_min, training_status, created_at, updated_at). Contrainte unique `uq_garmin_daily_user_date` (user_id, date). Schema `GarminDailyRead`. Import + contraintes verifies OK. 87/87 tests passent. |
| 2026-02-07 | 3 | 3.2.2 | [x] | Cree migration `d5f6a7b8c9e0_add_garmin_tables.py` : table `garminauth` (8 cols : id PK, user_id unique+indexe FK user, garmin_display_name, oauth_token_encrypted, token_created_at, last_sync_at, created_at, updated_at) et table `garmindaily` (17 cols : id PK, user_id FK indexe, date indexe, training_readiness, hrv_rmssd, sleep_score, sleep_duration_min, resting_hr, stress_score, spo2, vo2max_estimated, weight_kg, body_battery_max/min, training_status, created_at, updated_at). Contrainte unique (user_id, date) sur garmindaily. down_revision = c4e5f6a7b8d9. 185 tests passent. |
| 2026-02-07 | 3 | 3.2.3 | [x] | Ajout import GarminDaily, GarminDailyRead dans `__init__.py` + `__all__`. Ajout imports GarminAuth (depuis user.py) et GarminDaily (depuis garmin_daily.py) dans `env.py`. GarminAuth/GarminAuthRead etaient deja dans `__init__.py` (ajoutes lors de 3.1.2). 87/87 tests passent. |
| 2026-02-07 | 3 | 3.3.1 | [x] | Cree `garmin_sync_service.py` : `sync_daily_data(session, user_id, days_back=30)` async. Boucle sur chaque date, appelle 8 endpoints garth (TrainingReadinessData, HRVData, SleepData, DailyHeartRate, DailyBodyBatteryStress, DailySummary fallback SpO2, WeightData, GarminScoresData) + DailyTrainingStatus via stats. Upsert SQLModel (select+update ou insert). Delai 500ms entre dates. Champs manquants → NULL. last_sync_at mis a jour. 185 tests existants passent. |
| 2026-02-07 | 3 | 3.3.2 | [x] | Ajout 3 methodes Garmin dans `auth_service.py` : `handle_garmin_login()` (login one-time via garmin_auth, upsert GarminAuth en DB), `get_garmin_status()` (retourne connected/display_name/token_created_at/last_sync_at), `disconnect_garmin()` (supprime GarminAuth, raise ValueError si pas connecte). Import garmin_auth + GarminAuth ajoutes. Pattern identique aux methodes Strava/Google existantes. 87/87 tests passent. |
| 2026-02-07 | 3 | 3.4.1 | [x] | Cree `garmin_router.py` : 5 routes (POST /auth/garmin/login rate-limit 3/h, GET /auth/garmin/status, DELETE /auth/garmin/disconnect, POST /sync/garmin?days_back, GET /garmin/daily?date_from&date_to). Pattern identique aux autres routers (security, get_session, get_current_user_id). GarminLoginRequest via Pydantic BaseModel+EmailStr. Delegation auth_service + garmin_sync_service. 87/87 tests passent. |
| 2026-02-07 | 3 | 3.4.2 | [x] | Ajout import + include de garmin_router dans `__init__.py`. 58 routes totales enregistrees. 185/185 tests unitaires passent (echecs pre-existants sur tests d'integration Strava/Activities non lies). |
| 2026-02-07 | 3 | 3.4.3 | [x] | Ajout `garminconnect>=0.2.0` dans `requirements.txt` (section HTTP Client & OAuth, apres garth). |
| 2026-02-07 | 3 | 3.5.1 | [x] | Cree `GarminConnect.tsx` : page complete avec 2 etats (non connecte / connecte). Non connecte : formulaire email+password, notice securite "identifiants non stockes". Connecte : status card (display_name, last_sync), selecteur days_back (7/14/30/60/90j), bouton sync, apercu 7 derniers jours (table HRV/Training Readiness/Sleep avec code couleur), bouton deconnexion. Appels API inline (garminApi) en attendant garminService.ts (3.5.2). Pattern identique aux pages Strava/Google existantes (react-query, useMutation, lucide-react, useToast). Build Vite OK, aucune erreur TS nouvelle. |
| 2026-02-07 | 3 | 3.5.2 | [x] | Cree `garminService.ts` : 5 fonctions (loginGarmin, getGarminStatus, disconnectGarmin, syncGarminDaily, getGarminDaily). Types exportes GarminStatus et GarminDailyEntry. Mis a jour `GarminConnect.tsx` pour utiliser le service au lieu des appels API inline (suppression axios import + garminApi inline). Build Vite OK. |
| 2026-02-07 | 3 | 3.5.3 | [x] | Ajout route `/garmin-connect` dans `App.tsx` (React.lazy import de GarminConnect) + route protegee avec Layout. Ajout lien "Connexion Garmin" avec icone Watch dans la navigation de `Layout.tsx`. Build Vite OK, chunk GarminConnect genere en lazy-loading. |
| 2026-02-07 | 3 | 3.6.1 | [x] | Cree `tests/test_garmin_sync_service.py` : 23 tests avec mock garth API responses. Couvre _fetch_day (12 tests : toutes donnees, aucune donnee, donnees partielles, preference TR morning, single TR, SpO2 fallback summary, SpO2 priorite sleep, conversion poids g→kg, conversion sommeil s→min, exceptions API graceful, toutes exceptions→None, training_status fallback), _upsert (2 tests : insert + update), sync_daily_data (5 tests : sync reussie 3j, erreurs certains jours, jours sans data skip upsert, no auth→ValueError, last_sync_at mis a jour), HRV edge cases (2 tests : no summary, no avg), Sleep edge cases (2 tests : no DTO, score direct int). 23/23 passent, 110/110 total avec segmentation+weather. |
| 2026-02-07 | 3 | 3.6.2 | [x] | Cree `tests/test_garmin_auth_roundtrip.py` : 12 tests roundtrip token Garth. 3 classes : TestEncryptDecryptRoundtrip (4 tests : string simple, JSON token, unicode, IV aleatoire distinct), TestFullGarthRoundtrip (2 tests : login→encrypt→get_client avec mock garth.Client verifie loads() appele avec token original, dumps preservee apres encryption), TestRoundtripErrors (6 tests : mauvaise cle→400, token vide encrypt/decrypt→400, garbage→400, no encryption key→500, loads failure→401). 12/12 passent. |
| 2026-02-07 | 3 | 3.6.3 | [x] | Ajout classe `TestSyncMissingFields` dans `test_garmin_sync_service.py` : 6 tests couvrant upsert partiel (resting_hr seul → 11 champs NULL), upsert sommeil seul, update qui preserve les anciens champs, _fetch_day montre pas portee (seulement stress+weight), bout-en-bout fetch→upsert champs manquants=NULL, et sync 3 jours (complet/partiel/vide) verifiant days_synced et contenu de l'upsert. 29/29 tests passent. |
| 2026-02-07 | 3 | 3.6.4 | [x] | Verifie `tests/test_garmin_rate_limit.py` : 5 tests couvrant rate limit 3/hour sur POST /auth/garmin/login. Tests : 3 premieres requetes→200, 4e→429, body 429 contient message, pattern 200x3+429x2 sur 5 requetes, rate limit login n'affecte pas GET /auth/garmin/status. 5/5 passent. |
| 2026-02-07 | 3 | 3.6.5 | [x] | Cree `tests/GarminConnect.test.tsx` : 20 tests couvrant formulaire login (affichage, notice securite, bouton desactive si champs vides, active si remplis, appel loginGarmin, loading state), status display (connecte/non connecte, display_name, selecteur days_back, bouton sync, apercu 7j avec valeurs HRV/TR/Sleep, tirets pour NULL, code couleur readiness, bouton deconnexion), donnees vides (message aucune donnee), section info securite. 20/20 passent. |
| 2026-02-07 | 4 | 4.1.1 | [x] | Cree `training_load.py` : modele TrainingLoad (9 cols : id PK, user_id FK indexe, date indexe, ctl_42d, atl_7d, tsb, rhr_delta_7d, created_at, updated_at). Contrainte unique `uq_training_load_user_date` (user_id, date). Schema `TrainingLoadRead`. Import + contraintes verifies OK. 227/227 tests passent (echecs pre-existants non lies). |
| 2026-02-07 | 4 | 4.1.2 | [x] | Cree migration `e6a7b8c9d0f1_add_training_load.py` : table `trainingload` (9 cols : id PK, user_id FK indexe, date indexe, ctl_42d, atl_7d, tsb, rhr_delta_7d, created_at, updated_at). Contrainte unique `uq_training_load_user_date` (user_id, date). down_revision = d5f6a7b8c9e0. 133 tests unitaires passent. |
| 2026-02-07 | 4 | 4.1.3 | [x] | Ajout imports TrainingLoad, TrainingLoadRead dans `__init__.py` + `__all__`. Ajout import TrainingLoad dans `env.py`. Import verifie OK (`python -c "from app.domain.entities import TrainingLoad, TrainingLoadRead"`). 133/133 tests unitaires passent. |
| 2026-02-07 | 4 | 4.2.1 | [x] | Cree `derived_features_service.py` : Axe A per-segment (minetti_cost via polynome Minetti, grade_variability stdev glissante 5 segs, efficiency_factor pace/HR, cardiac_drift ratio HR/pace 1ere vs 2eme moitie, cadence_decay ratio cadence 1ere vs 2eme moitie) + compute_segment_features() et compute_all_segment_features(). Axe B per-day (compute_trimp simplifie/normalise, compute_training_load avec EWMA CTL 42j + ATL 7j + TSB, rhr_delta_7d via GarminDaily). 37 tests unitaires passent (Minetti valeurs connues, grade_variability plat/variable, cardiac_drift positif/constant/insuffisant, cadence_decay, efficiency_factor, TRIMP, CTL/ATL convergence 60j, TSB positif apres repos/negatif pendant effort, RHR delta). 165/165 tests totaux OK. |
| 2026-02-07 | 4 | 4.3.1 | [x] | Verification : `minetti_cost()` deja implementee dans `derived_features_service.py` (lignes 34-47) lors de la tache 4.2.1. Polynome C(i) = 155.4*i^5 - 30.4*i^4 - 43.3*i^3 + 46.3*i^2 + 19.5*i + 3.6. Utilisee dans `compute_segment_features()` avec conversion grade %→fraction. 6 tests unitaires (TestMinettiCost) passent : grade 0→3.6, grade negatif, minimum ~-0.18, grades positifs croissants, descente forte positive, valeur exacte. |
| 2026-02-07 | 4 | 4.3.2 | [x] | Verification : formule CTL deja implementee dans `derived_features_service.py` (ligne 353) lors de la tache 4.2.1. `ctl = ctl * (1 - 1/CTL_DAYS) + trimp * (1/CTL_DAYS)` avec `CTL_DAYS = 42`. 5 tests unitaires (TestCtlAtlConvergence) couvrent convergence 60j, comparaison ATL/CTL, TSB positif apres repos, TSB negatif sous effort, decroissance sans entrainement. 165/165 tests passent. |
| 2026-02-07 | 4 | 4.3.3 | [x] | Verification : formule ATL deja implementee dans `derived_features_service.py` (ligne 354) lors de la tache 4.2.1. `atl = atl * (1 - 1/ATL_DAYS) + trimp * (1/ATL_DAYS)` avec `ATL_DAYS = 7`. 5 tests unitaires (TestCtlAtlConvergence) couvrent convergence ATL vs CTL, TSB positif apres repos, TSB negatif sous effort, decroissance sans entrainement. 37/37 tests passent. |
| 2026-02-07 | 4 | 4.3.4 | [x] | Verification : `tsb = ctl - atl` deja implementee dans `derived_features_service.py` (ligne 355) lors de la tache 4.2.1. Valeur stockee arrondie dans TrainingLoad (lignes 370/379). 2 tests unitaires (TestCtlAtlConvergence) couvrent TSB positif apres repos et TSB negatif sous effort intense. 165/165 tests passent. |
| 2026-02-07 | 4 | 4.4.1 | [x] | Ajout 4 routes dans `segment_router.py` : POST /features/compute (compute_all_segment_features), POST /features/compute/{activity_id} (compute_segment_features avec verif ownership), GET /training-load (query TrainingLoad avec filtres date_from/date_to optionnels), POST /training-load/compute (compute_training_load, defaut 90j). Imports TrainingLoad, TrainingLoadRead, derived_features_service ajoutes. 11 routes totales dans le router. 124/124 tests unitaires passent. |
| 2026-02-07 | 4 | 4.5.1 | [x] | Ajout 9 tests dans `TestMinettiCost` : grade 0→3.6 exact (1e-6), grade -0.10→2.15, grade -0.20→1.80, grade +0.10→5.97, grade +0.20→9.01, minimum ~1.78 a grade ~-0.181, minimum a pente negative (pas a 0), symetrie montee>descente, cout positif sur [-0.45, +0.45]. 15/15 tests Minetti passent, 46/46 total. |
| 2026-02-07 | 4 | 4.5.2 | [x] | Ajout 17 tests TRIMP dans `test_derived_features_service.py` : 11 dans TestTrimp (easy run 45min, tempo 30min, long run 90min, interval 40min, ordering par intensite, proportionnalite duree/HR, HR negatif→None, duree 0→0, max_hr 0→fallback simplifie) + 6 dans TestGetDailyTrimp (single activity, 2 activities somme, no activities→0, sans HR→0, mix HR+no HR, sans max_hr→simplifie). 62/62 tests passent. |
| 2026-02-07 | 4 | 4.5.3 | [x] | Ajout classe `TestComputeTrainingLoad60Days` dans `test_derived_features_service.py` : 8 tests bout-en-bout de `compute_training_load()` avec mocks `_get_daily_trimp`/`_get_rhr_delta_7d`. Couvre : TRIMP constant 60j CTL converge >75% (verifie valeur EWMA exacte), ATL quasi-converge ~100, ATL converge plus vite que CTL a 14j, 30j entrainement + 30j repos → TSB positif, bloc intensif 7j → TSB negatif, 60 jours stockes avec TSB ≈ CTL - ATL (tolerance arrondi), TRIMP croissant → CTL monotone croissant, 0 TRIMP → CTL/ATL/TSB restent a 0. 70/70 tests passent. |
| 2026-02-07 | 4 | 4.5.4 | [x] | Ajout classe `TestCardiacDriftMockHR` dans `test_derived_features_service.py` : 8 tests avec mock HR croissant. Couvre : HR lineaire croissant a pace constant (drift exact verifie = 154/144-1), forte montee HR (>10% drift), HR+pace qui ralentit (drift negatif car pace augmente plus vite), HR+pace qui accelere (negative split), seuil minimum 4 segments (valeur exacte), 3 valides parmi 4 → None, proportionnalite drift/HR_delta, marathon 20 segments pace constant. 78/78 tests passent. |
| 2026-02-07 | 5 | 5.1.1 | [x] | Ajout `fitparse>=0.0.14` dans `requirements.txt` (section Data Processing, ligne 43). |
| 2026-02-07 | 5 | 5.1.2 | [x] | Ajout `download_fit_file(client, garmin_activity_id)` et `parse_fit_file(fit_bytes)` dans `garmin_sync_service.py`. Download via `client.download("/download-service/files/activity/{id}")`. Parsing via fitparse : Running Dynamics (stance_time→ground_contact_time_avg, vertical_oscillation→vertical_oscillation_avg, stance_time_balance→stance_time_balance_avg), puissance (power→power_avg), Training Effect (total_training_effect→aerobic, total_anaerobic_training_effect→anaerobic) depuis messages session. Moyennes calculees sur les records, arrondies. 29/29 tests existants passent. |
| 2026-02-07 | 5 | 5.2.1 | [x] | Cree `tests/test_fit_parsing.py` : 15 tests avec mock fitparse (sys.modules). 7 classes : TestParseFitFileComplete (1 test : full Running Dynamics + power + TE, moyennes verifiees), TestParseFitFilePartial (3 tests : only power, only RD, mixed records avec champs intermittents), TestParseFitFileEmpty (2 tests : no records/session, all None values), TestParseFitFileSession (3 tests : only aerobic TE, no TE, multiple sessions uses first), TestParseFitFileRounding (1 test : arrondis GCT 1 dec, VO 2 dec, balance 2 dec, power 1 dec, TE 1 dec), TestParseFitFileLongRun (1 test : 20 records progressifs, moyennes exactes), TestDownloadFitFile (4 tests : success, empty bytes, None, exception). 15/15 passent. |
| 2026-02-08 | — | Garmin Activities + FIT | [x] | Integration activites Garmin + FIT streams. Phase 1: ActivitySource enum + source/garmin_activity_id dans Activity, modele FitMetrics (1:1 avec Activity), migration `f7b8c9d0e1f2`. Phase 2: sync_garmin_activities() + _map_garmin_activity() + _deduplicate_activity() (fuzzy match Strava). Phase 3: parse_fit_file_streams() (conversion semicircles→degrees, format compatible segmentation) + enrich_garmin_activity_fit() + batch_enrich_garmin_fit(). Phase 4: 4 routes API (POST sync/garmin/activities, POST/batch enrich-fit, GET fit-metrics). Phase 5: branche Garmin dans auto_enrichment_service (_enrich_single_activity). Phase 6: garminService.ts (syncGarminActivities, enrichGarminFit, batchEnrichGarminFit, getActivityFitMetrics + types FitMetrics), GarminConnect.tsx (section activites avec boutons sync + enrichir FIT). Phase 7: 23 tests activity sync (mapping, dedup, sync) + 20 tests FIT streams (semicircles, indoor, segmentation-compatible). 264/264 tests unitaires passent. Build Vite OK. |
| _A remplir au fur et a mesure_ | | | | |
