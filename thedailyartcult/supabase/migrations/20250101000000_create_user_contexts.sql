-- TDAC Core Schema: user_contexts
-- Patron philosophical context profiles

create table if not exists public.user_contexts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  markdown_text text not null default '',
  selected_worldviews text[] not null default '{}',
  source_materials jsonb not null default '[]'::jsonb,
  completed_topics text[] not null default '{}',
  last_reflection_summary text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_user_contexts_user on public.user_contexts(user_id);
create unique index if not exists idx_user_contexts_user_unique on public.user_contexts(user_id);

alter table public.user_contexts enable row level security;

create policy "Users can view own context"
  on public.user_contexts for select
  using (auth.uid() = user_id);

create policy "Users can update own context"
  on public.user_contexts for all
  using (auth.uid() = user_id);

create policy "Service role full access"
  on public.user_contexts for all
  using (true)
  with check (true);
