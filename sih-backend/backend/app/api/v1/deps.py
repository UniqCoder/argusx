"""
app/api/v1/deps.py — Shared FastAPI dependencies.

Phase 0: auth guard is a shape-only stub — it validates the JWT signature and
extracts the subject/role, but does NOT yet enforce per-endpoint role restrictions.
Full RBAC middleware comes in Phase 2.

Usage in routers:
    from app.api.v1.deps import require_auth, require_vasp_key

    @router.get("/something")
    async def endpoint(current_user: CurrentUser = Depends(require_auth)):
        ...
"""
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.security import verify_access_token
from app.schemas.common import UserRole

settings = get_settings()

# ── JWT bearer (all /api/v1/... routes except login) ─────────────────────────
_bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser:
    """Decoded JWT payload, attached to the request by require_auth."""
    def __init__(self, sub: str, role: str):
        self.sub = sub
        self.role = UserRole(role)


async def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> CurrentUser:
    """
    Validates the JWT access token. Returns a CurrentUser on success.
    Raises 401 on missing or invalid/expired token.

    Phase 2 will layer role checks on top of this.
    """
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Missing or invalid authentication token.",
                "details": {},
            }
        },
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or not credentials.credentials:
        raise exc
    try:
        payload = verify_access_token(credentials.credentials)
    except Exception:
        raise exc

    sub = payload.get("sub")
    role = payload.get("role")
    if not sub or not role:
        raise exc
    return CurrentUser(sub=sub, role=role)


CurrentUserDep = Annotated[CurrentUser, Depends(require_auth)]

# ── VASP API key (for /check-wallet only) ─────────────────────────────────────
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_vasp_key(
    api_key: Annotated[str | None, Security(_api_key_header)],
) -> str:
    """
    Validates the X-API-Key header against the configured VASP key set.
    Raises 401 on missing/invalid key.

    This dependency is used ONLY on /check-wallet — never on JWT-guarded routes.
    """
    if not api_key or api_key not in settings.vasp_api_keys_set:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_API_KEY",
                    "message": "The provided X-API-Key is not recognised.",
                    "details": {},
                }
            },
        )
    return api_key


VaspKeyDep = Annotated[str, Depends(require_vasp_key)]
