-- TDAC Core Schema: gift_codes
-- Bespoke gift card codes for commission redemption

create table if not exists public.gift_codes (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  is_redeemed boolean not null default false,
  redeemed_by uuid references auth.users(id),
  redeemed_at timestamptz,
  created_at timestamptz not null default now(),
  expires_at timestamptz
);

create index if not exists idx_gift_codes_code on public.gift_codes(code);
create index if not exists idx_gift_codes_redeemed on public.gift_codes(is_redeemed);

alter table public.gift_codes enable row level security;

create policy "Anyone can check code status"
  on public.gift_codes for select
  using (true);

create policy "Service role full access"
  on public.gift_codes for all
  using (true)
  with check (true);
