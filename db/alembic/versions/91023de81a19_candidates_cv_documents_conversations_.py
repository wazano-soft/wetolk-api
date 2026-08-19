"""candidates/cv_documents/conversations: bigserial id + separate token

Regla de plataforma: id interno incremental para joins/FKs, y un UUID
separado (`token`) para lo que se expone a clientes externos. Ver
03-documento-tecnico.md §1.

Todo lo que hay en estas tablas hoy es data de prueba (2 candidatos
descartables, nada más) en los tres ambientes -- no hay usuarios reales
todavía en ningún lado. Truncar y recrear tipos es más simple y seguro
que intentar castear UUIDs existentes a bigint (no hay cast razonable
entre los dos).

Revision ID: 91023de81a19
Revises: 541a280c0570
Create Date: 2026-08-19 16:13:02.078261

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '91023de81a19'
down_revision: Union[str, Sequence[str], None] = '541a280c0570'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UPGRADE_SQL = """
truncate table public.candidates cascade;

drop policy "own documents" on public.cv_documents;
drop policy "own chunks" on public.cv_chunks;
drop policy "own questions" on public.quick_questions;

drop function if exists match_cv_chunks(uuid, vector(512), int);

-- ── candidates.id: uuid -> bigserial, + columna token nueva ────────────
-- cascade se lleva puestos: el PK viejo, las FK de las 9 tablas
-- dependientes (candidate_id sigue existiendo como columna suelta en
-- cada una, se retipa a continuación), y la vista public_profiles.
alter table public.candidates drop column id cascade;
alter table public.candidates add column id bigint generated always as identity primary key;
alter table public.candidates add column token uuid not null unique default gen_random_uuid();

-- ── candidate_id en cada tabla dependiente: uuid -> bigint ─────────────
alter table public.cv_documents drop column candidate_id cascade;
alter table public.cv_documents add column candidate_id bigint not null
  references public.candidates(id) on delete cascade;

alter table public.cv_chunks drop column candidate_id cascade;
alter table public.cv_chunks add column candidate_id bigint not null
  references public.candidates(id) on delete cascade;

alter table public.quick_questions drop column candidate_id cascade;
alter table public.quick_questions add column candidate_id bigint not null
  references public.candidates(id) on delete cascade;
alter table public.quick_questions
  add constraint quick_questions_candidate_id_position_key unique (candidate_id, position);

alter table public.candidate_tiers drop column candidate_id cascade;
alter table public.candidate_tiers add column candidate_id bigint primary key
  references public.candidates(id) on delete cascade;

alter table public.shares drop column candidate_id cascade;
alter table public.shares add column candidate_id bigint not null
  references public.candidates(id) on delete cascade;

alter table public.referral_visits drop column candidate_id cascade;
alter table public.referral_visits add column candidate_id bigint not null
  references public.candidates(id) on delete cascade;

alter table public.contributions drop column candidate_id cascade;
alter table public.contributions add column candidate_id bigint
  references public.candidates(id) on delete set null;

alter table public.conversations drop column candidate_id cascade;
alter table public.conversations add column candidate_id bigint not null
  references public.candidates(id) on delete cascade;

alter table public.contact_requests drop column candidate_id cascade;
alter table public.contact_requests add column candidate_id bigint not null
  references public.candidates(id) on delete cascade;
alter table public.contact_requests
  add constraint contact_requests_recruiter_id_candidate_id_key unique (recruiter_id, candidate_id);

-- ── cv_documents.id: uuid -> bigserial, + token ────────────────────────
-- cascade se lleva puesta la FK de cv_chunks.document_id (la columna
-- queda, se retipa a continuación).
alter table public.cv_documents drop column id cascade;
alter table public.cv_documents add column id bigint generated always as identity primary key;
alter table public.cv_documents add column token uuid not null unique default gen_random_uuid();

alter table public.cv_chunks drop column document_id cascade;
alter table public.cv_chunks add column document_id bigint
  references public.cv_documents(id) on delete cascade;

-- ── conversations.id: uuid -> bigserial, + token ───────────────────────
-- cascade se lleva puesta la FK de messages.conversation_id.
alter table public.conversations drop column id cascade;
alter table public.conversations add column id bigint generated always as identity primary key;
alter table public.conversations add column token uuid not null unique default gen_random_uuid();

alter table public.messages drop column conversation_id cascade;
alter table public.messages add column conversation_id bigint not null
  references public.conversations(id) on delete cascade;

-- ── Recrear lo que se cayó en cascada ───────────────────────────────────
create index cv_documents_candidate_id_is_current_idx on public.cv_documents (candidate_id, is_current);
create index cv_chunks_candidate_id_idx on public.cv_chunks (candidate_id);
create unique index referral_visits_daily_unique
  on public.referral_visits (candidate_id, visitor_hash, visit_date);
create index referral_visits_candidate_id_is_valid_idx on public.referral_visits (candidate_id, is_valid);
create index shares_candidate_id_idx on public.shares (candidate_id);
create index messages_conversation_id_created_at_idx on public.messages (conversation_id, created_at);

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

create or replace function match_cv_chunks(
  p_candidate_id bigint,
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

create or replace view public.public_profiles as
select id, slug, headline, degree, overview, years_experience,
       skills, interests, work_mode, location_city, location_country,
       linkedin_url, github_url, portfolio_url, agent_language
from public.candidates
where is_public = true;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    raise NotImplementedError(
        "No hay downgrade -- el cambio de uuid a bigint no es reversible sin "
        "perder datos. Restaurar desde un backup si hace falta volver atrás."
    )
