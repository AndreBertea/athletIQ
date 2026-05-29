-- Garmin relay queue
-- Le login Garmin (scraping garth) est bloque (HTTP 429) depuis l'IP datacenter
-- de Supabase. Cette file permet a un worker tournant sur une IP residentielle
-- (le "relais maison") de prendre en charge le login + le refresh des tokens.
--
-- Securite : cette table contient les identifiants Garmin chiffres (AES-GCM via
-- ENCRYPTION_KEY). Comme external_auth_tokens, elle reste accessible UNIQUEMENT
-- via la service-role. Aucune policy pour le role "authenticated" : le client ne
-- doit jamais lire les credentials. Le suivi cote PWA passe par sync_jobs.

create table if not exists public.garmin_relay_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  sync_job_id uuid references public.sync_jobs(id) on delete set null,
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'awaiting_mfa', 'mfa_submitted', 'done', 'failed')),
  credentials_encrypted text not null,
  mfa_code_encrypted text,
  display_name text,
  error text,
  attempts integer not null default 0,
  claimed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists garmin_relay_jobs_status_idx
  on public.garmin_relay_jobs(status, created_at);

create index if not exists garmin_relay_jobs_user_idx
  on public.garmin_relay_jobs(user_id, created_at desc);

alter table public.garmin_relay_jobs enable row level security;

-- Volontairement aucune policy "authenticated" : service-role uniquement.

drop trigger if exists set_garmin_relay_jobs_updated_at on public.garmin_relay_jobs;
create trigger set_garmin_relay_jobs_updated_at
  before update on public.garmin_relay_jobs
  for each row execute function public.set_updated_at();
