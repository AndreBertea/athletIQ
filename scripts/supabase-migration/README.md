# Migration AGON vers Supabase

Script week-end pour migrer l'historique depuis l'ancien Postgres FastAPI vers Supabase.

```bash
cd scripts/supabase-migration
npm install
cp .env.example .env
npm run migrate
```

Points importants:

- Les mots de passe existants ne sont pas récupérables. Le script crée des utilisateurs Supabase avec un mot de passe temporaire ou mappe un compte existant via `SUPABASE_USER_ID_MAP_JSON`.
- Les gros JSON (`streams_data`, `laps_data`, météo détaillée) partent dans les buckets privés `activity-raw` et `gpx-files`.
- Par défaut, les tokens OAuth legacy ne sont pas rendus utilisables par les Edge Functions. Reconnecter Strava/Garmin après migration, sauf si `LEGACY_TOKEN_MODE=copy` est explicitement choisi avec la même stratégie de chiffrement.
