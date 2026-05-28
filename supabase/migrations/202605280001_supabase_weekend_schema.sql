-- AGON Supabase weekend migration
-- Supabase Auth + Postgres + Realtime + Storage private buckets.

create schema if not exists extensions;

do $$
begin
  execute 'create extension if not exists pgcrypto with schema extensions';
exception when others then
  raise notice 'pgcrypto extension not enabled: %', sqlerrm;
end $$;

do $$
begin
  execute 'create extension if not exists "uuid-ossp" with schema extensions';
exception when others then
  raise notice 'uuid-ossp extension not enabled: %', sqlerrm;
end $$;

do $$
begin
  execute 'create extension if not exists pgmq with schema extensions';
exception when others then
  raise notice 'pgmq extension not enabled: %', sqlerrm;
end $$;

do $$
begin
  execute 'create extension if not exists pg_cron with schema extensions';
exception when others then
  raise notice 'pg_cron extension not enabled: %', sqlerrm;
end $$;

do $$
begin
  execute 'create extension if not exists pg_net with schema extensions';
exception when others then
  raise notice 'pg_net extension not enabled: %', sqlerrm;
end $$;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text unique,
  full_name text,
  display_name text,
  avatar_url text,
  onboarding_completed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.activities (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  legacy_id text,
  source text not null default 'unknown',
  strava_id bigint,
  garmin_activity_id bigint,
  name text not null,
  sport_type text not null default 'Run',
  activity_type text,
  activity_type_override text,
  start_date_utc timestamptz,
  timezone text,
  location_city text,
  location_country text,
  distance_m double precision,
  moving_time_s integer,
  elapsed_time_s integer,
  elev_gain_m double precision,
  avg_speed_m_s double precision,
  max_speed_m_s double precision,
  avg_heartrate_bpm double precision,
  max_heartrate_bpm double precision,
  avg_cadence double precision,
  calories_kcal double precision,
  visibility text,
  private boolean not null default false,
  description text,
  summary_polyline text,
  polyline text,
  start_latlng jsonb,
  end_latlng jsonb,
  has_strava boolean not null default false,
  has_garmin boolean not null default false,
  has_fit_metrics boolean not null default false,
  has_streams boolean not null default false,
  has_weather boolean not null default false,
  raw_streams_path text,
  raw_laps_path text,
  raw_payload_path text,
  raw_summary jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists activities_user_strava_id_idx
  on public.activities(user_id, strava_id)
  where strava_id is not null;

create unique index if not exists activities_user_garmin_activity_id_idx
  on public.activities(user_id, garmin_activity_id)
  where garmin_activity_id is not null;

create index if not exists activities_user_started_idx
  on public.activities(user_id, start_date_utc desc);

create table if not exists public.activity_weather (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  activity_id uuid not null references public.activities(id) on delete cascade,
  temperature_c double precision,
  humidity_pct double precision,
  wind_speed_kmh double precision,
  wind_direction_deg double precision,
  pressure_hpa double precision,
  precipitation_mm double precision,
  cloud_cover_pct double precision,
  weather_code integer,
  sampled_at timestamptz,
  latitude double precision,
  longitude double precision,
  elevation_m double precision,
  source_endpoint text,
  source_url text,
  request_params jsonb,
  hourly_units jsonb,
  hourly_snapshot jsonb,
  timeline_10min jsonb,
  raw_weather_path text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(activity_id)
);

create index if not exists activity_weather_user_idx
  on public.activity_weather(user_id);

create table if not exists public.garmin_daily (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  hrv_rmssd double precision,
  training_readiness double precision,
  sleep_score double precision,
  sleep_duration_min integer,
  deep_sleep_seconds integer,
  light_sleep_seconds integer,
  rem_sleep_seconds integer,
  awake_sleep_seconds integer,
  sleep_start_time timestamptz,
  sleep_end_time timestamptz,
  average_respiration double precision,
  avg_sleep_stress double precision,
  resting_hr double precision,
  stress_score double precision,
  body_battery_max double precision,
  body_battery_min double precision,
  spo2 double precision,
  total_steps integer,
  total_kilocalories integer,
  active_kilocalories integer,
  vo2max_estimated double precision,
  lactate_threshold_speed_mps double precision,
  lactate_threshold_hr double precision,
  race_prediction_5k_seconds integer,
  race_prediction_10k_seconds integer,
  race_prediction_half_seconds integer,
  race_prediction_marathon_seconds integer,
  weight_kg double precision,
  training_status text,
  raw_payload_path text,
  raw_summary jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, date)
);

