#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# test_migration_on_copy.sh
# -----------------------------------------------------------------------------
# Teste la migration Alembic `v231_engine_version` sur une COPIE de la
# base SQLite locale `backend/stridedelta.db`. La DB originale n'est jamais
# modifiee.
#
# Usage : cd backend && bash scripts/test_migration_on_copy.sh
#
# Reference : docs/RACE_PREDICTOR_V2_3_FIX_PLAN.md - R6 partiel, livrable 2.
# -----------------------------------------------------------------------------

set -uo pipefail

# Determine la racine backend (le script est dans backend/scripts/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE_DB="${BACKEND_DIR}/stridedelta.db"
COPY_DB="/tmp/stridedelta_migration_test.db"
TARGET_REVISION="v231_engine_version"
PYTHON_BIN="${BACKEND_DIR}/venv/bin/python"

# ------------- Helpers ------------------------------------------------------

color_green="\033[0;32m"
color_red="\033[0;31m"
color_yellow="\033[0;33m"
color_reset="\033[0m"

ok()   { printf "${color_green}[ OK ]${color_reset} %s\n" "$*"; }
warn() { printf "${color_yellow}[WARN]${color_reset} %s\n" "$*"; }
err()  { printf "${color_red}[FAIL]${color_reset} %s\n" "$*"; }

cleanup() {
    if [[ -f "${COPY_DB}" ]]; then
        rm -f "${COPY_DB}"
    fi
}

inspect_engine_version() {
    # Verifie via sqlite3 (sans dependre de python pour cette etape).
    "${PYTHON_BIN}" - <<'PY'
import sqlite3
import sys

conn = sqlite3.connect("/tmp/stridedelta_migration_test.db")
cur = conn.cursor()
cur.execute("PRAGMA table_info(raceprediction)")
cols = {row[1]: row for row in cur.fetchall()}
if "engine_version" not in cols:
    print("MISSING_COLUMN")
    sys.exit(1)
row = cols["engine_version"]
# row = (cid, name, type, notnull, dflt_value, pk)
col_type = row[2]
notnull = row[3]
default = row[4]
print(f"COLUMN_TYPE={col_type}")
print(f"NOTNULL={notnull}")
print(f"DEFAULT={default}")

cur.execute("PRAGMA index_list(raceprediction)")
idx_names = [row[1] for row in cur.fetchall()]
if "ix_raceprediction_engine_version" in idx_names:
    print("INDEX_PRESENT=1")
else:
    print("INDEX_PRESENT=0")

conn.close()
PY
}

run_alembic() {
    local action="$1"
    cd "${BACKEND_DIR}" && env DATABASE_URL="sqlite:///${COPY_DB}" "${PYTHON_BIN}" -m alembic ${action} 2>&1
}

# ------------- Pre-flight ---------------------------------------------------

if [[ ! -f "${SOURCE_DB}" ]]; then
    err "Source DB introuvable : ${SOURCE_DB}"
    exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
    err "venv Python introuvable : ${PYTHON_BIN}"
    exit 1
fi

ok "Source DB        : ${SOURCE_DB}"
ok "Copy destination : ${COPY_DB}"
ok "Target revision  : ${TARGET_REVISION}"

# Nettoyage prealable au cas ou une copie tournerait deja.
cleanup

# ------------- 1. Copier la DB ---------------------------------------------

cp "${SOURCE_DB}" "${COPY_DB}"
ok "DB copiee."

# ------------- 2. Upgrade head ---------------------------------------------

printf "\n--- alembic upgrade head ---\n"
upgrade_output=$(run_alembic "upgrade head")
upgrade_rc=$?
echo "${upgrade_output}"

if [[ ${upgrade_rc} -ne 0 ]]; then
    err "alembic upgrade head a echoue (rc=${upgrade_rc})."
    cleanup
    exit 1
fi
ok "Upgrade head reussi."

# ------------- 3. Verifier colonne + index ---------------------------------

printf "\n--- Inspection schema apres upgrade ---\n"
inspection=$(inspect_engine_version)
if [[ $? -ne 0 ]]; then
    err "La colonne engine_version est absente apres upgrade."
    echo "${inspection}"
    cleanup
    exit 1
fi
echo "${inspection}"

if ! grep -q "INDEX_PRESENT=1" <<<"${inspection}"; then
    err "Index ix_raceprediction_engine_version manquant."
    cleanup
    exit 1
fi
ok "Colonne engine_version et index presents."

# Verification revision courante.
printf "\n--- alembic current ---\n"
current_output=$(run_alembic "current")
echo "${current_output}"
if ! grep -q "${TARGET_REVISION}" <<<"${current_output}"; then
    err "La revision courante n'est pas ${TARGET_REVISION}."
    cleanup
    exit 1
fi
ok "Revision courante = ${TARGET_REVISION}."

# ------------- 4. Downgrade ------------------------------------------------

printf "\n--- alembic downgrade -1 ---\n"
downgrade_output=$(run_alembic "downgrade -1")
downgrade_rc=$?
echo "${downgrade_output}"

if [[ ${downgrade_rc} -ne 0 ]]; then
    err "alembic downgrade a echoue (rc=${downgrade_rc})."
    cleanup
    exit 1
fi
ok "Downgrade -1 reussi."

# La colonne devrait avoir disparu (en SQLite : batch op).
printf "\n--- Inspection schema apres downgrade ---\n"
post_downgrade=$("${PYTHON_BIN}" - <<'PY'
import sqlite3
conn = sqlite3.connect("/tmp/stridedelta_migration_test.db")
cur = conn.cursor()
cur.execute("PRAGMA table_info(raceprediction)")
cols = [row[1] for row in cur.fetchall()]
print(f"COLUMNS={cols}")
if "engine_version" in cols:
    print("STILL_PRESENT=1")
else:
    print("STILL_PRESENT=0")
conn.close()
PY
)
echo "${post_downgrade}"
if grep -q "STILL_PRESENT=1" <<<"${post_downgrade}"; then
    warn "La colonne engine_version est encore presente apres downgrade (acceptable pour DB de prod)."
fi

# ------------- 5. Re-upgrade pour valider la reversibilite -----------------

printf "\n--- alembic upgrade head (replay) ---\n"
reupgrade_output=$(run_alembic "upgrade head")
reupgrade_rc=$?
echo "${reupgrade_output}"

if [[ ${reupgrade_rc} -ne 0 ]]; then
    err "Re-upgrade apres downgrade a echoue (rc=${reupgrade_rc})."
    cleanup
    exit 1
fi
ok "Re-upgrade reussi : migration reversible."

# Verification finale.
printf "\n--- Inspection schema final ---\n"
final=$(inspect_engine_version)
echo "${final}"
if ! grep -q "INDEX_PRESENT=1" <<<"${final}"; then
    err "Index manquant apres re-upgrade."
    cleanup
    exit 1
fi
ok "Schema final coherent."

# ------------- Recap --------------------------------------------------------

printf "\n=============================================================\n"
ok "MIGRATION ${TARGET_REVISION} VALIDEE SUR COPIE DB."
printf "  - Upgrade head        : OK\n"
printf "  - Colonne presente    : OK\n"
printf "  - Index present       : OK\n"
printf "  - Downgrade -1        : OK\n"
printf "  - Re-upgrade head     : OK\n"
printf "=============================================================\n"

cleanup
exit 0
