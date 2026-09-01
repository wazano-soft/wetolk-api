"""handle_new_user: transliterate accents in the generated slug

Revision ID: f1a2b3c4d5e6
Revises: 784a571991f9
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = '784a571991f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# `regexp_replace(v_full_name, '[^a-zA-Z0-9]+', '-', 'g')` trataba cada letra
# acentuada como separador: "José Jesús" -> "jos-jes-s". Con translate() las
# pasamos a su equivalente ASCII ANTES del regexp ("José Jesús" -> "jose-jesus")
# y recortamos guiones de los extremos. No usamos la extensión `unaccent` para
# no tocar el `search_path = public` endurecido en d49b1feda36a ni depender de
# que exista el schema `extensions` en cada entorno.
_FROM = "áàäâãÁÀÄÂÃéèëêÉÈËÊíìïîÍÌÏÎóòöôõÓÒÖÔÕúùüûÚÙÜÛñÑçÇýÝ"
_TO = "aaaaaAAAAAeeeeEEEEiiiiIIIIoooooOOOOOuuuuUUUUnNcCyY"


def _handle_new_user_sql(slug_expr: str) -> str:
    return f"""
        create or replace function public.handle_new_user()
        returns trigger
        language plpgsql
        security definer set search_path = public
        as $$
        declare
          v_full_name text := coalesce(
            new.raw_user_meta_data ->> 'full_name',
            new.raw_user_meta_data ->> 'name',
            split_part(new.email, '@', 1)
          );
          v_avatar_url text := coalesce(
            new.raw_user_meta_data ->> 'avatar_url',
            new.raw_user_meta_data ->> 'picture'
          );
        begin
          insert into public.profiles (id, full_name, avatar_url)
          values (new.id, v_full_name, v_avatar_url);

          insert into public.candidates (user_id, slug)
          values (new.id, {slug_expr});

          insert into public.candidate_tiers (candidate_id)
          select id from public.candidates where user_id = new.id;

          return new;
        end;
        $$;
    """


_NEW_SLUG = (
    "lower(trim(both '-' from regexp_replace("
    f"translate(v_full_name, '{_FROM}', '{_TO}'), "
    "'[^a-zA-Z0-9]+', '-', 'g'))) "
    "|| '-' || substr(gen_random_uuid()::text, 1, 4)"
)
_OLD_SLUG = (
    "lower(regexp_replace(v_full_name, '[^a-zA-Z0-9]+', '-', 'g')) "
    "|| '-' || substr(gen_random_uuid()::text, 1, 4)"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(_handle_new_user_sql(_NEW_SLUG))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(_handle_new_user_sql(_OLD_SLUG))
