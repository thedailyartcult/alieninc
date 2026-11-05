-- TDAC Core Schema: publishers
-- Publisher/worldview registry

create table if not exists public.publishers (
  id text primary key,
  name text not null,
  worldview text not null,
  description text,
  publisher_type text not null default 'secular',
  video_url text,
  image_url text,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

alter table public.publishers enable row level security;

create policy "Anyone can view active publishers"
  on public.publishers for select
  using (is_active = true);

create policy "Service role full access"
  on public.publishers for all
  using (true)
  with check (true);

-- Seed the 14 publishers from the website
insert into public.publishers (id, name, worldview, description, publisher_type) values
  ('nocturnal-school', 'The Nocturnal School', 'Becoming', 'Existential self-creation and radical freedom', 'secular'),
  ('atelier-obsidian', 'Atelier Obsidian', 'Existentialism', 'The weight of choice and the architecture of meaning', 'secular'),
  ('vellum-review', 'The Vellum Review', 'Stoicism', 'Endurance, duty, and the disciplined mind', 'secular'),
  ('friction-form', 'Friction & Form', 'Absurdism', 'Finding joy in the tension between seeking and silence', 'secular'),
  ('silent-spine', 'Silent Spine', 'The Leap', 'Kierkegaardian faith beyond reason', 'secular'),
  ('anima-mundi', 'Anima Mundi Press', 'Mysticism', 'The soul of the world and hidden correspondences', 'spiritual'),
  ('soma-thread', 'Soma & Thread', 'Eastern Wisdom', 'Buddhist, Taoist, and Hindu contemplative traditions', 'spiritual'),
  ('marrow-archive', 'Marrow Archive', 'Politics', 'Power, structure, and the material conditions of life', 'secular'),
  ('better-books', 'Better Books & Garments', 'Witness', 'Literary testimony and the examined life', 'secular'),
  ('guidepost-ministries', 'Guidepost Ministries', 'Christian Contemplative', 'Centering prayer and the cloud of unknowing', 'spiritual'),
  ('horsemag', 'HORSES', 'Wildness', 'Untamed expression and the beauty of the unbroken', 'secular'),
  ('immortality-projects', 'Immortality Projects', 'Legacy', 'Voice, memory, and what outlasts the body', 'secular'),
  ('thedailyartcult', 'The Daily Art Cult', 'Synthesis', 'The parent platform weaving all worldviews together', 'secular'),
  ('rousseau-press', 'Rousseau Press', 'Capital & Culture', 'Where resources meet meaning', 'secular')
on conflict (id) do update set
  name = excluded.name,
  worldview = excluded.worldview,
  description = excluded.description,
  publisher_type = excluded.publisher_type;