create table if not exists public.fit_metrics (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  activity_id uuid not null references public.activities(id) on delete cascade,
  ground_contact_time_avg double precision,
  vertical_oscillation_avg double precision,
  stance_time_balance_avg double precision,
  stance_time_percent_avg double precision,
  step_length_avg double precision,
  vertical_ratio_avg double precision,
  power_avg double precision,
  power_max double precision,
  normalized_power double precision,
  cadence_avg double precision,
  cadence_max double precision,
  heart_rate_avg double precision,
  heart_rate_max double precision,
  speed_avg double precision,
  speed_max double precision,
  temperature_avg double precision,
  temperature_max double precision,
  aerobic_training_effect double precision,
  anaerobic_training_effect double precision,
  total_calories double precision,
  total_strides double precision,
  total_ascent double precision,
  total_descent double precision,
  total_distance double precision,
  total_timer_time double precision,
  total_elapsed_time double precision,
  record_count integer,
  fit_downloaded_at timestamptz,
  raw_fit_path text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(activity_id)
);

create table if not exists public.segments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  activity_id uuid not null references public.activities(id) on delete cascade,
  segment_index integer not null,
  distance_m double precision not null,
  elapsed_time_s double precision,
  avg_grade_percent double precision,
  elevation_gain_m double precision,
  elevation_loss_m double precision,
  altitude_m double precision,
  avg_hr double precision,
  avg_cadence double precision,
  lat double precision,
  lon double precision,
  pace_min_per_km double precision,
  geometry jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(activity_id, segment_index)
);

create table if not exists public.segment_features (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  segment_id uuid not null references public.segments(id) on delete cascade,
  activity_id uuid not null references public.activities(id) on delete cascade,
  cumulative_distance_km double precision,
  elapsed_time_min double precision,
  cumulative_elev_gain_m double precision,
  cumulative_elev_loss_m double precision,
  race_completion_pct double precision,
  intensity_proxy double precision,
  minetti_cost double precision,
  cardiac_drift double precision,
  cadence_decay double precision,
  grade_variability double precision,
  efficiency_factor double precision,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(segment_id)
);

create table if not exists public.training_load (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  ctl_42d double precision,
  atl_7d double precision,
  tsb double precision,
  rhr_delta_7d double precision,
  edwards_trimp_daily double precision,
  ctl_42d_edwards double precision,
  atl_7d_edwards double precision,
  tsb_edwards double precision,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, date)
);

create table if not exists public.daily_checkins (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  entry_date date not null,
  wellbeing integer,
  sleep_quality integer,
  legs integer,
  motivation integer,
  srpe_yesterday integer,
  session_duration_min integer,
  context_tags jsonb not null default '[]'::jsonb,
  hrv_ln_rmssd numeric,
  resting_hr_bpm integer,
  sleep_duration_h numeric,
  notes text,
  source text not null default 'manual',
  client_origin text not null default 'pwa',
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, entry_date)
);

create table if not exists public.athletic_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade unique,
  sex text,
  birth_date date,
  height_cm double precision,
  weight_kg double precision,
  activity_level text,
  experience_level text,
  practice_dominant text,
  weekly_volume_band text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.reference_tests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  test_type text not null,
  performed_at timestamptz not null,
  duration_seconds integer not null,
  distance_m double precision,
  elevation_gain_m double precision,
  temperature_c double precision,
  surface text,
  conditions_notes text,
  quality_status text not null default 'valid',
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.gpx_routes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  filename text not null,
  is_public boolean not null default false,
  distance_km double precision,
  elevation_gain_m double precision,
  gpx_storage_path text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists gpx_routes_user_created_idx
  on public.gpx_routes(user_id, created_at desc);

create table if not exists public.gpx_route_settings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  route_id uuid not null references public.gpx_routes(id) on delete cascade,
  preferred_engine text not null default 'v3',
  analysis_mode text not null default 'auto',
  effort_mode text not null default 'steady',
  ravito_mode text not null default 'auto',
  weather_mode text not null default 'manual',
  manual_temperature_c double precision,
  history_start_date date,
  race_datetime timestamptz,
  custom_ravitos jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, route_id)
);

create table if not exists public.race_predictions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  route_id uuid references public.gpx_routes(id) on delete set null,
  name text not null,
  filename text,
  engine_version text not null default 'v3_supabase_mvp',
  analysis_mode text,
  ravito_mode text,
  history_start_date date,
  total_distance_km double precision,
  total_elevation_gain_m double precision,
  moving_time_min double precision,
  total_pause_min double precision,
  total_time_min double precision,
  avg_pace double precision,
  prediction_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists race_predictions_user_created_idx
  on public.race_predictions(user_id, created_at desc);

