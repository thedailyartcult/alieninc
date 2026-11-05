-- TDAC Core Schema: listening_logs
-- Logs from the landing page conversational studio sessions

create table if not exists public.listening_logs (
  id uuid primary key default gen_random_uuid(),
  q1_carrying text,
  q2_state text,
  q3_goal text,
  worldview text,
  philosopher text,
  assigned_territory text,
  ai_script text,
  patron_name text,
  patron_title text,
  email text,
  created_at timestamptz not null default now()
);

create index if not exists idx_listening_logs_created on public.listening_logs(created_at desc);

alter table public.listening_logs enable row level security;

create policy "Service role full access"
  on public.listening_logs for all
  using (true)
  with check (true);
