#!/bin/bash
# Relais Garmin maison — OUVRE LE PONT.
#
# Idempotent : au premier lancement il cree l'environnement Python et installe
# les dependances ; ensuite il lance directement le worker. Le Mac est maintenu
# eveille (caffeinate) tant que cette fenetre reste ouverte.
#
# Usage : double-clic (si .sh associe au Terminal) ou  ./run.sh  dans le Terminal.
set -euo pipefail
cd "$(dirname "$0")"

echo "================  RELAIS GARMIN  ================"

# 1) Python 3 disponible ?
if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ python3 introuvable."
  echo "   Installe-le :  xcode-select --install     (ou : brew install python)"
  exit 1
fi

# 2) Secrets presents ?
if [ ! -f .env ]; then
  echo "❌ Fichier .env manquant."
  echo "   Fais :  cp .env.example .env   puis remplis les 3 secrets."
  exit 1
fi

# 3) Environnement Python (cree au premier lancement seulement)
if [ ! -d .venv ]; then
  echo "→ Premier lancement : creation de l'environnement Python..."
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r requirements.txt
  echo "→ Dependances installees."
fi

# 4) Charge les secrets (.env)
set -a
# shellcheck disable=SC1091
source .env
set +a

# 5) Lance le relais en empechant la mise en veille du Mac.
#    caffeinate -s : empeche la veille systeme (efficace sur secteur).
#    Ajoute -i pour empecher aussi la veille en cas d'inactivite.
echo "→ Pont Garmin OUVERT. Laisse cette fenetre ouverte."
echo "   (Ctrl+C pour arreter le pont)"
echo "================================================="
exec caffeinate -s -i ./.venv/bin/python garmin_relay.py
