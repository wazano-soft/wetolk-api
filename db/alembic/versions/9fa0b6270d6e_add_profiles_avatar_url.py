"""add profiles.avatar_url, capture it in handle_new_user

Revision ID: 9fa0b6270d6e
Revises: d6a675d45c53
Create Date: 2026-08-27 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9fa0b6270d6e'
down_revision: Union[str, Sequence[str], None] = 'd6a675d45c53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'profiles',
        sa.Column('avatar_url', sa.Text(), nullable=True),
        schema='public',
    )
    # Mismo cuerpo que db/0001_init.sql, solo agrega v_avatar_url --
    # Google/LinkedIn lo mandan en raw_user_meta_data como avatar_url o
    # picture según el provider. El REVOKE EXECUTE de anon/authenticated
    # (ver d49b1feda36a) no toca la definición, sigue vigente.
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
        begin
          insert into public.profiles (id, full_name)
          values (new.id, v_full_name);

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
    op.drop_column('profiles', 'avatar_url', schema='public')
