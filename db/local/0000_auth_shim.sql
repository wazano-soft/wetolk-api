-- Solo para el Postgres LOCAL de desarrollo. NUNCA correr esto en Supabase:
-- Supabase ya trae su propio schema `auth` real (GoTrue) y esto rompería
-- contra el suyo.
--
-- Emula lo mínimo de Supabase Auth que el schema de negocio (0001_init.sql)
-- necesita para correr sin cambios en local: la tabla auth.users (de la que
-- cuelga el FK de public.profiles y el trigger on_auth_user_created) y la
-- función auth.uid() que usan las políticas RLS.

create schema if not exists auth;

create table if not exists auth.users (
  id                  uuid primary key default gen_random_uuid(),
  email               text unique,
  raw_user_meta_data  jsonb not null default '{}',
  created_at          timestamptz not null default now()
);

-- En Supabase, PostgREST setea request.jwt.claim.sub en cada request a
-- partir del JWT verificado. En local, la app (o un script de seed) hace
-- `select set_config('request.jwt.claim.sub', '<user_id>', true)` por
-- transacción para simular al usuario autenticado.
create or replace function auth.uid() returns uuid
language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
