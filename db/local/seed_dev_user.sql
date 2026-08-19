-- Solo local. Crea un usuario de prueba y dispara el mismo trigger que en
-- Supabase (on_auth_user_created), así queda un candidate + candidate_tiers
-- listos para desarrollar sin pasar por un login real.

insert into auth.users (email, raw_user_meta_data)
values ('dev@vivae.local', '{"full_name": "Dev User"}')
returning id;
