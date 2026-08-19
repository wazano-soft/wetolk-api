from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

security = HTTPBearer()

# PyJWKClient cachea las claves internamente (respeta el mismo TTL que
# Supabase expone en el endpoint), así que un solo cliente a nivel de
# módulo alcanza — no hay que resolver el JWKS en cada request.
_jwks_client = jwt.PyJWKClient(
    f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
)


@dataclass
class AuthUser:
    id: str
    email: str | None
    full_name: str | None


def _decode(token: str) -> dict:
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthUser:
    payload = _decode(credentials.credentials)
    return AuthUser(
        id=payload["sub"],
        email=payload.get("email"),
        full_name=(payload.get("user_metadata") or {}).get("full_name"),
    )


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    return _decode(credentials.credentials)["sub"]
