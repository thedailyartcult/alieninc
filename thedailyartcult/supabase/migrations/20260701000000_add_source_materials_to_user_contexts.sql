alter table public.user_contexts
  add column if not exists source_materials jsonb not null default '[]'::jsonb;
