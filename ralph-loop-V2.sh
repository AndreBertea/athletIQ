#!/bin/bash
# ralph-loop-V2.sh — Boucle d iteration automatique pour athletIQ
# Pipeline d'Acquisition de Donnees (DATA_AQI_PLAN.md)
# Compatible bash 3.2+ (macOS default)
#
# Usage :
#   ./ralph-loop-V2.sh                  # Lance depuis la vague 1
#   ./ralph-loop-V2.sh --from-wave 4    # Reprend a la vague 4
#   ./ralph-loop-V2.sh --dry-run        # Affiche le plan sans executer
#   ./ralph-loop-V2.sh --max-retries 5  # Nombre max de tentatives par tache
#   ./ralph-loop-V2.sh --auto           # Mode 100% automatique (pas de pause entre vagues)

set -uo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────

PROJECT_DIR="/Users/andrebertea/Projects/athletIQ"
PLAN_FILE="$PROJECT_DIR/DATA_AQI_PLAN.md"
GUIDE_FILE="$PROJECT_DIR/PLAN_GUIDE_AQUI.md"
LOG_DIR="$PROJECT_DIR/.ralph-logs"
LOG_FILE="$LOG_DIR/ralph-v2-$(date '+%Y%m%d-%H%M%S').log"
PROMPT_FILE="$LOG_DIR/.current-prompt-v2.txt"
MAX_RETRIES=3
MAX_TURNS=30
START_WAVE=1
DRY_RUN=false
AUTO_MODE=false

# ─── Couleurs ────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ─── Parsing arguments ──────────────────────────────────────────────────────

while [ $# -gt 0 ]; do
    case $1 in
        --from-wave)  START_WAVE="$2"; shift 2 ;;
        --dry-run)    DRY_RUN=true; shift ;;
        --auto)       AUTO_MODE=true; shift ;;
        --max-retries) MAX_RETRIES="$2"; shift 2 ;;
        --max-turns)  MAX_TURNS="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: ./ralph-loop-V2.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --from-wave N     Reprendre a la vague N (defaut: 1)"
            echo "  --dry-run         Afficher le plan sans executer"
            echo "  --auto            Mode 100% automatique (pas de pause entre vagues)"
            echo "  --max-retries N   Tentatives max par tache (defaut: 3)"
            echo "  --max-turns N     Tours max par appel claude (defaut: 30)"
            echo "  -h, --help        Afficher cette aide"
            echo ""
            echo "Vagues :"
            echo "  1  Etape 1 - Segmentation : modeles + migration"
            echo "  2  Etape 1 - Segmentation : service + routes + tests"
            echo "  3  Etape 2 - Meteo : complet"
            echo "  4  Etape 3 - Garmin : backend (auth + modeles + service + routes)"
            echo "  5  Etape 3 - Garmin : frontend + tests"
            echo "  6  Etape 4 - Features derivees : complet"
            echo "  7  Etape 5 - FIT files (optionnel)"
            exit 0
            ;;
        *) echo "Option inconnue: $1"; exit 1 ;;
    esac
done

# ─── Fonctions utilitaires ──────────────────────────────────────────────────

mkdir -p "$LOG_DIR"

log() {
    local msg
    msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo -e "$msg" | tee -a "$LOG_FILE"
}

separator() {
    echo -e "${DIM}───────────────────────────────────────────────────────────${NC}" | tee -a "$LOG_FILE"
}

check_task_done() {
    local task_id="$1"
    grep -qE "\[x\].*\*\*${task_id}\*\*" "$PLAN_FILE" 2>/dev/null
}

check_task_in_progress() {
    local task_id="$1"
    grep -qE "\[~\].*\*\*${task_id}\*\*" "$PLAN_FILE" 2>/dev/null
}

count_done() {
    local n
    n=$(grep -cE "\[x\].*\*\*[0-9]+\.[0-9]+\.[0-9]+\*\*" "$PLAN_FILE" 2>/dev/null) || true
    printf "%d" "${n:-0}"
}

