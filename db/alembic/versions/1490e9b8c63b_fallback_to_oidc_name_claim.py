"""handle_new_user: fall back to the OIDC "name" claim (LinkedIn)

Revision ID: 1490e9b8c63b
Revises: 9fa0b6270d6e
Create Date: 2026-08-27 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1490e9b8c63b'
down_revision: Union[str, Sequence[str], None] = '9fa0b6270d6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # LinkedIn (OIDC estándar) manda el nombre en "name", no en
    # "full_name" -- solo Google manda full_name. Sin este fallback, todo
    # signup por LinkedIn caía directo al prefijo del email.
    op.execute(
        """
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
          values (
            new.id,
            lower(regexp_replace(v_full_name, '[^a-zA-Z0-9]+', '-', 'g'))
              || '-' || substr(gen_random_uuid()::text, 1, 4)
          );

          insert into public.candidate_tiers (candidate_id)
          select id from public.candidates where user_id = new.id;

          return new;
        end;
        $$;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        create or replace function public.handle_new_user()
        returns trigger
        language plpgsql
        security definer set search_path = public
        as $$
        declare
          v_full_name text := coalesce(
            new.raw_user_meta_data ->> 'full_name',
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
          values (
            new.id,
            lower(regexp_replace(v_full_name, '[^a-zA-Z0-9]+', '-', 'g'))
              || '-' || substr(gen_random_uuid()::text, 1, 4)
          );

          insert into public.candidate_tiers (candidate_id)
          select id from public.candidates where user_id = new.id;

          return new;
        end;
        $$;
        """
    )