create table if not exists public.sync_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  type text not null,
  status text not null default 'queued'
    check (status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
  progress integer not null default 0 check (progress >= 0 and progress <= 100),
  stage text,
  message text,
  error text,
  payload jsonb not null default '{}'::jsonb,
  result jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz
);

create index if not exists sync_jobs_user_created_idx
  on public.sync_jobs(user_id, created_at desc);

create table if not exists public.job_events (
  id uuid primary key default gen_random_uuid(),
  job_id uuid references public.sync_jobs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  type text not null,
  message text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists job_events_user_created_idx
  on public.job_events(user_id, created_at desc);

create index if not exists job_events_job_created_idx
  on public.job_events(job_id, created_at asc);

create table if not exists public.external_auth_tokens (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  provider text not null,
  provider_user_id text,
  display_name text,
  email text,
  scopes text[] not null default array[]::text[],
  access_token_encrypted text,
  refresh_token_encrypted text,
  expires_at timestamptz,
  token_payload jsonb not null default '{}'::jsonb,
  last_sync_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, provider)
);

create index if not exists external_auth_tokens_user_provider_idx
  on public.external_auth_tokens(user_id, provider);

insert into storage.buckets (id, name, public, file_size_limit)
values
  ('activity-raw', 'activity-raw', false, 52428800),
  ('gpx-files', 'gpx-files', false, 10485760)
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit;

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'profiles',
    'activities',
    'activity_weather',
    'garmin_daily',
    'fit_metrics',
    'segments',
    'segment_features',
    'training_load',
    'daily_checkins',
    'athletic_profiles',
    'reference_tests',
    'gpx_routes',
    'gpx_route_settings',
    'race_predictions',
    'sync_jobs',
    'job_events',
    'external_auth_tokens'
  ]
  loop
    execute format('alter table public.%I enable row level security', table_name);
  end loop;
end $$;

create or replace function public.install_updated_at_trigger(target_table text)
returns void
language plpgsql
as $$
begin
  execute format('drop trigger if exists set_%I_updated_at on public.%I', target_table, target_table);
  execute format(
    'create trigger set_%I_updated_at before update on public.%I for each row execute function public.set_updated_at()',
    target_table,
    target_table
  );
end;
$$;

select public.install_updated_at_trigger('profiles');
select public.install_updated_at_trigger('activities');
select public.install_updated_at_trigger('activity_weather');
select public.install_updated_at_trigger('garmin_daily');
select public.install_updated_at_trigger('fit_metrics');
select public.install_updated_at_trigger('segments');
select public.install_updated_at_trigger('segment_features');
select public.install_updated_at_trigger('training_load');
select public.install_updated_at_trigger('daily_checkins');
select public.install_updated_at_trigger('athletic_profiles');
select public.install_updated_at_trigger('reference_tests');
select public.install_updated_at_trigger('gpx_routes');
select public.install_updated_at_trigger('gpx_route_settings');
select public.install_updated_at_trigger('race_predictions');
select public.install_updated_at_trigger('external_auth_tokens');

drop function public.install_updated_at_trigger(text);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, full_name, display_name)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data ->> 'full_name', ''),
    coalesce(new.raw_user_meta_data ->> 'full_name', split_part(new.email, '@', 1))
  )
  on conflict (id) do update
  set email = excluded.email,
      full_name = excluded.full_name,
      display_name = excluded.display_name,
      updated_at = now();
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

create or replace function public.get_external_auth_status(provider_name text)
returns table (
  provider text,
  connected boolean,
  provider_user_id text,
  display_name text,
  email text,
  scopes text[],
  expires_at timestamptz,
  is_expired boolean,
  last_sync_at timestamptz
)
language sql
security definer
set search_path = public
as $$
  select
    t.provider,
    true as connected,
    t.provider_user_id,
    t.display_name,
    t.email,
    t.scopes,
    t.expires_at,
    coalesce(t.expires_at < now(), false) as is_expired,
    t.last_sync_at
  from public.external_auth_tokens t
  where t.user_id = auth.uid()
    and t.provider = provider_name
  limit 1;
$$;

create or replace function public.create_sync_job(job_type text, job_payload jsonb default '{}'::jsonb)
returns public.sync_jobs
language plpgsql
security invoker
set search_path = public
as $$
declare
  new_job public.sync_jobs;
