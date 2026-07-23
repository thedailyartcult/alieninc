-- TDAC Core Schema: patrons
-- Denormalized patron profiles synced from auth.users + user_contexts

create table if not exists public.patrons (
  id uuid primary key,
  email text not null,
  name text,
  honorary_title text,
  subscription_tier text not null default 'standard',
  philosophical_context_md text,
  selected_worldviews text[] not null default '{}',
  source_materials jsonb not null default '[]'::jsonb,
  completed_topics text[] not null default '{}',
  context_update_count integer not null default 0,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_patrons_email on public.patrons(email);
create index if not exists idx_patrons_active on public.patrons(is_active);
create index if not exists idx_patrons_tier on public.patrons(subscription_tier);

alter table public.patrons enable row level security;

create policy "Users can view own patron record"
  on public.patrons for select
  using (auth.uid() = id);

create policy "Service role full access"
  on public.patrons for all
  using (true)
  with check (true);
