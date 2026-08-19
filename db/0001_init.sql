-- Vivae — schema inicial
-- Fuente: 03-documento-tecnico.md §3
-- Correr una sola vez en el SQL Editor de Supabase (proyecto ya creado).

create extension if not exists vector;
create extension if not exists pg_trgm;   -- búsqueda por texto (híbrida)

-- ─────────────────────────────────────────────────────────────
-- Perfil base (1:1 con auth.users)
-- ─────────────────────────────────────────────────────────────
create table public.profiles (
  id          uuid primary key references auth.users on delete cascade,
  role        text not null default 'candidate'
              check (role in ('candidate','recruiter','admin')),
  full_name   text,
  locale      text not null default 'es' check (locale in ('es','en')),
  created_at  timestamptz not null default now()
);

-- ─────────────────────────────────────────────────────────────
-- Candidato: perfil profesional
-- ─────────────────────────────────────────────────────────────
create table public.candidates (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null unique references public.profiles(id) on delete cascade,

  slug              text not null unique,          -- URL pública /a/{slug}
  storage_token     uuid not null unique default gen_random_uuid(),

  -- Datos del CV
  headline          text,                          -- "Engineering Manager"
  degree            text,
  overview          text,
  years_experience  numeric(4,1),
  years_experience_updated_at date,       -- fecha del último recálculo (job periódico, §13)
  skills            text[] not null default '{}',
  interests         text[] not null default '{}',

  -- Datos por formulario
  work_mode         text check (work_mode in ('remote','hybrid','onsite')),
  location_city     text,
  location_country  text,
  willing_relocate  boolean default false,
  salary_min        numeric(12,2),
  salary_max        numeric(12,2),
  salary_currency   text default 'MXN',

  -- Links
  linkedin_url      text,
  github_url        text,
  portfolio_url     text,

  -- Contacto (nunca expuesto sin consentimiento)
  contact_email     text,
  contact_phone     text,
  share_email       boolean not null default false,
  share_phone       boolean not null default false,

  -- Configuración del agente
  agent_language    text not null default 'es' check (agent_language in ('es','en')),
  is_public         boolean not null default true,   -- URL pública activa
  is_searchable     boolean not null default true,   -- aparece ante reclutadores

  -- Embedding del perfil completo, para matching de reclutador
  profile_embedding vector(512),

  status            text not null default 'draft'
                    check (status in ('draft','processing','ready','error')),
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

create index on public.candidates (slug);
create index on public.candidates (is_searchable, work_mode, location_country);
create index on public.candidates using gin (skills);

-- ─────────────────────────────────────────────────────────────
-- Documentos subidos
-- ─────────────────────────────────────────────────────────────
create table public.cv_documents (
  id            uuid primary key default gen_random_uuid(),
  candidate_id  uuid not null references public.candidates(id) on delete cascade,
  r2_key        text not null,
  filename      text not null,
  size_bytes    int not null,
  page_count    int,
  extracted     jsonb,                    -- JSON estructurado del parseo
  is_current    boolean not null default true,
  status        text not null default 'uploaded'
                check (status in ('uploaded','parsing','parsed','failed')),
  error_message text,
  created_at    timestamptz not null default now()
);

create index on public.cv_documents (candidate_id, is_current);

-- ─────────────────────────────────────────────────────────────
-- Chunks vectorizados
-- ─────────────────────────────────────────────────────────────
create table public.cv_chunks (
  id            bigserial primary key,
  candidate_id  uuid not null references public.candidates(id) on delete cascade,
  document_id   uuid references public.cv_documents(id) on delete cascade,

  section       text not null,      -- 'experience'|'education'|'project'|
                                    -- 'skills'|'overview'|'achievement'|'course'
  title         text,               -- "Engineering Manager @ Acme"
  content       text not null,      -- texto autocontenido del chunk
  metadata      jsonb default '{}', -- {company, start, end, tech[], ...}

  embedding     vector(512),
  token_count   int,
  created_at    timestamptz not null default now()
);

create index on public.cv_chunks (candidate_id);
create index on public.cv_chunks (section);

-- Índice vectorial: HNSW da mejor recall, IVFFlat usa menos RAM.
-- En free tier de Supabase, empezá con HNSW mientras el volumen sea bajo.
create index cv_chunks_embedding_idx on public.cv_chunks
  using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);

