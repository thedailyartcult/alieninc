-- TDAC Core Schema: commissions
-- Bespoke audio commission details submitted via gift card redemption

create table if not exists public.commissions (
  id uuid primary key default gen_random_uuid(),
  gift_code text not null,
  name text not null,
  email text not null,
  worldview text,
  prompt text not null default '',
  tone text,
  status text not null default 'pending',
  audio_release_id uuid references public.audio_releases(id),
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create index if not exists idx_commissions_gift_code on public.commissions(gift_code);
create index if not exists idx_commissions_status on public.commissions(status);
create index if not exists idx_commissions_email on public.commissions(email);

alter table public.commissions enable row level security;

create policy "Service role full access"
  on public.commissions for all
  using (true)
  with check (true);
