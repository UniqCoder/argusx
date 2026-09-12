"""
app/workers/tasks/osint_refresh.py — Structured OSINT bulk-sync Celery task.

Periodically pulls the public structured sources and refreshes the Redis OSINT
cache so /risk lookups stay fast (no per-request network):
  * ransomwhe.re — bulk JSON export (https://api.ransomwhe.re/export), no key.
  * Bitcoin Abuse — 30d bulk CSV, only if BITCOINABUSE_API_KEY is configured.

Fails safely: on any source error the previous cached data is retained and the
failure is logged; this task never blocks or breaks the risk hot path.
"""
import json
import structlog
from typing import Optional

from app.core.config import get_settings
from app.services import osint_service
from app.services.registry_service import get_redis_client
from app.workers.celery_app import celery_app
from app.workers.tasks._async_utils import run_async

logger = structlog.get_logger(__name__)
settings = get_settings()


async def _reload_ransomwhe_from_disk() -> int:
    """Force-reload the in-memory index from the bundled snapshot on disk."""
    return osint_service.rebuild_in_memory_index()


async def _refresh_ransomwhe_redis(redis_client) -> int:
    """Write hits for all bundled ransomwhe.re addresses into Redis."""
    idx = osint_service._load_ransomwhe_index()
    count = 0
    for composite_key, entries in idx.items():
        chain, addr = composite_key.split(":", 1)
        hits = [
            {"source": "ransomwhe.re", "category": e.get("family", ""),
             "report_date": e.get("created_at", ""),
             "detail": f"Ransomware family: {e.get('family', 'unknown')}",
             "reference_url": f"https://ransomwhe.re/address/{addr}"}
            for e in entries
        ]
        cache_key = osint_service._osint_cache_key(chain, addr)
        try:
            await redis_client.set(cache_key, json.dumps(hits, separators=(",", ":")), ex=osint_service.OSINT_CACHE_TTL)
            count += 1
        except Exception:
            pass
    return count


async def _refresh_bitcoinabuse_redis(redis_client) -> int:
    """Fetch Bitcoin Abuse 30d bulk CSV and prime its addresses into Redis."""
    if not settings.bitcoinabuse_api_key:
        return 0
    hits = await osint_service._bitcoinabuse_bulk_download()
    count = 0
    for h in hits:
        addr = h.get("address", "")
        if not addr:
            continue
        cache_key = osint_service._osint_cache_key("BTC", addr)
        payload = [{
            "source": "bitcoinabuse",
            "category": h.get("abuse_type", "unknown"),
            "report_date": h.get("created_at", ""),
            "detail": f"{h.get('reports_count', '1')} reports",
            "reference_url": f"https://www.bitcoinabuse.com/reports/{addr}",
        }]
        try:
            await redis_client.set(cache_key, json.dumps(payload, separators=(",", ":")), ex=osint_service.OSINT_CACHE_TTL)
            count += 1
        except Exception:
            pass
    return count


async def _sync_async() -> dict:
    redis_client = get_redis_client()

    # ranswomwhe.re — reload snapshot + re-prime Redis cache
    rw_redis = 0
    try:
        # Re-download the latest bulk export and overwrite the bundled snapshot
        # on disk (keeps the committed asset current). On any live failure we
        # retain whatever exists on disk.
        await osint_service.refresh_snapshot_on_disk()
        rw_index_count = await _reload_ransomwhe_from_disk()
        rw_redis = await _refresh_ransomwhe_redis(redis_client)
    except Exception as exc:
        logger.warning("osint_ransomwhe_sync_failed", error=str(exc))
        rw_index_count = osint_service.ransomwhe_address_count()

    # Bitcoin Abuse — bulk CSV (no-op if key not configured)
    try:
        ba_redis = await _refresh_bitcoinabuse_redis(redis_client)
    except Exception as exc:
        logger.warning("osint_bitcoinabuse_sync_failed", error=str(exc))
        ba_redis = 0

    logger.info(
        "osint_sync_completed",
        ransomwhe_indexed=rw_index_count,
        ransomwhe_redis_keys=rw_redis,
        bitcoinabuse_redis_keys=ba_redis,
    )
    return {
        "ransomwhe_indexed": rw_index_count,
        "ransomwhe_redis_keys": rw_redis,
        "bitcoinabuse_redis_keys": ba_redis,
        "status": "completed",
    }


@celery_app.task(name="app.workers.tasks.osint_refresh.sync_osint_sources")
def sync_osint_sources() -> dict:
    """Celery task: refresh structured OSINT cache from public sources."""
    return run_async(_sync_async)
