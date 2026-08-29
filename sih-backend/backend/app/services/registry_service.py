"""
app/services/registry_service.py — Redis Risk Registry for VASP Chokepoint (USP 2).

Key shape (PRD §9.4 / implementation.md Phase 2):
  risk:{chain}:{address} → {"score": float, "tier": str, "case_ref": str|null, "flagged_at": str, "ttl": int}

Latency target: p95 < 200ms (Redis only in hot path).
No Postgres or Neo4j synchronous calls allowed.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.core.config import get_settings
from app.schemas.common import AlertAction, RiskTier

logger = logging.getLogger(__name__)
settings = get_settings()

_redis_pool: Optional[Redis] = None


def get_redis_client() -> Redis:
    """Return a singleton Redis async client connection pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
        )
    return _redis_pool


async def close_redis() -> None:
    """Close Redis client pool on shutdown."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


def format_risk_key(chain: str, address: str) -> str:
    """Format Redis key for risk registry."""
    return f"risk:{chain.upper()}:{address.strip()}"


async def get_risk_entry(redis_client: Redis, chain: str, address: str) -> Optional[dict[str, Any]]:
    """Retrieve raw risk registry entry for a wallet address from Redis."""
    key = format_risk_key(chain, address)
    try:
        raw = await redis_client.get(key)
        if not raw:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning("redis_risk_registry_lookup_failed", extra={"key": key, "error": str(e)})
        return None


async def set_risk_entry(
    redis_client: Optional[Redis] = None,
    chain: str = "BTC",
    address: str = "",
    score: float = 0.0,
    tier: Any = RiskTier.low,
    case_ref: Optional[str] = None,
    ttl: int = 2592000,  # 30 days default TTL
) -> None:
    """Store or refresh a risk entry in the Redis risk registry."""
    client = redis_client if redis_client is not None else get_redis_client()
    key = format_risk_key(chain, address)
    payload = {
        "score": round(score, 3),
        "tier": tier.value if isinstance(tier, RiskTier) else tier,
        "case_ref": case_ref,
        "flagged_at": datetime.now(timezone.utc).isoformat(),
        "ttl": ttl,
    }
    await client.set(key, json.dumps(payload), ex=ttl)


def determine_action(score: float, tier_str: Optional[str] = None) -> AlertAction:
    """
    Determine allow / hold / block action based on risk score and tier.
    - score >= 0.85 or tier critical -> block
    - score >= 0.30 or tier high/medium -> hold
    - else -> allow
    """
    if tier_str:
        tier_str = tier_str.lower()
        if tier_str == RiskTier.critical.value:
            return AlertAction.block
        if tier_str in (RiskTier.high.value, RiskTier.medium.value):
            return AlertAction.hold
        if tier_str == RiskTier.low.value:
            return AlertAction.allow

    if score >= 0.85:
        return AlertAction.block
    if score >= 0.30:
        return AlertAction.hold
    return AlertAction.allow


async def check_wallet_hot_path(
    redis_client: Redis,
    chain: str,
    address: str,
    amount: float,
) -> Tuple[float, AlertAction, Optional[str]]:
    """
    Latency-critical hot path for VASP deposits.
    Single Redis GET lookup. Never blocks on Postgres or Neo4j.
    Returns: (risk_score, action, case_ref)
    """
    entry = await get_risk_entry(redis_client, chain, address)
    if not entry:
        # Default for unflagged addresses
        return 0.0, AlertAction.allow, None

    score = float(entry.get("score", 0.0))
    tier_str = entry.get("tier")
    case_ref = entry.get("case_ref")
    action = determine_action(score, tier_str)

    return score, action, case_ref
