-- TDAC Core Schema: audio_releases
-- Generated reflection audio files linked to patrons

create table if not exists public.audio_releases (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  issue_id uuid,
  title text not null default '',
  description text,
  storage_path text not null,
  duration_seconds integer,
  topic text,
  publisher_id text,
  created_at timestamptz not null default now()
);

create index if not exists idx_audio_releases_user on public.audio_releases(user_id);
create index if not exists idx_audio_releases_created on public.audio_releases(created_at desc);

alter table public.audio_releases enable row level security;

create policy "Users can view own releases"
  on public.audio_releases for select
  using (auth.uid() = user_id);

create policy "Service role full access"
  on public.audio_releases for all
  using (true)
  with check (true);