count_total() {
    local n
    n=$(grep -cE "\[[ x~]\].*\*\*[0-9]+\.[0-9]+\.[0-9]+\*\*" "$PLAN_FILE" 2>/dev/null) || true
    printf "%d" "${n:-0}"
}

progress_bar() {
    local done_n
    local total_n
    done_n=$(count_done)
    total_n=$(count_total)
    if [ "$total_n" -eq 0 ]; then
        echo "0/0"
        return
    fi
    local pct=$((done_n * 100 / total_n))
    local filled=$((pct / 5))
    local empty=$((20 - filled))
    local bar=""
    local i=0
    while [ "$i" -lt "$filled" ]; do bar="${bar}█"; i=$((i + 1)); done
    i=0
    while [ "$i" -lt "$empty" ]; do bar="${bar}░"; i=$((i + 1)); done
    echo "${bar} ${done_n}/${total_n} (${pct}%)"
}

# ─── Execution d une tache AGENT ─────────────────────────────────────────────

run_agent_task() {
    local task_id="$1"
    local description="$2"

    if check_task_done "$task_id"; then
        log "${GREEN}  [OK] $task_id deja termine${NC}"
        return 0
    fi

    if $DRY_RUN; then
        log "${CYAN}  [DRY] AGENT  $task_id -- $description${NC}"
        return 0
    fi

    log "${BLUE}  [>>] AGENT  $task_id -- $description${NC}"

    local attempt=1
    while [ "$attempt" -le "$MAX_RETRIES" ]; do
        log "${DIM}       tentative $attempt/$MAX_RETRIES${NC}"

        local task_log="$LOG_DIR/task-${task_id}-attempt${attempt}.log"

        # Ecrire le prompt dans un fichier temporaire
        cat > "$PROMPT_FILE" <<EOF
Tu travailles sur le projet athletIQ ($PROJECT_DIR).

== CONTEXTE ==
Lis DATA_AQI_PLAN.md et PLAN_GUIDE_AQUI.md pour comprendre le pipeline de donnees.
Lis aussi CLAUDE.md pour les regles generales du projet.

== TA TACHE UNIQUE ==
Tache **${task_id}** : ${description}

== REGLES ==
1. Ne travaille QUE sur cette tache, rien d autre.
2. Ecris du code propre, minimal, sans sur-ingenierie.
3. Verifie que ca fonctionne (lance les tests si pertinent).
4. Une fois termine, mets a jour DATA_AQI_PLAN.md :
   - Change [ ] en [x] pour la tache ${task_id}
   - Ajoute une ligne dans le Journal des modifications
5. Si tu es bloque, marque la tache [~] et explique pourquoi dans le journal.

Commence maintenant.
EOF

        local prompt_content
        prompt_content=$(cat "$PROMPT_FILE")

        claude -p "$prompt_content" \
            --dangerously-skip-permissions \
            --max-turns "$MAX_TURNS" \
            2>&1 | tee -a "$task_log" "$LOG_FILE"

        if check_task_done "$task_id"; then
            log "${GREEN}  [OK] $task_id termine !${NC}"
            return 0
        fi

        # Verifier si marque en cours (bloque)
        if check_task_in_progress "$task_id"; then
            log "${YELLOW}  [~~] $task_id marque en cours/bloque — intervention humaine potentielle${NC}"
            return 2
        fi

        log "${YELLOW}  [!!] $task_id pas valide apres tentative $attempt${NC}"
        if [ -s "$task_log" ]; then
            tail -5 "$task_log" | while IFS= read -r line; do
                log "${DIM}       | $line${NC}"
            done
        fi
        attempt=$((attempt + 1))
        sleep 2
    done

    log "${RED}  [XX] $task_id ECHEC apres $MAX_RETRIES tentatives${NC}"
    return 1
}

# ─── Gestion des pauses humaines ─────────────────────────────────────────────

