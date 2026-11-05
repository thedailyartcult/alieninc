-- TDAC Core Schema: publisher_issues
-- Content issues/prompts per publisher worldview

create table if not exists public.publisher_issues (
  id uuid primary key default gen_random_uuid(),
  publisher_id text not null,
  title text not null,
  base_prompt text not null default '',
  worldview text,
  description text,
  is_published boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_publisher_issues_publisher on public.publisher_issues(publisher_id);
create index if not exists idx_publisher_issues_published on public.publisher_issues(is_published);

alter table public.publisher_issues enable row level security;

create policy "Authenticated users can view published issues"
  on public.publisher_issues for select
  using (is_published = true or auth.role() = 'service_role');

create policy "Service role full access"
  on public.publisher_issues for all
  using (true)
  with check (true);
