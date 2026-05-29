-- LiveTrack sur Supabase (migration de l'ancien backend Render vers le relais maison).
-- Le relais (IP residentielle) scrape la page publique livetrack.garmin.com et
-- insere les trackpoints ici (service-role). La PWA lit via Supabase Realtime.

create table if not exists public.live_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  source text not null default 'livetrack' check (source in ('livetrack', 'connect_iq')),
  label text,
  status text not null default 'active' check (status in ('active', 'finished', 'stopped')),
  -- LiveTrack : extraits de l'URL partagee (jeton public, pas un secret de compte).
  garmin_session_id text,
  garmin_token text,
  started_at timestamptz,
  ended_at timestamptz,
  last_point_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists live_sessions_user_idx on public.live_sessions(user_id, created_at desc);
create index if not exists live_sessions_active_idx on public.live_sessions(status, source);

create table if not exists public.live_trackpoints (
  session_id uuid not null references public.live_sessions(id) on delete cascade,
  ts bigint not null,
  lat double precision,
  lng double precision,
  hr integer,
  speed double precision,
  cadence integer,
  power integer,
  distance double precision,
  altitude double precision,
  primary key (session_id, ts)
);

alter table public.live_sessions enable row level security;
alter table public.live_trackpoints enable row level security;

-- live_sessions : proprietaire = acces complet.
create policy "live_sessions_select_own" on public.live_sessions
  for select to authenticated using (user_id = auth.uid());
create policy "live_sessions_insert_own" on public.live_sessions
  for insert to authenticated with check (user_id = auth.uid());
create policy "live_sessions_update_own" on public.live_sessions
  for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "live_sessions_delete_own" on public.live_sessions
  for delete to authenticated using (user_id = auth.uid());

-- live_trackpoints : lecture si la session appartient a l'utilisateur.
-- L'ecriture se fait UNIQUEMENT via la service-role (le relais) -> pas de policy
-- insert/update pour 'authenticated'.
create policy "live_trackpoints_select_own" on public.live_trackpoints
  for select to authenticated using (
    session_id in (select id from public.live_sessions where user_id = auth.uid())
  );

drop trigger if exists set_live_sessions_updated_at on public.live_sessions;
create trigger set_live_sessions_updated_at
  before update on public.live_sessions
  for each row execute function public.set_updated_at();

-- Realtime : la PWA s'abonne aux INSERT de points et aux changements de statut.
alter table public.live_sessions replica identity full;
alter table public.live_trackpoints replica identity full;

do $$
begin
  alter publication supabase_realtime add table public.live_sessions;
exception when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.live_trackpoints;
exception when duplicate_object then null;
end $$;
