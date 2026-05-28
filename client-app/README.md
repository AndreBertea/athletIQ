# AGON - PWA mobile

App mobile-first AGON: check-in quotidien, analytics, activites,
profil, live tracking et race predictor.

## Demarrage local

```bash
npm install
cp .env.example .env
npm run dev
```

Le serveur Vite ecoute par defaut sur `http://localhost:5173`.

## Variables d'environnement

| Var | Usage |
| --- | --- |
| `VITE_SUPABASE_URL` | URL du projet Supabase |
| `VITE_SUPABASE_ANON_KEY` | Cle anon publique Supabase |
| `VITE_MAPTILER_API_KEY` | Cle MapTiler pour les cartes |

## Stack

React 19 + Vite + TypeScript + Tailwind CSS, TanStack Query,
Supabase JS et vite-plugin-pwa.
