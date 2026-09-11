"""
app/api/v1/routers/auth.py — JWT auth endpoints.

Phase 0/1: shape-only implementation.
- /auth/login: accepts email+password, returns access + refresh tokens.
  In Phase 0/1 there's no user DB, so it accepts a single dev credential
  configured via env vars (DEV_USER_EMAIL / DEV_USER_PASSWORD / DEV_USER_ROLE)
  so /docs testing works. Real user lookup + bcrypt verify in Phase 2.
- /auth/refresh: accepts a refresh token (via JSON body), returns a new access token.

Rules: router never touches SQLAlchemy directly — delegates to auth_service (stub).
"""
import hmac
import logging
import time
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request, status

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
)
from app.schemas.auth import LoginRequest, LoginResponse, RefreshRequest, RefreshResponse
from app.schemas.common import ErrorEnvelope, UserRole

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Brute-force throttle on /auth/login ────────────────────────────────────────
# In-memory sliding window keyed by client IP. Single-process scope only (does
# not coordinate across replicas) — acceptable for the current single-instance
# deployment, and strictly better than the previous unlimited-attempt endpoint.
# A distributed deployment should move this to Redis (registry_service already
# holds a client) rather than widen the in-memory window.
_LOGIN_WINDOW_SECONDS = 300
_LOGIN_MAX_ATTEMPTS = 10
_login_attempts: dict[str, list[float]] = defaultdict(list)


def _enforce_login_rate_limit(client_ip: str) -> None:
    now = time.monotonic()
    attempts = _login_attempts[client_ip]
    attempts[:] = [t for t in attempts if now - t < _LOGIN_WINDOW_SECONDS]
    if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": {
                    "code": "TOO_MANY_ATTEMPTS",
                    "message": "Too many login attempts. Try again later.",
                    "details": {"retry_after_seconds": _LOGIN_WINDOW_SECONDS},
                }
            },
        )
    attempts.append(now)


def reset_login_rate_limit_state() -> None:
    """Test-only hook — clears the in-memory attempt log between test cases so
    a shared test-client IP doesn't accumulate attempts across unrelated
    tests. Not called from any production code path."""
    _login_attempts.clear()


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={
        401: {"model": ErrorEnvelope, "description": "Invalid credentials"},
    },
    summary="Obtain JWT access + refresh tokens",
)
async def login(body: LoginRequest, request: Request) -> LoginResponse:
    """
    Phase 0/1: authenticates against DEV_USER_* env vars (dev-only stub).
    Phase 2 will replace this with real Postgres user lookup + bcrypt verify.

    In production the dev user MUST be disabled by setting DEV_USER_PASSWORD
    to the empty string (see settings.validate_production_safety).
    """
    client_ip = request.client.host if request.client else "unknown"
    _enforce_login_rate_limit(client_ip)

    # ── Dev-only credential check via env-configurable settings ────────────
    dev_email = settings.dev_user_email.strip()
    dev_password = settings.dev_user_password
    dev_role_raw = settings.dev_user_role.strip()

    # Safety: in production we allow disabling the dev user entirely by
    # clearing DEV_USER_PASSWORD. Phase 2+ will have real users instead.
    if not dev_password:
        logger.warning("dev_user_disabled")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "AUTH_DISABLED",
                    "message": "Dev user is disabled. Use your provisioned account.",
                    "details": {},
                }
            },
        )

    try:
        dev_role = UserRole(dev_role_raw)
    except ValueError:
        dev_role = UserRole.investigator

    # Constant-time comparison — a plain `!=` leaks timing information
    # proportional to the matching-prefix length of the password guess.
    email_matches = hmac.compare_digest(body.email.encode("utf-8"), dev_email.encode("utf-8"))
    password_matches = hmac.compare_digest(
        body.password.encode("utf-8"), dev_password.encode("utf-8")
    )
    if not (email_matches and password_matches):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_CREDENTIALS",
                    "message": "Email or password is incorrect.",
                    "details": {},
                }
            },
        )

    access_token = create_access_token(subject=body.email, role=dev_role.value)
    refresh_token = create_refresh_token(subject=body.email, role=dev_role.value)

    logger.info("login_success", extra={"email": body.email, "role": dev_role.value})

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role=dev_role,
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    responses={
        401: {"model": ErrorEnvelope, "description": "Invalid or expired refresh token"},
    },
    summary="Exchange a refresh token for a new access token",
)
async def refresh(body: RefreshRequest) -> RefreshResponse:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Invalid or expired refresh token.",
                "details": {},
            }
        },
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = verify_refresh_token(body.refresh_token)
    except Exception:
        raise exc

    sub = payload.get("sub")
    role = payload.get("role")
    if not sub or not role:
        raise exc

    new_access_token = create_access_token(subject=sub, role=role)
    return RefreshResponse(access_token=new_access_token)
