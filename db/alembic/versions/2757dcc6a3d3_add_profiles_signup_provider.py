"""add profiles.signup_provider, capture it in handle_new_user

Revision ID: 2757dcc6a3d3
Revises: 1490e9b8c63b
Create Date: 2026-08-27 14:15:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2757dcc6a3d3'
down_revision: Union[str, Sequence[str], None] = '1490e9b8c63b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'profiles',
        sa.Column('signup_provider', sa.Text(), nullable=True),
        schema='public',
    )
    # Backfill de las cuentas ya existentes -- Supabase lo tiene guardado en
    # auth.users.raw_app_meta_data.provider desde siempre, esto solo lo
    # copia una vez para las filas que ya estaban acá antes de esta columna.
    # Solo corre si auth.users vive en esta misma base (Supabase real, no
    # local) -- si no existe la tabla, el UPDATE simplemente no matchea
    # nada en vez de romper.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_schema = 'auth' AND table_name = 'users'
                  AND column_name = 'raw_app_meta_data'
            ) THEN
                UPDATE public.profiles p
                SET signup_provider = u.raw_app_meta_data ->> 'provider'
                FROM auth.users u
                WHERE u.id = p.id AND p.signup_provider IS NULL;
            END IF;
        END $$;
        """
    )
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
          insert into public.profiles (id, full_name, avatar_url, signup_provider)
          values (new.id, v_full_name, v_avatar_url, new.raw_app_meta_data ->> 'provider');

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
    op.drop_column('profiles', 'signup_provider', schema='public')
