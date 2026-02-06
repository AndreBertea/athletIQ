#!/bin/bash
# ralph-loop.sh — Boucle d iteration automatique pour athletIQ
# Compatible bash 3.2+ (macOS default)
#
# Usage :
#   ./ralph-loop.sh                  # Lance depuis la vague 1
#   ./ralph-loop.sh --from-wave 4    # Reprend a la vague 4
#   ./ralph-loop.sh --dry-run        # Affiche le plan sans executer
#   ./ralph-loop.sh --max-retries 5  # Nombre max de tentatives par tache

set -uo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────

PROJECT_DIR="/Users/andrebertea/Projects/athletIQ"
PLAN_FILE="$PROJECT_DIR/PRODUCTION_PLAN.md"
LOG_DIR="$PROJECT_DIR/.ralph-logs"
LOG_FILE="$LOG_DIR/ralph-$(date '+%Y%m%d-%H%M%S').log"
PROMPT_FILE="$LOG_DIR/.current-prompt.txt"
MAX_RETRIES=3
MAX_TURNS=30
START_WAVE=1
DRY_RUN=false

# ─── Couleurs ────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ─── Parsing arguments ──────────────────────────────────────────────────────

while [ $# -gt 0 ]; do
    case $1 in
        --from-wave)  START_WAVE="$2"; shift 2 ;;
        --dry-run)    DRY_RUN=true; shift ;;
        --max-retries) MAX_RETRIES="$2"; shift 2 ;;
        --max-turns)  MAX_TURNS="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: ./ralph-loop.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --from-wave N     Reprendre a la vague N (defaut: 1)"
            echo "  --dry-run         Afficher le plan sans executer"
            echo "  --max-retries N   Tentatives max par tache (defaut: 3)"
            echo "  --max-turns N     Tours max par appel claude (defaut: 30)"
            echo "  -h, --help        Afficher cette aide"
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

