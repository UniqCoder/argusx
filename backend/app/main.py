"""
app/main.py — FastAPI application entrypoint for Argus (SIH26183).

Architecture: routers/ → services/ → models/ + graph/ + nlp/ + ml/
Routers are the ONLY layer that speaks HTTP — services are framework-agnostic.

Startup sequence:
  1. configure_logging()
  2. Register all routers
  3. Attach global exception handler (standard error envelope on every failure)
  4. Mount /health

On shutdown:
  - Close Neo4j driver connection pool
  - Close Redis client pool
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.graph.neo4j_client import close_driver

# ── Routers ──────────────────────────────────────────────────────────────────
from app.api.v1.routers.auth import router as auth_router
from app.api.v1.routers.complaints import router as complaints_router
from app.api.v1.routers.wallets import router as wallets_router
from app.api.v1.routers.correlate import router as correlate_router
from app.api.v1.routers.check_wallet import router as check_wallet_router
from app.api.v1.routers.cases import router as cases_router
from app.api.v1.routers.alerts import router as alerts_router

configure_logging()
logger = logging.getLogger(__name__)
settings = get_settings()


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("argus_startup", extra={"version": settings.app_version})
    from app.services import registry_service, sanctions_service

    # Seed the curated OFAC SDN list into the Redis risk registry (best-effort,
    # fire-and-forget so startup is not blocked by Redis availability).
    asyncio.create_task(sanctions_service.ensure_redis_seeded())
    yield
    # Shutdown
    await close_driver()
    await registry_service.close_redis()
    logger.info("argus_shutdown")


# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Argus — Real-Time Crypto Fraud Attribution",
    description=(
        "SIH26183 · MHA/I4C · Blockchain & Cybersecurity\n\n"
        "All routes require `Authorization: Bearer <JWT>` except:\n"
        "- `POST /api/v1/auth/login` (no auth)\n"
        "- `POST /check-wallet` (X-API-Key header — VASP use only)\n"
        "- `GET /health` (no auth)\n\n"
        "Error envelope: `{ \"error\": { \"code\", \"message\", \"details\" } }`"
    ),
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── CORS (dev: allow all localhost/LAN origins; production: lock down) ────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ] if settings.app_env == "development" else [],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$" if settings.app_env == "development" else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

# ── Global exception handlers — standard envelope on every failure ──────────
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        content = exc.detail
    elif isinstance(exc.detail, dict):
        content = {
            "error": {
                "code": exc.detail.get("code", "HTTP_ERROR"),
                "message": exc.detail.get("message", str(exc.detail)),
                "details": exc.detail.get("details", {}),
            }
        }
    else:
        content = {
            "error": {
                "code": "HTTP_ERROR",
                "message": str(exc.detail),
                "details": {},
            }
        }
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=getattr(exc, "headers", None),
    )


from fastapi.encoders import jsonable_encoder

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": {"errors": jsonable_encoder(exc.errors())},
            }
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred.",
                "details": {},
            }
        },
    )


# ── Health endpoint ───────────────────────────────────────────────────────────
@app.get(
    "/health",
    tags=["health"],
    summary="Service health check",
    response_description="Returns 200 when the service is up",
)
async def health_check() -> dict[str, Any]:
    """
    Lightweight health check — no auth required.
    Reports connectivity to Postgres, Neo4j, and Redis.
    """
    import asyncio
    import redis.asyncio as aioredis
    from sqlalchemy import text

    service_status: dict[str, str] = {}

    # Postgres
    try:
        from app.db.session import engine
        async def _check_pg():
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        await asyncio.wait_for(_check_pg(), timeout=1.0)
        service_status["postgres"] = "ok"
    except Exception as e:
        logger.warning("health_postgres_down", extra={"error": str(e)})
        service_status["postgres"] = "down"

    # Redis
    try:
        async def _check_redis():
            r = aioredis.from_url(settings.redis_url, decode_responses=True)
            await r.ping()
            await r.aclose()
        await asyncio.wait_for(_check_redis(), timeout=1.0)
        service_status["redis"] = "ok"
    except Exception as e:
        logger.warning("health_redis_down", extra={"error": str(e)})
        service_status["redis"] = "down"

    # Neo4j
    try:
        from app.graph.neo4j_client import run_query
        await asyncio.wait_for(run_query("RETURN 1 AS ok"), timeout=1.0)
        service_status["neo4j"] = "ok"
    except Exception as e:
        logger.warning("health_neo4j_down", extra={"error": str(e)})
        service_status["neo4j"] = "down"

    overall = "ok" if all(v == "ok" for v in service_status.values()) else "degraded"

    return {
        "status": overall,
        "version": settings.app_version,
        "services": service_status,
    }


# ── Register routers ──────────────────────────────────────────────────────────
V1 = "/api/v1"

# Auth — no prefix beyond /auth (router adds /auth internally)
app.include_router(auth_router, prefix=V1)

# Resource routers — all under /api/v1/
app.include_router(complaints_router, prefix=V1)
app.include_router(wallets_router, prefix=V1)
app.include_router(correlate_router, prefix=V1)
app.include_router(cases_router, prefix=V1)
app.include_router(alerts_router, prefix=V1)

# VASP check-wallet — mounted at root /check-wallet (not /api/v1/)
# Uses X-API-Key auth, NOT JWT — see openapi.yaml for the security scheme split.
app.include_router(check_wallet_router)
