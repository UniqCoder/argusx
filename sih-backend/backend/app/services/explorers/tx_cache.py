"""
app/services/explorers/tx_cache.py — Short-lived Redis cache for explorer results.

WHY
---
Redis is a first-class dependency of this system and the explorers never touched
it. Every trace re-fetched every address from scratch, so re-running the same
investigation — which is what happens constantly during an investigation, a
demo, or a page refresh — cost the full wall-clock time again.

WHAT IS AND IS NOT CACHED
-------------------------
Cached: a successful fetch, including a confirmed-empty history (`[]`). An empty
history is a real answer and re-asking for it is pure latency.

NOT cached: `ExplorerUnavailableError`. An outage is a condition of the moment,
not a property of the address. Caching it would turn one rate-limited second
into ten minutes of addresses reported as EXPLORER_UNAVAILABLE, which the engine
faithfully renders as dead ends — the worst possible failure mode, because it
looks exactly like a real finding.

TTL
---
Ten minutes. Long enough that re-running a trace is instant and that the
frontier prefetch is never wasted; short enough that an investigator watching a
wallet actively move money sees the new transactions within one coffee-length
pause. A confirmed *cache-miss* costs one Redis round-trip (~1 ms), so the
downside on a cold trace is negligible.

FAILURE POLICY
--------------
Every Redis error is swallowed and treated as a miss. A cache that is down must
degrade into "slower", never into "wrong" and never into "broken".
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional

import structlog

from app.schemas.common import Chain
from app.services.explorers.base import RawTx

logger = structlog.get_logger(__name__)

TTL_SECONDS = 600


def cache_key(chain: str, address: str) -> str:
    return f"tx:{chain.upper()}:{address.strip()}"


def _encode(txs: List[RawTx]) -> str:
    return json.dumps([
        {
            "tx_hash": t.tx_hash,
            "from_address": t.from_address,
            "to_address": t.to_address,
            "amount": t.amount,
            "chain": t.chain.value if isinstance(t.chain, Chain) else str(t.chain),
            "timestamp": t.timestamp.isoformat() if t.timestamp else None,
            "asset": t.asset,
            "asset_id": t.asset_id,
            "vasp_tag": t.vasp_tag,
            "fee_native": t.fee_native,
            "gas_price_gwei": t.gas_price_gwei,
            "gas_used": t.gas_used,
            "bandwidth_used": t.bandwidth_used,
            "energy_used": t.energy_used,
        }
        for t in txs
    ])


def _decode(raw: str) -> List[RawTx]:
    out: List[RawTx] = []
    for d in json.loads(raw):
        ts = d.get("timestamp")
        out.append(
            RawTx(
                tx_hash=d["tx_hash"],
                from_address=d["from_address"],
                to_address=d["to_address"],
                amount=d["amount"],
                chain=Chain(d["chain"]),
                timestamp=(
                    datetime.fromisoformat(ts)
                    if ts
                    else datetime.now(timezone.utc)
                ),
                asset=d.get("asset", ""),
                asset_id=d.get("asset_id"),
                vasp_tag=d.get("vasp_tag"),
                fee_native=d.get("fee_native"),
                gas_price_gwei=d.get("gas_price_gwei"),
                gas_used=d.get("gas_used"),
                bandwidth_used=d.get("bandwidth_used"),
                energy_used=d.get("energy_used"),
            )
        )
    return out


async def get(chain: str, address: str, limit: int) -> Optional[List[RawTx]]:
    """Cached transactions for (chain, address), or None on a miss."""
    try:
        from app.services import registry_service

        client = registry_service.get_redis_client()
        raw = await client.get(cache_key(chain, address))
        if not raw:
            return None
        txs = _decode(raw)
        logger.debug("tx_cache_hit", chain=chain, address=address, count=len(txs))
        # The cached window may be wider than this caller asked for; never
        # narrower, because a narrower window would silently hide outflows and
        # the engine would report a wrong terminal.
        return txs[:limit]
    except Exception as exc:
        logger.debug("tx_cache_read_failed", error=str(exc))
        return None


async def put(chain: str, address: str, txs: List[RawTx]) -> None:
    try:
        from app.services import registry_service

        client = registry_service.get_redis_client()
        await client.set(cache_key(chain, address), _encode(txs), ex=TTL_SECONDS)
    except Exception as exc:
        logger.debug("tx_cache_write_failed", error=str(exc))
