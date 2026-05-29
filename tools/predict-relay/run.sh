#!/bin/bash
# Worker de prédiction de course (V2.2/V2.3/V3) — fait tourner le VRAI moteur
# Python contre stridedelta.db, sur le 2e Mac. Idempotent : crée le venv et
# installe les deps du backend au premier lancement.
set -euo pipefail
cd "$(dirname "$0")"

echo "============  WORKER PREDICTION (vrai moteur V3)  ============"

# Racine du repo (tools/predict-relay -> ../../)
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ python3 introuvable. Installe : xcode-select --install  (ou brew install python)"
  exit 1
fi
if [ ! -f .env ]; then
  echo "❌ .env manquant. Fais : cp .env.example .env  puis remplis les valeurs."
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

# Defaults dérivés du repo si non fournis.
: "${PREDICT_DB_PATH:=$REPO_DIR/backend/stridedelta.db}"
export PREDICT_DB_PATH
export PYTHONPATH="$REPO_DIR/backend"

if [ ! -f "$PREDICT_DB_PATH" ]; then
  echo "❌ Base historique introuvable : $PREDICT_DB_PATH"
  echo "   Copie stridedelta.db (170 Mo, AirDrop depuis le 1er Mac) dans $REPO_DIR/backend/"
  exit 1
fi

if [ ! -d .venv ]; then
  echo "→ Premier lancement : création de l'environnement Python + deps backend..."
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r "$REPO_DIR/backend/requirements.txt"
  ./.venv/bin/pip install --quiet requests
  echo "→ Dépendances installées."
fi

echo "→ Worker prédiction OUVERT (DB: $PREDICT_DB_PATH). Laisse cette fenêtre ouverte."
echo "   (Ctrl+C pour arrêter)"
echo "=============================================================="

# IMPORTANT : on lance le worker depuis un CWD VIDE. Le backend
# (app.core.settings.Settings) utilise env_file=".env" + extra=forbid : si
# pydantic trouvait NOTRE .env (qui contient des clés propres au worker comme
# SUPABASE_URL/OLD_USER_ID, non déclarées dans Settings), l'import du moteur
# planterait (extra_forbidden). Depuis un dossier vide, pydantic ne trouve aucun
# .env et lit uniquement os.environ (source qui ignore les variables inconnues).
# Les secrets ont déjà été chargés dans l'environnement via `source .env` ci-dessus.
VENV_PY="$PWD/.venv/bin/python"
WORKER="$REPO_DIR/tools/predict-relay/predict_worker.py"
RUNDIR="$(mktemp -d)"
cd "$RUNDIR"
exec caffeinate -s -i "$VENV_PY" "$WORKER"