create index candidates_profile_embedding_idx on public.candidates
  using hnsw (profile_embedding vector_cosine_ops);

-- ─────────────────────────────────────────────────────────────
-- Preguntas rápidas (máx 5)
-- ─────────────────────────────────────────────────────────────
create table public.quick_questions (
  id            uuid primary key default gen_random_uuid(),
  candidate_id  uuid not null references public.candidates(id) on delete cascade,
  question      text not null check (char_length(question) <= 80),
  position      smallint not null check (position between 1 and 5),
  created_at    timestamptz not null default now(),
  unique (candidate_id, position)
);

-- ─────────────────────────────────────────────────────────────
-- Aporta o Comparte: nivel de desbloqueo
-- ─────────────────────────────────────────────────────────────
create table public.candidate_tiers (
  candidate_id     uuid primary key references public.candidates(id) on delete cascade,
  tier             text not null default 'base'
                   check (tier in ('base','impulso','alcance')),
  unlocked_by      text check (unlocked_by in ('donation','share','referrals','manual')),
  referral_count   int not null default 0,     -- visitas referidas válidas
  share_count      int not null default 0,
  donated_total    numeric(10,2) not null default 0,
  unlocked_at      timestamptz,
  updated_at       timestamptz not null default now()
);

-- Cada vez que el candidato comparte
create table public.shares (
  id            uuid primary key default gen_random_uuid(),
  candidate_id  uuid not null references public.candidates(id) on delete cascade,
  ref_token     text not null unique,          -- corto, url-safe (nanoid 10)
  channel       text not null
                check (channel in ('linkedin','x','whatsapp','facebook','copy','other')),
  created_at    timestamptz not null default now()
);

create index on public.shares (ref_token);
create index on public.shares (candidate_id);

-- Visitas atribuidas a un share
create table public.referral_visits (
  id            bigserial primary key,
  share_id      uuid not null references public.shares(id) on delete cascade,
  candidate_id  uuid not null references public.candidates(id) on delete cascade,
  visitor_hash  text not null,                 -- sha256(ip + ua + salt diaria)
  is_valid      boolean not null default false,-- true tras 10s de permanencia
  dwell_ms      int,
  visit_date    date not null default current_date,
  created_at    timestamptz not null default now()
);

-- una visita válida por visitante por candidato por día (columna real, no
-- expresión sobre created_at: ese cast no es IMMUTABLE, ver 03-documento-tecnico §3)
create unique index referral_visits_daily_unique
  on public.referral_visits (candidate_id, visitor_hash, visit_date);

create index on public.referral_visits (candidate_id, is_valid);

-- Donaciones (registro manual en MVP; webhook después)
create table public.contributions (
  id            uuid primary key default gen_random_uuid(),
  candidate_id  uuid references public.candidates(id) on delete set null,
  provider      text not null check (provider in ('stripe','mercadopago')),
  external_id   text unique,
  amount        numeric(10,2),
  currency      text default 'MXN',
  created_at    timestamptz not null default now()
);

-- ─────────────────────────────────────────────────────────────
-- Conversaciones del agente público (anónimas)
-- ─────────────────────────────────────────────────────────────
create table public.conversations (
  id             uuid primary key default gen_random_uuid(),
  candidate_id   uuid not null references public.candidates(id) on delete cascade,
  visitor_hash   text,                  -- hash de IP+UA, NO la IP
  langsmith_run  text,
  message_count  int not null default 0,
  created_at     timestamptz not null default now()
);

create table public.messages (
  id               bigserial primary key,
  conversation_id  uuid not null references public.conversations(id) on delete cascade,
  role             text not null check (role in ('user','assistant')),
  content          text not null,
  chunk_ids        bigint[],            -- trazabilidad: qué chunks se usaron
  created_at       timestamptz not null default now()
);