begin
  insert into public.sync_jobs (user_id, type, payload)
  values (auth.uid(), job_type, coalesce(job_payload, '{}'::jsonb))
  returning * into new_job;
  return new_job;
end;
$$;

create or replace function public.disconnect_external_auth(provider_name text)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
begin
  delete from public.external_auth_tokens
  where user_id = auth.uid()
    and provider = provider_name;
  return true;
end;
$$;

create or replace function public.append_job_event(
  target_job_id uuid,
  event_type text,
  event_message text default null,
  event_payload jsonb default '{}'::jsonb
)
returns public.job_events
language plpgsql
security invoker
set search_path = public
as $$
declare
  event_row public.job_events;
begin
  insert into public.job_events (job_id, user_id, type, message, payload)
  select id, user_id, event_type, event_message, coalesce(event_payload, '{}'::jsonb)
  from public.sync_jobs
  where id = target_job_id
    and user_id = auth.uid()
  returning * into event_row;

  if event_row.id is null then
    raise exception 'sync job not found or not owned by current user';
  end if;

  return event_row;
end;
$$;

grant execute on function public.get_external_auth_status(text) to authenticated;
grant execute on function public.create_sync_job(text, jsonb) to authenticated;
grant execute on function public.disconnect_external_auth(text) to authenticated;
grant execute on function public.append_job_event(uuid, text, text, jsonb) to authenticated;

create policy "profiles_select_own"
  on public.profiles for select
  to authenticated
  using (id = auth.uid());

create policy "profiles_update_own"
  on public.profiles for update
  to authenticated
  using (id = auth.uid())
  with check (id = auth.uid());

create policy "profiles_insert_own"
  on public.profiles for insert
  to authenticated
  with check (id = auth.uid());

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'activities',
    'activity_weather',
    'garmin_daily',
    'fit_metrics',
    'segments',
    'segment_features',
    'training_load',
    'daily_checkins',
    'athletic_profiles',
    'reference_tests',
    'gpx_routes',
    'gpx_route_settings',
    'race_predictions',
    'sync_jobs',
    'job_events'
  ]
  loop
    execute format(
      'create policy %I on public.%I for select to authenticated using (user_id = auth.uid())',
      table_name || '_select_own',
      table_name
    );
    execute format(
      'create policy %I on public.%I for insert to authenticated with check (user_id = auth.uid())',
      table_name || '_insert_own',
      table_name
    );
    execute format(
      'create policy %I on public.%I for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid())',
      table_name || '_update_own',
      table_name
    );
    execute format(
      'create policy %I on public.%I for delete to authenticated using (user_id = auth.uid())',
      table_name || '_delete_own',
      table_name
    );
  end loop;
end $$;

-- No authenticated select policy on external_auth_tokens: secrets stay
-- service-role only. The safe metadata access path is get_external_auth_status().

create policy "activity_raw_select_own"
  on storage.objects for select
  to authenticated
  using (bucket_id = 'activity-raw' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "activity_raw_insert_own"
  on storage.objects for insert
  to authenticated
  with check (bucket_id = 'activity-raw' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "activity_raw_update_own"
  on storage.objects for update
  to authenticated
  using (bucket_id = 'activity-raw' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'activity-raw' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "activity_raw_delete_own"
  on storage.objects for delete
  to authenticated
  using (bucket_id = 'activity-raw' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "gpx_files_select_own"
  on storage.objects for select
  to authenticated
  using (bucket_id = 'gpx-files' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "gpx_files_insert_own"
  on storage.objects for insert
  to authenticated
  with check (bucket_id = 'gpx-files' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "gpx_files_update_own"
  on storage.objects for update
  to authenticated
  using (bucket_id = 'gpx-files' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'gpx-files' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "gpx_files_delete_own"
  on storage.objects for delete
  to authenticated
  using (bucket_id = 'gpx-files' and (storage.foldername(name))[1] = auth.uid()::text);

alter table public.sync_jobs replica identity full;
alter table public.job_events replica identity full;

do $$
begin
  alter publication supabase_realtime add table public.sync_jobs;
exception
  when duplicate_object then null;
  when undefined_object then
    raise notice 'publication supabase_realtime not available in this environment';
end $$;

do $$
begin
  alter publication supabase_realtime add table public.job_events;
exception
  when duplicate_object then null;
  when undefined_object then
    raise notice 'publication supabase_realtime not available in this environment';
end $$;
