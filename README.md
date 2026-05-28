# AGON

AGON est une application mobile-first d'analyse d'endurance et de trail.
Elle combine donnees Strava, Garmin, meteo, charge d'entrainement, check-in
quotidien, live tracking et prediction de course GPX.

## Stack cible

- Frontend prioritaire: `client-app` React + TypeScript + Vite + Tailwind.
- Frontend web historique: `frontend` React + TypeScript + Vite.
- Backend cible week-end: Supabase Auth, Postgres, Realtime, Storage prive et Edge Functions.
- Backend legacy: FastAPI + PostgreSQL + Redis, conserve comme reference et source de migration.

## Demarrage local

### PWA AGON

```bash
cd client-app
npm install
cp .env.example .env
npm run dev
```

Variables attendues:

```env
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
VITE_MAPTILER_API_KEY=
```

### Frontend web

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

### Supabase

```bash
supabase link --project-ref <project-ref>
supabase db push
supabase functions deploy predict-race
supabase functions deploy strava-oauth-start
supabase functions deploy strava-oauth-callback
supabase functions deploy strava-sync
supabase functions deploy weather-enrich
supabase functions deploy data-export
supabase functions deploy delete-account
```

Secrets requis pour les Edge Functions:

```env
SUPABASE_SERVICE_ROLE_KEY=
STRAVA_CLIENT_ID=
STRAVA_CLIENT_SECRET=
ENCRYPTION_KEY=
OPEN_METEO_BASE_URL=https://api.open-meteo.com/v1/forecast
PUBLIC_SITE_URL=
```

## Migration des donnees

Le script de migration est dans `scripts/supabase-migration`.

```bash
cd scripts/supabase-migration
npm install
cp .env.example .env
npm run migrate
```

Il migre l'historique legacy vers Supabase et externalise les gros JSON vers
Supabase Storage prive.

## GitHub Page

La page de presentation dediee AGON est dans `docs/index.html`.
Le workflow `.github/workflows/github-pages.yml` publie ce dossier sur GitHub Pages.

## Notes de production

- Render n'est plus dans le chemin critique du MVP.
- La prediction GPX MVP tourne dans l'Edge Function `predict-race`.
- La sync Garmin/FIT complete reste hors garantie week-end; l'historique migre reste affichable.