create index on public.messages (conversation_id, created_at);

-- ─────────────────────────────────────────────────────────────
-- FASE 2 — Reclutadores
-- ─────────────────────────────────────────────────────────────
create table public.recruiters (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null unique references public.profiles(id) on delete cascade,
  company      text,
  plan         text not null default 'free' check (plan in ('free','pro','team')),
  created_at   timestamptz not null default now()
);

create table public.searches (
  id            uuid primary key default gen_random_uuid(),
  recruiter_id  uuid not null references public.recruiters(id) on delete cascade,
  raw_query     text not null,
  parsed        jsonb,                  -- criterios extraídos
  results       jsonb,                  -- snapshot de los matches
  created_at    timestamptz not null default now()
);

create table public.contact_requests (
  id            uuid primary key default gen_random_uuid(),
  recruiter_id  uuid not null references public.recruiters(id) on delete cascade,
  candidate_id  uuid not null references public.candidates(id) on delete cascade,
  message       text not null,
  status        text not null default 'pending'
                check (status in ('pending','accepted','declined','revoked')),
  responded_at  timestamptz,
  created_at    timestamptz not null default now(),
  unique (recruiter_id, candidate_id)
);

-- ─────────────────────────────────────────────────────────────
-- Row Level Security
-- ─────────────────────────────────────────────────────────────
alter table public.candidates       enable row level security;
alter table public.cv_documents     enable row level security;
alter table public.cv_chunks        enable row level security;
alter table public.quick_questions  enable row level security;

-- El candidato gestiona lo suyo
create policy "own candidate row" on public.candidates
  for all using (auth.uid() = user_id);

-- Lectura pública SOLO de perfiles publicados, y solo campos no sensibles
-- (esto se expone vía una VIEW, no directo sobre la tabla)
create policy "public read published" on public.candidates
  for select using (is_public = true);

create policy "own documents" on public.cv_documents
  for all using (
    candidate_id in (select id from public.candidates where user_id = auth.uid())
  );

create policy "own chunks" on public.cv_chunks
  for all using (
    candidate_id in (select id from public.candidates where user_id = auth.uid())
  );

create policy "own questions" on public.quick_questions
  for all using (
    candidate_id in (select id from public.candidates where user_id = auth.uid())
  );

-- Vista pública — el frontend anónimo nunca toca columnas sensibles
create view public.public_profiles as
select id, slug, headline, degree, overview, years_experience,
       skills, interests, work_mode, location_city, location_country,
       linkedin_url, github_url, portfolio_url, agent_language
from public.candidates
where is_public = true;

-- ─────────────────────────────────────────────────────────────
-- Trigger: crear fila en candidates al registrarse (RF-01)
-- ─────────────────────────────────────────────────────────────
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, full_name)
  values (new.id, new.raw_user_meta_data ->> 'full_name');

  insert into public.candidates (user_id, slug)
  values (
    new.id,
    lower(regexp_replace(coalesce(new.raw_user_meta_data ->> 'full_name', 'user'), '[^a-zA-Z0-9]+', '-', 'g'))
      || '-' || substr(gen_random_uuid()::text, 1, 4)
  );

  insert into public.candidate_tiers (candidate_id)
  select id from public.candidates where user_id = new.id;

  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ─────────────────────────────────────────────────────────────
-- Función: búsqueda vectorial dentro del CV de un candidato (§5)
-- ─────────────────────────────────────────────────────────────
create or replace function match_cv_chunks(
  p_candidate_id uuid,
  p_embedding    vector(512),
  p_limit        int default 5
)
returns table (id bigint, section text, title text, content text, similarity float)
language sql stable as $$
  select c.id, c.section, c.title, c.content,
         1 - (c.embedding <=> p_embedding) as similarity
  from public.cv_chunks c
  where c.candidate_id = p_candidate_id
  order by c.embedding <=> p_embedding
  limit p_limit;
$$;