# Appelee quand une tache est bloquee ([~]) ou echoue apres max retries.
# La loop s arrete et signale a l humain qu il doit intervenir.
handle_human_needed() {
    local task_id="$1"
    local description="$2"
    local reason="$3"

    echo ""
    echo -e "${MAGENTA}  ╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${MAGENTA}  ║  INTERVENTION HUMAINE REQUISE                           ║${NC}"
    echo -e "${MAGENTA}  ╠══════════════════════════════════════════════════════════╣${NC}"
    echo -e "${MAGENTA}  ║  Tache : $task_id${NC}"
    echo -e "${MAGENTA}  ║  $description${NC}"
    echo -e "${MAGENTA}  ║  Raison : $reason${NC}"
    echo -e "${MAGENTA}  ╠══════════════════════════════════════════════════════════╣${NC}"
    echo -e "${MAGENTA}  ║  Options :                                              ║${NC}"
    echo -e "${MAGENTA}  ║    Entree = j ai corrige, relance cette tache           ║${NC}"
    echo -e "${MAGENTA}  ║    skip   = passer et continuer                         ║${NC}"
    echo -e "${MAGENTA}  ║    quit   = arreter la loop                             ║${NC}"
    echo -e "${MAGENTA}  ╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""

    read -rp "  > " response
    case "$response" in
        skip) return 1 ;;
        quit) return 99 ;;
        *)    return 0 ;;  # retry
    esac
}

# ─── Execution d une vague ───────────────────────────────────────────────────

