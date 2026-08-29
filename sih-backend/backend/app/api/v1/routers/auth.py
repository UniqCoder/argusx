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
import logging

from fastapi import APIRouter, HTTPException, status

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


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={
        401: {"model": ErrorEnvelope, "description": "Invalid credentials"},
    },
    summary="Obtain JWT access + refresh tokens",
)
async def login(body: LoginRequest) -> LoginResponse:
    """
    Phase 0/1: authenticates against DEV_USER_* env vars (dev-only stub).
    Phase 2 will replace this with real Postgres user lookup + bcrypt verify.

    In production the dev user MUST be disabled by setting DEV_USER_PASSWORD
    to the empty string (see settings.validate_production_safety).
    """
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

    if body.email != dev_email or body.password != dev_password:
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