count_done() {
    local n
    n=$(grep -cE "\[x\].*\*\*[0-9]+\.[0-9]+\.[0-9]+\*\*" "$PLAN_FILE" 2>/dev/null) || true
    printf "%d" "${n:-0}"
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
        log "${CYAN}  [DRY] $task_id -- $description${NC}"
        return 0
    fi

    log "${BLUE}  [>>] $task_id -- $description${NC}"

    local attempt=1
    while [ "$attempt" -le "$MAX_RETRIES" ]; do
        log "${DIM}       tentative $attempt/$MAX_RETRIES${NC}"

        local task_log="$LOG_DIR/task-${task_id}-attempt${attempt}.log"

        # Ecrire le prompt dans un fichier temporaire (evite les heredocs imbriques)
        cat > "$PROMPT_FILE" <<EOF
Tu travailles sur le projet athletIQ ($PROJECT_DIR).

== CONTEXTE ==
Lis PRODUCTION_PLAN.md et PLAN_GUIDE.md pour comprendre le projet.

== TA TACHE UNIQUE ==
Tache **${task_id}** : ${description}

== REGLES ==
1. Ne travaille QUE sur cette tache, rien d autre.
2. Ecris du code propre, minimal, sans sur-ingenierie.
3. Verifie que ca fonctionne (lance les tests si pertinent).
4. Une fois termine, mets a jour PRODUCTION_PLAN.md :
   - Change [ ] en [x] pour la tache ${task_id}
   - Ajoute une ligne dans le Journal des modifications
5. Si tu es bloque, marque la tache [~] et explique pourquoi dans le journal.

Commence maintenant.
EOF

        local prompt_content
        prompt_content=$(cat "$PROMPT_FILE")

        # --dangerously-skip-permissions : necessaire car claude -p est non-interactif
        # tee -a : affiche dans le terminal ET ecrit dans les logs
        claude -p "$prompt_content" \
            --dangerously-skip-permissions \
            --max-turns "$MAX_TURNS" \
            2>&1 | tee -a "$task_log" "$LOG_FILE"

        if check_task_done "$task_id"; then
            log "${GREEN}  [OK] $task_id termine !${NC}"
            return 0
        fi

        # Verifier si marque en cours (bloque)
        if grep -qE "\[~\].*\*\*${task_id}\*\*" "$PLAN_FILE" 2>/dev/null; then
            log "${YELLOW}  [~~] $task_id marque en cours/bloque${NC}"
            return 2
        fi

        log "${YELLOW}  [!!] $task_id pas valide apres tentative $attempt${NC}"
        log "${DIM}       Derniere sortie (voir $task_log pour le detail complet)${NC}"
        # Afficher les 5 dernieres lignes du log de la tentative
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

# ─── Notification tache HUMAIN ───────────────────────────────────────────────

notify_human_task() {
    local task_id="$1"
    local description="$2"

    if check_task_done "$task_id"; then
        log "${GREEN}  [OK] $task_id (HUMAIN) deja termine${NC}"
        return 0
    fi

    log "${YELLOW}  [HH] $task_id (HUMAIN) -- $description${NC}"

    if $DRY_RUN; then
        return 0
    fi

    echo ""
    echo -e "${YELLOW}  =======================================================${NC}"
    echo -e "${YELLOW}  ACTION HUMAINE REQUISE${NC}"
    echo -e "${YELLOW}  Tache $task_id : $description${NC}"
    echo -e "${YELLOW}  =======================================================${NC}"
    echo ""

    read -rp "  > Appuie sur Entree quand termine, ou tape skip : " response
    if [ "$response" = "skip" ]; then
        log "${DIM}       $task_id skippe${NC}"
        return 1
    fi
    return 0
}

# ─── Execution d une vague ───────────────────────────────────────────────────

run_wave() {
    local wave_num="$1"
    shift
    local failed=0

    echo ""
    log "${BOLD}${CYAN}========== VAGUE $wave_num ==========${NC}"
    separator

    while [ $# -gt 0 ]; do
        local entry="$1"
        shift

        local type="${entry%%|*}"
        local rest="${entry#*|}"
        local task_id="${rest%%|*}"
        local description="${rest#*|}"

        if [ "$type" = "HUMAIN" ]; then
            notify_human_task "$task_id" "$description" || failed=$((failed + 1))
        else
            run_agent_task "$task_id" "$description"
            local rc=$?
            if [ $rc -eq 1 ]; then
                failed=$((failed + 1))
                if ! $DRY_RUN; then
                    log "${RED}  Tache critique echouee. Arreter la vague ? (y/n)${NC}"
                    read -rp "  > " stop
                    if [ "$stop" = "y" ]; then
                        return 1
                    fi
                fi
            fi
        fi
    done

    separator
    log "${BOLD}Vague $wave_num terminee ($failed echec(s))${NC}"
    return 0
}

# ═══════════════════════════════════════════════════════════════════════════════
# DEFINITION DES VAGUES (extraites de PLAN_GUIDE.md)
# Format : "TYPE|TASK_ID|DESCRIPTION"
# ═══════════════════════════════════════════════════════════════════════════════

run_all_waves() {
    local current_wave=0

    # ── VAGUE 1 : Phase 1 Securite (lancement immediat) ─────────────────────

    current_wave=1
    if [ "$START_WAVE" -le "$current_wave" ]; then
        run_wave 1 \
            "AGENT|1.1.3|Generer une nouvelle ENCRYPTION_KEY Fernet" \
            "AGENT|1.1.4|Generer un nouveau JWT_SECRET_KEY fort" \
            "AGENT|1.1.5|Verifier .gitignore et historique git pour les secrets" \
            "AGENT|1.2.3|Supprimer secrets hardcodes de docker-compose.dev.yml" \
            "AGENT|1.2.4|Supprimer valeurs par defaut dangereuses dans settings.py" \
            "AGENT|1.3.1|Remplacer ALLOWED_ORIGINS wildcard par liste explicite selon ENVIRONMENT" \
            "AGENT|1.3.2|Configurer origines CORS pour dev (localhost:3000, localhost:4000)" \
            "AGENT|1.3.3|Configurer origines CORS pour prod (athletiq.vercel.app)" \
            "AGENT|1.3.4|Supprimer le wildcard de allow_origins dans main.py" \
            "AGENT|1.4.1|Changer le defaut de DEBUG a False dans settings.py" \
            "AGENT|1.4.2|ENVIRONMENT conditionne le comportement (logging, error detail)" \
            "AGENT|1.4.3|Ne pas exposer les stack traces en mode non-DEBUG" \
            "AGENT|1.5.1|Ajouter FRONTEND_URL et BACKEND_URL dans settings.py" \
            "HUMAIN|1.1.1|Regenerer STRAVA_CLIENT_SECRET depuis le dashboard Strava" \
            "HUMAIN|1.1.2|Regenerer STRAVA_REFRESH_TOKEN via un nouveau flow OAuth"

        if [ $? -ne 0 ]; then return 1; fi
        if ! $DRY_RUN && [ "$current_wave" -lt 8 ]; then
            echo ""
            log "${BOLD}Vague 1 OK. Continuer vers la vague 2 ?${NC}"
            read -rp "  > Entree=continuer, q=quitter : " resp
            if [ "$resp" = "q" ]; then return 0; fi
        fi
    fi

    # ── VAGUE 2 : Phase 1 suite (apres vague 1) ─────────────────────────────

    current_wave=2
    if [ "$START_WAVE" -le "$current_wave" ]; then
        run_wave 2 \
            "AGENT|1.1.6|Mettre a jour .env.example avec des placeholders clairs" \
            "AGENT|1.5.2|Remplacer URLs localhost hardcodees dans routes.py par settings.FRONTEND_URL" \
            "AGENT|1.5.3|Rendre STRAVA_REDIRECT_URI dynamique base sur BACKEND_URL" \
            "AGENT|1.5.4|Rendre Google OAuth redirect URI dynamique" \
            "HUMAIN|1.2.1|Configurer env vars sur Render.com" \
            "HUMAIN|1.2.2|Configurer env vars sur Vercel"

        if [ $? -ne 0 ]; then return 1; fi
        if ! $DRY_RUN && [ "$current_wave" -lt 8 ]; then
            echo ""
            log "${BOLD}Vague 2 OK. Continuer vers la vague 3 ?${NC}"
            read -rp "  > Entree=continuer, q=quitter : " resp
            if [ "$resp" = "q" ]; then return 0; fi
        fi
    fi

    # ── VAGUE 3 : Fin Phase 1 (HUMAIN uniquement) ───────────────────────────

    current_wave=3
    if [ "$START_WAVE" -le "$current_wave" ]; then
        run_wave 3 \
            "HUMAIN|1.5.5|Mettre a jour URIs dans dashboards Strava et Google Cloud Console"

        if [ $? -ne 0 ]; then return 1; fi
        if ! $DRY_RUN && [ "$current_wave" -lt 8 ]; then
            echo ""
            log "${BOLD}Vague 3 OK. Continuer vers la vague 4 ?${NC}"
            read -rp "  > Entree=continuer, q=quitter : " resp
            if [ "$resp" = "q" ]; then return 0; fi
        fi
    fi

    # ── VAGUE 4 : Phase 2 debut (Redis + Queue + Webhooks) ──────────────────

    current_wave=4
    if [ "$START_WAVE" -le "$current_wave" ]; then
        run_wave 4 \
            "AGENT|2.1.1|Verifier que Redis est bien connecte et fonctionnel" \
            "AGENT|2.1.2|Creer un RedisQuotaManager (compteurs dans Redis)" \
            "AGENT|2.1.3|Implementer TTL automatique sur le compteur 15min" \
            "AGENT|2.1.4|Implementer reset quotidien du compteur daily" \
            "AGENT|2.1.5|Remplacer StravaQuotaManager in-memory par RedisQuotaManager" \
            "AGENT|2.1.6|Ajouter endpoint /strava/quota retournant le statut temps reel" \
            "AGENT|2.2.1|Creer table enrichment_queue (activity_id, user_id, priority, status, created_at)" \
            "AGENT|2.2.2|Implementer scheduler round-robin pour enrichissement" \
            "AGENT|2.3.1|Creer endpoint POST /api/v1/webhooks/strava" \
            "AGENT|2.3.2|Creer endpoint GET /api/v1/webhooks/strava (validation challenge)" \
            "AGENT|2.3.3|Implementer verification de signature des webhooks" \
            "AGENT|2.3.4|Gerer les types evenements (activity.create/update/delete)"

        if [ $? -ne 0 ]; then return 1; fi
        if ! $DRY_RUN && [ "$current_wave" -lt 8 ]; then
            echo ""
            log "${BOLD}Vague 4 OK. Continuer vers la vague 5 ?${NC}"
            read -rp "  > Entree=continuer, q=quitter : " resp
            if [ "$resp" = "q" ]; then return 0; fi
        fi
    fi

    # ── VAGUE 5 : Phase 2 fin (Worker + Retries + Webhooks fin) ─────────────

    current_wave=5
    if [ "$START_WAVE" -le "$current_wave" ]; then
        run_wave 5 \
            "AGENT|2.2.3|Creer worker background qui depile la queue en respectant les quotas" \
            "AGENT|2.2.4|Ajouter endpoint position dans la queue pour utilisateur" \
            "AGENT|2.2.5|Gerer retries avec backoff exponentiel (max 3 tentatives)" \
            "AGENT|2.3.5|Sur activity.create ajouter automatiquement dans la queue enrichissement" \
            "HUMAIN|2.3.6|Enregistrer subscription webhook via API Strava" \
            "AGENT|2.3.7|Documenter la procedure enregistrement webhook dans le README"

        if [ $? -ne 0 ]; then return 1; fi
        if ! $DRY_RUN && [ "$current_wave" -lt 8 ]; then
            echo ""
            log "${BOLD}Vague 5 OK. Continuer vers la vague 6 ?${NC}"
            read -rp "  > Entree=continuer, q=quitter : " resp
            if [ "$resp" = "q" ]; then return 0; fi
        fi
    fi

    # ── VAGUE 6 : Phase 3 Robustesse ────────────────────────────────────────

    current_wave=6
    if [ "$START_WAVE" -le "$current_wave" ]; then
        run_wave 6 \
            "AGENT|3.1.1|Installer slowapi pour FastAPI" \
            "AGENT|3.1.2|Rate limit /auth/login : 5 tentatives/min par IP" \
            "AGENT|3.1.3|Rate limit /auth/signup : 3 inscriptions/heure par IP" \
            "AGENT|3.1.4|Rate limit global : 100 req/min par utilisateur" \
            "AGENT|3.1.5|Retourner headers Retry-After et status 429" \
            "AGENT|3.2.1|Middleware redirect HTTP vers HTTPS en production" \
            "AGENT|3.2.2|Flag Secure sur tous les cookies" \
            "AGENT|3.2.3|Headers de securite : HSTS, X-Content-Type-Options, X-Frame-Options" \
            "AGENT|3.3.1|Installer et configurer Sentry backend (sentry-sdk fastapi)" \
            "AGENT|3.3.2|Installer et configurer Sentry frontend (@sentry/react)" \
            "AGENT|3.3.4|Structured logging JSON pour les logs backend en production" \
            "AGENT|3.3.5|Rotation des logs (RotatingFileHandler)" \
            "AGENT|3.4.1|Creer composant ErrorBoundary global React" \
            "AGENT|3.4.2|Ajouter error boundaries par section (Dashboard, Activities, Plans)" \
            "AGENT|3.4.3|Message utilisateur friendly avec option reload" \
            "AGENT|3.4.4|Remonter erreur a Sentry depuis ErrorBoundary" \
            "AGENT|3.5.1|Ajouter alembic upgrade head dans Dockerfile" \
            "AGENT|3.5.2|Etape migration dans pipeline CI/CD" \
            "AGENT|3.5.3|Test migration sur base vierge dans la CI" \
            "AGENT|3.6.1|Configurer gunicorn multi-workers avec uvicorn" \
            "AGENT|3.6.2|Code splitting et lazy loading React (Dashboard, RacePredictor)" \
            "AGENT|3.6.3|Pagination reelle des activites (remplacer limit 1000)" \
            "HUMAIN|3.3.3|Configurer alertes Sentry (email sur nouvelle erreur)"

        if [ $? -ne 0 ]; then return 1; fi
        if ! $DRY_RUN && [ "$current_wave" -lt 8 ]; then
            echo ""
            log "${BOLD}Vague 6 OK. Continuer vers la vague 7 ?${NC}"
            read -rp "  > Entree=continuer, q=quitter : " resp
            if [ "$resp" = "q" ]; then return 0; fi
        fi
    fi

    # ── VAGUE 7 : Phase 4 Qualite ───────────────────────────────────────────

    current_wave=7
    if [ "$START_WAVE" -le "$current_wave" ]; then
        run_wave 7 \
            "AGENT|4.1.1|Decouper routes.py en routers separes (auth, activity, plan, sync, data)" \
            "AGENT|4.1.2|Creer api/routers/__init__.py incluant tous les routers" \
            "AGENT|4.1.3|Deplacer logique metier restante dans les services" \
            "AGENT|4.2.1|Tests integration OAuth Strava (mock des appels API)" \
            "AGENT|4.2.2|Tests pour le quota manager Redis" \
            "AGENT|4.2.3|Tests pour les webhooks Strava" \
            "AGENT|4.2.4|Tests frontend (AuthContext, services, composants critiques)" \
            "AGENT|4.2.5|Coverage frontend dans la CI" \
            "AGENT|4.3.1|Decouper RacePredictor.tsx en sous-composants" \
            "AGENT|4.3.2|Migrer JWT de localStorage vers cookies httpOnly" \
            "AGENT|4.3.3|Systeme de notifications toast pour feedback utilisateur"

        if [ $? -ne 0 ]; then return 1; fi
        if ! $DRY_RUN && [ "$current_wave" -lt 8 ]; then
            echo ""
            log "${BOLD}Vague 7 OK. Continuer vers la vague 8 ?${NC}"
            read -rp "  > Entree=continuer, q=quitter : " resp
            if [ "$resp" = "q" ]; then return 0; fi
        fi
    fi

    # ── VAGUE 8 : Phase 5 Infrastructure ────────────────────────────────────

    current_wave=8
    if [ "$START_WAVE" -le "$current_wave" ]; then
        run_wave 8 \
            "AGENT|5.1.1|Creer docker-compose.prod.yml (PostgreSQL, Redis, Backend, Frontend/Nginx)" \
            "AGENT|5.1.2|Creer Dockerfile.prod frontend (build React + Nginx)" \
            "AGENT|5.1.3|Health checks pour tous les services Docker" \
            "AGENT|5.2.1|Connection pooling PostgreSQL (pool_size, max_overflow)" \
            "AGENT|5.2.3|Index sur colonnes filtrees (user_id, start_date, activity_type)" \
            "HUMAIN|5.2.2|Backups automatiques DB (pg_dump ou service manage)" \
            "HUMAIN|5.3.1|Acheter/configurer nom de domaine" \
            "HUMAIN|5.3.2|Configurer DNS vers Render et Vercel" \
            "HUMAIN|5.3.3|Configurer certificat SSL"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

main() {
    echo ""
    echo -e "${BOLD}${CYAN}"
    echo "  RALPH LOOP — athletIQ"
    echo "  ====================="
    echo -e "${NC}"
    echo -e "  ${DIM}Vague de depart : $START_WAVE | Retries : $MAX_RETRIES | Dry run : $DRY_RUN${NC}"
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

    cd "$PROJECT_DIR" || exit 1

    local done_before
    done_before=$(count_done)
    log "Taches deja terminees : $done_before"
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
    echo "  Total taches terminees :          $done_after"
    echo "  Log complet :                     $LOG_FILE"
    echo -e "${NC}"
}

main "$@"