run_wave() {
    local wave_num="$1"
    local wave_label="$2"
    shift 2
    local failed=0
    local human_stop=false

    echo ""
    log "${BOLD}${CYAN}========== VAGUE $wave_num — $wave_label ==========${NC}"
    log "${DIM}  Progression globale : $(progress_bar)${NC}"
    separator

    while [ $# -gt 0 ]; do
        local entry="$1"
        shift

        local task_id="${entry%%|*}"
        local description="${entry#*|}"

        run_agent_task "$task_id" "$description"
        local rc=$?

        if [ $rc -eq 2 ]; then
            # Tache bloquee — besoin humain
            handle_human_needed "$task_id" "$description" "Tache marquee [~] (bloquee par l agent)"
            local human_rc=$?
            if [ $human_rc -eq 99 ]; then
                return 1
            elif [ $human_rc -eq 0 ]; then
                # Retry : re-ajouter la tache (en relancant run_agent_task)
                run_agent_task "$task_id" "$description"
                local retry_rc=$?
                if [ $retry_rc -ne 0 ]; then
                    failed=$((failed + 1))
                fi
            else
                failed=$((failed + 1))
            fi
        elif [ $rc -eq 1 ]; then
            # Echec apres max retries — besoin humain
            handle_human_needed "$task_id" "$description" "Echec apres $MAX_RETRIES tentatives"
            local human_rc=$?
            if [ $human_rc -eq 99 ]; then
                return 1
            elif [ $human_rc -eq 0 ]; then
                run_agent_task "$task_id" "$description"
                local retry_rc=$?
                if [ $retry_rc -ne 0 ]; then
                    failed=$((failed + 1))
                fi
            else
                failed=$((failed + 1))
            fi
        fi
    done

    separator
    log "${BOLD}Vague $wave_num terminee ($failed echec(s))${NC}"
    log "${DIM}  Progression globale : $(progress_bar)${NC}"
    return 0
}

# ═══════════════════════════════════════════════════════════════════════════════
# DEFINITION DES VAGUES (extraites de PLAN_GUIDE_AQUI.md)
# Format : "TASK_ID|DESCRIPTION"
# Toutes les taches sont AGENT — la loop detecte automatiquement
# quand l intervention humaine est necessaire (echec ou blocage).
# ═══════════════════════════════════════════════════════════════════════════════

run_all_waves() {
    local current_wave=0

    # ── VAGUE 1 : Etape 1 — Segmentation : modeles + migration ───────────

    current_wave=1
    if [ "$START_WAVE" -le "$current_wave" ]; then
        run_wave 1 "Segmentation — Modeles + Migration" \
            "1.1.1|Creer modele Segment dans backend/app/domain/entities/segment.py (activity_id, user_id, segment_index, distance_m, elapsed_time_s, avg_grade_percent, elevation_gain/loss_m, altitude_m, avg_hr, avg_cadence, lat, lon, pace_min_per_km)" \
            "1.1.2|Creer modele SegmentFeatures dans backend/app/domain/entities/segment_features.py (segment_id, activity_id, cumulative_distance_km, elapsed_time_min, cumulative_elev_gain/loss_m, race_completion_pct, intensity_proxy, + champs Minetti/drift/cadence_decay a remplir plus tard)" \
            "1.1.3|Generer la migration Alembic add_segment_tables pour les tables segment et segment_features" \
            "1.1.4|Ajouter les imports Segment et SegmentFeatures dans backend/app/domain/entities/__init__.py et backend/alembic/env.py"

        if [ $? -ne 0 ]; then return 1; fi
        if ! $DRY_RUN && ! $AUTO_MODE; then
            echo ""
            log "${BOLD}Vague 1 OK. Continuer vers la vague 2 ?${NC}"
            read -rp "  > Entree=continuer, q=quitter : " resp
            if [ "$resp" = "q" ]; then return 0; fi
        fi
    fi

    # ── VAGUE 2 : Etape 1 — Segmentation : service + routes + tests ──────

    current_wave=2
    if [ "$START_WAVE" -le "$current_wave" ]; then
        run_wave 2 "Segmentation — Service + Routes + Tests" \
            "1.2.1|Creer backend/app/domain/services/segmentation_service.py avec methodes segment_activity(), segment_all_enriched(), is_activity_segmented(). Parcourir distance.data du stream, couper un segment a chaque 100m, moyenner HR/cadence/grade_smooth, sommer elevation, midpoint GPS" \
            "1.2.2|Dans segmentation_service.py, implementer la logique de decoupage : a chaque franchissement de 100m dans distance.data, couper un segment" \
            "1.2.3|Gerer le bug connu streams_data = la chaine 'null' (string) — traiter comme None dans segmentation_service.py" \
            "1.2.4|Calculer pace_min_per_km = (elapsed_time_s / 60) / (distance_m / 1000) — c est la variable cible des futurs modeles" \
            "1.3.1|Creer backend/app/api/routers/segment_router.py avec routes POST /segments/process, POST /segments/process/{activity_id}, GET /segments/{activity_id}, GET /segments/status" \
            "1.3.2|Inclure segment_router dans backend/app/api/routers/__init__.py" \
            "1.4.1|Dans auto_enrichment_service.py, apres enrichissement Strava appeler segmentation_service.segment_activity() dans un try/except non-bloquant" \
            "1.5.1|Creer des tests pytest avec mock streams_data (5-10 points GPS) pour le segmentation_service" \
            "1.5.2|Verifier dans les tests que race_completion_pct va de 0 a environ 100" \
            "1.5.3|Verifier dans les tests que le nombre de segments est approximativement egal a distance_totale / 100"

        if [ $? -ne 0 ]; then return 1; fi
        if ! $DRY_RUN && ! $AUTO_MODE; then
            echo ""
            log "${BOLD}Vague 2 OK. Continuer vers la vague 3 ?${NC}"
            read -rp "  > Entree=continuer, q=quitter : " resp
            if [ "$resp" = "q" ]; then return 0; fi
        fi
    fi

    # ── VAGUE 3 : Etape 2 — Meteo complet ────────────────────────────────

    current_wave=3
    if [ "$START_WAVE" -le "$current_wave" ]; then
        run_wave 3 "Meteo — Complet" \
            "2.1.1|Creer modele ActivityWeather dans backend/app/domain/entities/activity_weather.py (activity_id unique, temperature_c, humidity_pct, wind_speed_kmh, wind_direction_deg, pressure_hpa, precipitation_mm, cloud_cover_pct, weather_code)" \
            "2.1.2|Generer la migration Alembic add_activity_weather" \
            "2.1.3|Ajouter les imports ActivityWeather dans backend/app/domain/entities/__init__.py et backend/alembic/env.py" \
            "2.2.1|Creer backend/app/domain/services/weather_service.py — extraire lat/lon du 1er point GPS dans streams_data, appeler Open-Meteo Historical API, trouver heure la plus proche du start_date" \
            "2.2.2|Dans weather_service.py, utiliser Historical API (archive-api.open-meteo.com) si activite > 5 jours, Forecast API (api.open-meteo.com) sinon" \
            "2.2.3|Dans weather_service.py, ajouter un delai de 100ms entre les appels API Open-Meteo" \
            "2.2.4|Dans weather_service.py, implementer les methodes fetch_weather_for_activity(), enrich_all_weather(), is_weather_fetched()" \
            "2.3.1|Ajouter dans segment_router.py les routes GET /weather/{activity_id}, POST /weather/enrich, GET /weather/status" \
            "2.4.1|Dans auto_enrichment_service.py, apres segmentation appeler weather_service.fetch_weather_for_activity() dans un try/except non-bloquant" \
            "2.5.1|Creer des tests pytest avec mock HTTP response Open-Meteo pour le weather_service" \
            "2.5.2|Tester le fallback si pas de GPS (activite sans coordonnees)" \
            "2.5.3|Verifier dans les tests que l interpolation horaire est correcte"

        if [ $? -ne 0 ]; then return 1; fi
        if ! $DRY_RUN && ! $AUTO_MODE; then
            echo ""
            log "${BOLD}Vague 3 OK. Continuer vers la vague 4 ?${NC}"
            read -rp "  > Entree=continuer, q=quitter : " resp
            if [ "$resp" = "q" ]; then return 0; fi
        fi
    fi

    # ── VAGUE 4 : Etape 3 — Garmin backend ───────────────────────────────

    current_wave=4
    if [ "$START_WAVE" -le "$current_wave" ]; then
        run_wave 4 "Garmin — Backend (Auth + Modeles + Service + Routes)" \
            "3.1.1|Creer backend/app/auth/garmin_auth.py — GarminAuthManager avec login(email, password) qui serialise le token Garth, get_client(encrypted_token), encrypt_token/decrypt_token (Fernet, meme pattern que strava_oauth.py). Email et mot de passe ne sont JAMAIS stockes." \
            "3.1.2|Ajouter GarminAuth dans backend/app/domain/entities/user.py (user_id unique FK, garmin_display_name, oauth_token_encrypted, token_created_at, last_sync_at, created_at, updated_at) + relation user.garmin_auth" \
            "3.1.3|Le flow auth Garmin doit etre one-time : user saisit email/password, backend appelle Garmin().login(), serialise le token Garth, le chiffre avec Fernet, et stocke dans GarminAuth. Jamais de re-login." \
            "3.2.1|Creer modele GarminDaily dans backend/app/domain/entities/garmin_daily.py (user_id, date, training_readiness, hrv_rmssd, sleep_score, sleep_duration_min, resting_hr, stress_score, spo2, vo2max_estimated, weight_kg, body_battery_max/min, training_status). Contrainte unique (user_id, date)." \
            "3.2.2|Generer la migration Alembic add_garmin_tables pour GarminAuth et GarminDaily" \
            "3.2.3|Ajouter les imports GarminAuth et GarminDaily dans backend/app/domain/entities/__init__.py et backend/alembic/env.py" \
            "3.3.1|Creer backend/app/domain/services/garmin_sync_service.py — sync_daily_data(session, user_id, days_back=30) : boucle sur chaque date, appelle les endpoints Garmin (training_readiness, hrv, sleep, rhr, stress, spo2, body_composition, body_battery), upsert dans garmin_daily. Delai 500ms entre dates." \
            "3.3.2|Ajouter handle_garmin_login(), get_garmin_status(), disconnect_garmin() dans backend/app/domain/services/auth_service.py" \
            "3.4.1|Creer backend/app/api/routers/garmin_router.py avec routes POST /auth/garmin/login (rate limit 3/h), GET /auth/garmin/status, DELETE /auth/garmin/disconnect, POST /sync/garmin?days_back=30, GET /garmin/daily?date_from=&date_to=" \
            "3.4.2|Inclure garmin_router dans backend/app/api/routers/__init__.py" \
            "3.4.3|Ajouter garminconnect>=0.2.0 dans backend/requirements.txt"

        if [ $? -ne 0 ]; then return 1; fi
        if ! $DRY_RUN && ! $AUTO_MODE; then
            echo ""
            log "${BOLD}Vague 4 OK. Continuer vers la vague 5 ?${NC}"
            read -rp "  > Entree=continuer, q=quitter : " resp
            if [ "$resp" = "q" ]; then return 0; fi
        fi
    fi

    # ── VAGUE 5 : Etape 3 — Garmin frontend + tests ─────────────────────

    current_wave=5
    if [ "$START_WAVE" -le "$current_wave" ]; then
        run_wave 5 "Garmin — Frontend + Tests" \
            "3.5.1|Creer frontend/src/pages/GarminConnect.tsx — si non connecte : formulaire email/password + notice 'identifiants non stockes' ; si connecte : status, bouton sync, selecteur days_back, apercu 7 derniers jours (HRV, Training Readiness, Sleep), bouton deconnexion" \
            "3.5.2|Creer frontend/src/services/garminService.ts — loginGarmin(email, password), getGarminStatus(), disconnectGarmin(), syncGarminDaily(daysBack), getGarminDaily(dateFrom?, dateTo?)" \
            "3.5.3|Ajouter route /garmin-connect dans App.tsx (React.lazy) + lien navigation Connexion Garmin dans Layout.tsx" \
            "3.6.1|Creer des tests avec mock Garmin API responses (garminconnect)" \
            "3.6.2|Tester serialisation/deserialisation token Garth roundtrip" \
            "3.6.3|Tester sync avec champs manquants (montre pas portee un jour = NULL)" \
            "3.6.4|Tester rate limit sur endpoint POST /auth/garmin/login" \
            "3.6.5|Tester frontend form GarminConnect.tsx + status display"

        if [ $? -ne 0 ]; then return 1; fi
        if ! $DRY_RUN && ! $AUTO_MODE; then
            echo ""
            log "${BOLD}Vague 5 OK. Continuer vers la vague 6 ?${NC}"
            read -rp "  > Entree=continuer, q=quitter : " resp
            if [ "$resp" = "q" ]; then return 0; fi
        fi
    fi

    # ── VAGUE 6 : Etape 4 — Features derivees complet ───────────────────

    current_wave=6
    if [ "$START_WAVE" -le "$current_wave" ]; then
        run_wave 6 "Features Derivees — Complet" \
            "4.1.1|Creer modele TrainingLoad dans backend/app/domain/entities/training_load.py (user_id, date, ctl_42d, atl_7d, tsb, rhr_delta_7d). Contrainte unique (user_id, date)." \
            "4.1.2|Generer la migration Alembic add_training_load" \
            "4.1.3|Ajouter les imports TrainingLoad dans backend/app/domain/entities/__init__.py et backend/alembic/env.py" \
            "4.2.1|Creer backend/app/domain/services/derived_features_service.py — Axe A per-segment : minetti_cost, grade_variability, efficiency_factor, cardiac_drift, cadence_decay. Axe B per-day : TRIMP, CTL (EWMA 42j), ATL (EWMA 7j), TSB = CTL - ATL, rhr_delta_7d (si Garmin dispo)." \
            "4.3.1|Dans derived_features_service.py implementer Minetti cost : C(i) = 155.4*i^5 - 30.4*i^4 - 43.3*i^3 + 46.3*i^2 + 19.5*i + 3.6 (cout metabolique J/(kg.m), grade i en fraction)" \
            "4.3.2|Dans derived_features_service.py implementer CTL : CTL_today = CTL_yesterday * (1 - 1/42) + TRIMP_today * (1/42) (EWMA 42 jours)" \
            "4.3.3|Dans derived_features_service.py implementer ATL : ATL_today = ATL_yesterday * (1 - 1/7) + TRIMP_today * (1/7) (EWMA 7 jours)" \
            "4.3.4|Dans derived_features_service.py implementer TSB = CTL - ATL (positif = frais, negatif = fatigue)" \
            "4.4.1|Ajouter dans segment_router.py les routes POST /features/compute, POST /features/compute/{activity_id}, GET /training-load?date_from=&date_to=, POST /training-load/compute" \
            "4.5.1|Tester Minetti contre valeurs connues (grade 0 → environ 3.6 J/(kg.m), grade -0.1 → minimum)" \
            "4.5.2|Tester TRIMP avec une activite connue" \
            "4.5.3|Tester CTL/ATL convergence sur 60 jours de donnees" \
            "4.5.4|Tester cardiac drift avec mock HR croissant"

        if [ $? -ne 0 ]; then return 1; fi
        if ! $DRY_RUN && ! $AUTO_MODE; then
            echo ""
            log "${BOLD}Vague 6 OK. Continuer vers la vague 7 ?${NC}"
            read -rp "  > Entree=continuer, q=quitter : " resp
            if [ "$resp" = "q" ]; then return 0; fi
        fi
    fi

    # ── VAGUE 7 : Etape 5 — FIT files (optionnel) ───────────────────────

    current_wave=7
    if [ "$START_WAVE" -le "$current_wave" ]; then
        run_wave 7 "FIT Files — Optionnel" \
            "5.1.1|Ajouter fitparse>=0.0.14 dans backend/requirements.txt" \
            "5.1.2|Dans garmin_sync_service.py ajouter download_fit_file(garmin_activity_id) et parse_fit_file(fit_bytes) pour extraire Running Dynamics (ground contact time, vertical oscillation, balance G/D), puissance estimee, Training Effect" \
            "5.2.1|Tester parsing d un fichier FIT sample"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

main() {
    echo ""
    echo -e "${BOLD}${CYAN}"
    echo "  RALPH LOOP V2 — athletIQ Data Acquisition"
    echo "  ==========================================="
    echo -e "${NC}"
    echo -e "  ${DIM}Plan    : DATA_AQI_PLAN.md${NC}"
    echo -e "  ${DIM}Guide   : PLAN_GUIDE_AQUI.md${NC}"
    echo -e "  ${DIM}Vague   : $START_WAVE | Retries : $MAX_RETRIES | Auto : $AUTO_MODE | Dry run : $DRY_RUN${NC}"
    echo ""

    # Verifier prerequisites
    if ! command -v claude >/dev/null 2>&1; then
        echo -e "${RED}Erreur : claude CLI non trouve dans le PATH${NC}"
        echo "Installe Claude Code : https://docs.anthropic.com/en/docs/claude-code"
        exit 1
    fi

    if [ ! -f "$PLAN_FILE" ]; then
        echo -e "${RED}Erreur : $PLAN_FILE introuvable${NC}"
        exit 1
    fi

    if [ ! -f "$GUIDE_FILE" ]; then
        echo -e "${YELLOW}Warning : $GUIDE_FILE introuvable (pas critique)${NC}"
    fi

    cd "$PROJECT_DIR" || exit 1

    local done_before
    done_before=$(count_done)
    log "Progression initiale : $(progress_bar)"
    separator

    # Lancer les vagues
    run_all_waves

    # Resume final
    echo ""
    separator
    local done_after
    done_after=$(count_done)
    local completed=$((done_after - done_before))

    echo -e "${BOLD}${GREEN}"
    echo "  RESUME DE LA SESSION"
    echo "  ===================="
    echo "  Taches completees cette session : $completed"
    echo "  Progression globale :             $(progress_bar)"
    echo "  Log complet :                     $LOG_FILE"
    echo -e "${NC}"
}

main "$@"
