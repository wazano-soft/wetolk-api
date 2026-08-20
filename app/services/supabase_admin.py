import uuid

import httpx

from app.core.config import settings


def delete_auth_user(user_id: uuid.UUID) -> None:
    """RNF-03: borrado de cuenta completo -- borra al usuario en Supabase
    Auth. La fila en public.profiles ya se borró antes vía cascade (ver
    account.py); esto elimina la identidad de auth.users, sin la cual no
    puede volver a loguearse con el mismo email a menos que se registre de
    nuevo. Mismo patrón httpx-contra-/auth/v1/admin usado ad-hoc para
    limpiar usuarios de prueba durante esta sesión, promovido a código real."""
    res = httpx.delete(
        f"{settings.supabase_url}/auth/v1/admin/users/{user_id}",
        headers={
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
        },
        timeout=30,
    )
    res.raise_for_status()
