# Relais Garmin maison

Worker qui fait le **login Garmin depuis ton IP résidentielle** (ton Mac H24),
parce que l'`oauth-service` de Garmin renvoie **HTTP 429** depuis l'IP datacenter
de Supabase. C'est le pont qui débloque la connexion Garmin **pour tous tes
athlètes**, directement depuis la PWA.

## Architecture (rappel)

```
PWA → Edge garmin-login → file garmin_relay_jobs (creds chiffrés) + sync_jobs
                                          │
                  ┌───────── polling sortant (aucun port ouvert) ───────────┐
                  ▼                                                          │
            CE WORKER (ton Mac)                                              │
            garth.login() depuis ton IP → token chiffré → external_auth_tokens
                  │                                                          │
                  └→ marque sync_jobs "succeeded" ←── la PWA poll et affiche ✅
```

Le worker ne reçoit rien de l'extérieur : il **tire** le travail depuis Supabase.
Pas besoin d'IP fixe, de port ouvert ni de tunnel.

## Prérequis

1. **Appliquer la migration** `supabase/migrations/202605290001_garmin_relay_queue.sql`
   (crée la table `garmin_relay_jobs`).
2. **Déployer la fonction Edge** mise à jour :
   `supabase functions deploy garmin-login`
3. **Déployer le front** (le polling est dans `client-app/src/lib/api.ts`).

## Installation du worker (sur le Mac H24)

```bash
cd tools/garmin-relay
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # puis remplir les 3 secrets
```

Les 3 secrets à remplir dans `.env` :

| Variable | Où le trouver |
|----------|---------------|
| `SUPABASE_URL` | URL du projet |
| `SUPABASE_SERVICE_ROLE_KEY` | Dashboard → Project Settings → API → `service_role` |
| `ENCRYPTION_KEY` | **Exactement la même** que le secret des Edge Functions (Dashboard → Edge Functions → Secrets). Sinon le worker ne pourra pas déchiffrer les identifiants ni produire un token lisible par l'Edge. |

### Lancer le pont (le plus simple)

`run.sh` est fourni et fait tout : il crée le venv et installe les dépendances
au premier lancement, charge `.env`, puis lance le worker en empêchant le Mac de
dormir (`caffeinate`).

```bash
./run.sh
```

Tu dois voir `Relais Garmin demarre. Polling...`. Connecte-toi depuis la PWA :
la ligne `login job ...` doit apparaître, puis `connecte (...)`. **Laisse la
fenêtre ouverte** : le pont reste ouvert tant qu'elle tourne.

### Lancer en permanence (launchd, redémarrage auto au boot)

Pour un vrai H24 qui survit aux reboots, utilise launchd avec `run.sh` :
adapte `com.agon.garmin-relay.plist` (remplace les `/ABSOLUTE/PATH/...` et fais
pointer `ProgramArguments` sur `run.sh`), retire le bloc `EnvironmentVariables`
(les secrets viennent du `.env` via `run.sh`), puis :

```bash
cp com.agon.garmin-relay.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.agon.garmin-relay.plist
tail -f relay.log
```

> ⚠️ **Empêche le Mac de dormir** sinon le relais s'arrête : Réglages Système →
> Batterie/Alimentation → « Empêcher la mise en veille automatique » quand
> l'écran est éteint (ou lance le worker via `caffeinate -s`).

## MFA (double authentification)

Géré automatiquement : si Garmin demande un code, le `sync_jobs` passe en
`mfa_required`, la PWA affiche le champ code, l'athlète saisit, le worker reprend
la session (`resume_login`) et termine. La session MFA est gardée **en mémoire**
du worker ; s'il redémarre pendant l'attente, l'athlète relance simplement la
connexion.

## Le point à surveiller (refresh & sync)

- Le worker **rafraîchit les tokens avant expiration** (boucle toutes les 5 min)
  pour que la sync côté Edge n'ait jamais à appeler l'`oauth-service` (qui
  re-429erait depuis Supabase).
- La **sync des données** (`connectapi.garmin.com`) reste pour l'instant sur
  l'Edge. Si elle se met aussi à renvoyer 429 (à tester en conditions réelles),
  il faudra la déplacer ici aussi — l'ossature du worker (garth + écriture base)
  est déjà en place pour ça.

## Sécurité

- Le `.env` contient la `service_role` et l'`ENCRYPTION_KEY` : **ne jamais le
  committer** (déjà couvert par `.gitignore`).
- Les identifiants Garmin transitent chiffrés (AES-GCM) et ne sont jamais
  lisibles par le client (table `garmin_relay_jobs` en service-role uniquement).
