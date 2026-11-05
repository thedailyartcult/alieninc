-- TDAC Core Schema: reflections
-- Denormalized reflection records synced from audio_releases

create table if not exists public.reflections (
  id uuid primary key default gen_random_uuid(),
  patron_id uuid not null references public.patrons(id) on delete cascade,
  publisher_id text not null references public.publishers(id),
  script_text text,
  audio_url text,
  storage_path text,
  duration_seconds integer,
  topic text,
  listened_percentage float not null default 0,
  is_complete boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_reflections_patron on public.reflections(patron_id);
create index if not exists idx_reflections_publisher on public.reflections(publisher_id);
create index if not exists idx_reflections_created on public.reflections(created_at desc);

alter table public.reflections enable row level security;

create policy "Users can view own reflections"
  on public.reflections for select
  using (auth.uid() = patron_id);

create policy "Service role full access"
  on public.reflections for all
  using (true)
  with check (true);
