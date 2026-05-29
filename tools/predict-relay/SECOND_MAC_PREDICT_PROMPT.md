# Prompt #4 (Prédicteur) — worker du vrai moteur de course sur le SECOND Mac

> **Mode d'emploi (André) :** ce worker fait tourner ton VRAI moteur de prédiction
> (V2.2/V2.3/V3, ~9700 lignes Python) contre ta base historique `stridedelta.db`,
> sur le 2e Mac. Il remplace le MVP Edge qui sortait un temps quasi-élite (15h42).
> Prouvé en local : V3 sur Swiss Canyon → **21h52** (ta prédiction perso).
>
> Contrairement au relais Garmin, ce worker a besoin du **code du repo** + de
> **`stridedelta.db`**. Prépare 2 choses avant :
> 1. La **clé `service_role`** Supabase (la même que dans `~/garmin-relay/.env`).
> 2. Le fichier **`backend/stridedelta.db`** (170 Mo) — AirDrop depuis le 1er Mac.
>
> Colle le bloc entre les `=====` dans le Claude Code du 2e Mac.

=====================================================================

Tu es sur le 2e Mac (celui qui héberge déjà le relais Garmin). Mission : installer
et lancer le **worker de prédiction de course**. Il fait tourner le vrai moteur
Python (dossier `backend/app/domain/services/race_predictor/`) contre la base
historique `stridedelta.db`, et il est piloté par une file Supabase
(`prediction_jobs`) : la PWA enfile une demande, ce worker calcule la vraie
prédiction personnalisée et écrit le résultat.

Procède dans l'ordre :

## Étape 1 — Python 3 + git

```bash
python3 --version
git --version
```
Si manquant : `xcode-select --install`.

## Étape 2 — Récupérer le code du repo

```bash
cd ~
git clone https://github.com/AndreBertea/athletIQ.git 2>/dev/null || (cd athletIQ && git fetch)
cd ~/athletIQ
git checkout codex/agon-supabase-vercel
git pull
```
Si le repo est privé et que le clone demande une auth : lance `gh auth login`
(GitHub.com, HTTPS, login navigateur), puis recommence le clone.

## Étape 3 — Mettre la base historique en place

Le fichier `stridedelta.db` (170 Mo) n'est PAS dans git. André va te l'AirDropper
depuis le 1er Mac (il se trouve à `athletIQ/backend/stridedelta.db` là-bas).
Place-le dans `~/athletIQ/backend/stridedelta.db`. Vérifie :

```bash
ls -lh ~/athletIQ/backend/stridedelta.db
```
Il doit faire ~170 Mo. (Demande-moi le fichier si tu ne le vois pas.)

## Étape 4 — Configurer le worker

```bash
cd ~/athletIQ/tools/predict-relay
cp .env.example .env
```
Édite `.env` et renseigne **`SUPABASE_SERVICE_ROLE_KEY`** (demande-la à André — c'est
la même clé que dans `~/garmin-relay/.env`). Les autres valeurs (`SUPABASE_URL`,
`OLD_USER_ID`, et les clés bidons) sont déjà pré-remplies. Ne mets ces secrets que
dans `.env`, ne les affiche pas en clair.

## Étape 5 — Lancer

```bash
./run.sh
```
Au premier lancement il crée le venv et installe les dépendances du backend
(numpy, sqlmodel, gpxpy… ~1-2 min). Tu dois voir :
```
Worker prédiction démarré (DB=sqlite:////Users/.../stridedelta.db). Polling...
```
**Laisse cette fenêtre ouverte.** (C'est un 2e process, séparé du relais Garmin :
tu as donc 2 fenêtres `run.sh` qui tournent — une pour Garmin, une pour la prédiction.)

## Vérification

Dans l'app AGON → Race Predictor → choisis une trace (ex. Swiss Canyon), moteur
**V3**, puis « Lancer V3 hybride ». Côté worker tu verras :
```
job <id> : moteur v3 (user ...)
  job <id> OK : v3_hybrid -> 21h52
```
et l'app affichera la prédiction personnalisée (≈22h, avec trail factor et
incertitude P10/P50/P90) au lieu du temps quasi-élite.

> ℹ️ V1 reste calculé instantanément côté serveur (Edge). V2 et V3 passent par ce
> worker (le vrai moteur). Si une prédiction reste « en attente » >3 min, c'est que
> ce worker ne tourne pas — relance `./run.sh`.

=====================================================================
