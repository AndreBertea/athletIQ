-- GPX legacy compatibility:
-- - allow public catalog routes migrated from legacy gpxroute(user_id = null)
-- - persist PDF/image/other legacy gpxattachment files in private Storage
-- - expose public routes/attachments to authenticated users without making user-owned files public

alter table public.gpx_routes
  alter column user_id drop not null;

create index if not exists gpx_routes_public_created_idx
  on public.gpx_routes(is_public, created_at desc);

create table if not exists public.gpx_route_attachments (
  id uuid primary key default gen_random_uuid(),
  route_id uuid not null references public.gpx_routes(id) on delete cascade,
  user_id uuid references auth.users(id) on delete cascade,
  name text not null,
  filename text not null,
  mime_type text not null default 'application/octet-stream',
  kind text not null default 'other',
  storage_path text not null,
  created_at timestamptz not null default now()
);

create index if not exists gpx_route_attachments_route_idx
  on public.gpx_route_attachments(route_id);

create index if not exists gpx_route_attachments_user_idx
  on public.gpx_route_attachments(user_id);

alter table public.gpx_route_attachments enable row level security;

drop policy if exists "gpx_routes_select_own" on public.gpx_routes;
drop policy if exists "gpx_routes_insert_own" on public.gpx_routes;
drop policy if exists "gpx_routes_update_own" on public.gpx_routes;
drop policy if exists "gpx_routes_delete_own" on public.gpx_routes;

create policy "gpx_routes_select_visible"
  on public.gpx_routes for select
  to authenticated
  using (user_id = auth.uid() or is_public = true);

create policy "gpx_routes_insert_own"
  on public.gpx_routes for insert
  to authenticated
  with check (user_id = auth.uid());

create policy "gpx_routes_update_own"
  on public.gpx_routes for update
  to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

create policy "gpx_routes_delete_own"
  on public.gpx_routes for delete
  to authenticated
  using (user_id = auth.uid());

create policy "gpx_route_attachments_select_visible"
  on public.gpx_route_attachments for select
  to authenticated
  using (
    user_id = auth.uid()
    or exists (
      select 1
      from public.gpx_routes r
      where r.id = public.gpx_route_attachments.route_id
        and r.is_public = true
    )
  );

create policy "gpx_route_attachments_insert_own"
  on public.gpx_route_attachments for insert
  to authenticated
  with check (user_id = auth.uid());

create policy "gpx_route_attachments_update_own"
  on public.gpx_route_attachments for update
  to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

create policy "gpx_route_attachments_delete_own"
  on public.gpx_route_attachments for delete
  to authenticated
  using (user_id = auth.uid());

drop policy if exists "gpx_files_select_own" on storage.objects;
drop policy if exists "gpx_files_select_visible" on storage.objects;

create policy "gpx_files_select_visible"
  on storage.objects for select
  to authenticated
  using (
    bucket_id = 'gpx-files'
    and (
      (storage.foldername(name))[1] = auth.uid()::text
      or (storage.foldername(name))[1] = 'public'
    )
  );
