-- File des prédictions de course traitées par le VRAI moteur Python (V2.2/V2.3/V3)
-- qui tourne sur le 2e Mac (le relais), car le moteur (~9700 lignes + numpy) ne
-- peut pas tourner dans Deno. L'Edge `predict-race` enfile ici ; le worker récupère
-- le GPX, lance predict_v3/predict_v2_3 contre la base historique (stridedelta.db),
-- et écrit le résultat complet dans `result`. La PWA lit `result` (poll).
--
-- Secrets : pas de credentials ici, mais service-role only par cohérence (le worker
-- écrit, la PWA lit son propre job).

create table if not exists public.prediction_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  engine text not null default 'v3' check (engine in ('v3', 'v2_3', 'v2_2', 'v2', 'v1')),
  route_id uuid references public.gpx_routes(id) on delete set null,
  gpx_storage_path text,
  params jsonb not null default '{}'::jsonb,
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'done', 'failed')),
  result jsonb,
  result_prediction_id uuid,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists prediction_jobs_status_idx
  on public.prediction_jobs(status, created_at);
create index if not exists prediction_jobs_user_idx
  on public.prediction_jobs(user_id, created_at desc);

alter table public.prediction_jobs enable row level security;

-- La PWA lit l'avancement/résultat de ses propres jobs.
create policy "prediction_jobs_select_own" on public.prediction_jobs
  for select to authenticated using (user_id = auth.uid());
-- Insertion via l'Edge (service-role) ; traitement via le worker (service-role).
-- Pas de policy insert/update pour 'authenticated'.

drop trigger if exists set_prediction_jobs_updated_at on public.prediction_jobs;
create trigger set_prediction_jobs_updated_at
  before update on public.prediction_jobs
  for each row execute function public.set_updated_at();

alter table public.prediction_jobs replica identity full;
do $$
begin
  alter publication supabase_realtime add table public.prediction_jobs;
exception when duplicate_object then null;
end $$;
