"""
app/services/osint_service.py — Structured OSINT lookup (USP 2 corroboration).

Public structured-source lookups for wallet addresses:
  * ransomwhe.re — ransomware family attribution (bulk JSON export, no API key)
  * Bitcoin Abuse — BTC address abuse reports (free-tier API key required)

Design constraints (docs/osint.md):
  - Structured fields only — no free-text parsing or conclusion derivation.
  - Evidence-only: raised visibility in /risk; does NOT change tier or score.
  - Bounded: no web crawlers, no unstructured parsing.
  - Out-of-scope: Etherscan nametag (Pro-Plus only), forum/social scraping.

Patterns mirror sanctions_service.py (in-memory seed + Redis cache + registry
consult) to stay consistent with the existing risk-service hot path.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx

from app.core.config import get_settings
from app.schemas.common import Chain, EvidenceDirection
from app.schemas.wallet import OsintEvidence, RiskEvidence

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Bundled snapshot ──────────────────────────────────────────────────────
# Compact ransomwhe.re export (address, blockchain, family, created_at, updated_at).
# Generated from https://api.ransomwhe.re/export by scripts/build_osint_snapshot.py.
_RANSOMWHE_RE_PATH = Path(__file__).resolve().parent.parent / "data" / "osint" / "ransomwhe_export.json"

# Map source blockchain labels to the app's Chain codes (ransomwhe.re uses
# lowercase names like "bitcoin"/"ethereum"; the app uses BTC/ETH).
_BLOCKCHAIN_TO_CHAIN = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "eth": "ETH",
    "btc": "BTC",
}


def _normalize_chain(chain: str) -> str:
    """Normalize a source blockchain label to the app's Chain code (BTC/ETH/...)."""
    key = chain.strip().lower()
    return _BLOCKCHAIN_TO_CHAIN.get(key, key.upper())

# ── Cache TTLs ────────────────────────────────────────────────────────────
OSINT_CACHE_TTL = 24 * 3600  # 24 hours — matches Celery sync cadence
BA_RATE_LIMIT_INTERVAL = 2.5  # seconds between Bitcoin Abuse live calls (30/min)


# ── Data model ────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class OsintHit:
    """One structured OSINT hit for an address — the core unit surfaced in /risk."""
    source: str       # "ransomwhe.re" | "bitcoinabuse"
    category: str     # ransomware family / abuse_type
    report_date: str  # ISO timestamp or ""
    detail: str       # short structured detail (family, count, etc.)
    reference_url: str = ""

    def to_osint_evidence(self) -> OsintEvidence:
        return OsintEvidence(
            source=self.source,
            category=self.category,
            report_date=self.report_date or None,
            detail=self.detail or None,
            reference_url=self.reference_url or None,
        )

    def to_risk_evidence(self) -> RiskEvidence:
        """Append as a RiskEvidence entry visible alongside SHAP evidence."""
        return RiskEvidence(
            feature_name=f"osint.{self.source}",
            contribution=0.0,
            direction=EvidenceDirection.increases_risk,
            detail=self.detail,
        )


# ── In-memory index ───────────────────────────────────────────────────────

_ransomwhe_index: dict[str, list[dict[str, str]]] = {}
_loaded = False


def _load_ransomwhe_index() -> dict[str, list[dict[str, str]]]:
    """Load and index the bundled ransomwhe.re snapshot (cached)."""
    global _ransomwhe_index, _loaded
    if _loaded:
        return _ransomwhe_index
    if not _RANSOMWHE_RE_PATH.exists():
        logger.warning("osint_ransomwhe_snapshot_missing", extra={"path": str(_RANSOMWHE_RE_PATH)})
        _ransomwhe_index = {}
        _loaded = True
        return _ransomwhe_index
    entries: list[dict] = json.loads(_RANSOMWHE_RE_PATH.read_text(encoding="utf-8"))
    for entry in entries:
        addr = entry["address"].strip().lower()
        chain_key = _normalize_chain(entry.get("blockchain", "bitcoin"))
        key = f"{chain_key}:{addr}"
        _ransomwhe_index.setdefault(key, []).append({
            "family": entry.get("family", ""),
            "created_at": entry.get("created_at", ""),
            "updated_at": entry.get("updated_at", ""),
        })
    _loaded = True
    logger.info(
        "osint_ransomwhe_loaded",
        extra={"entries": len(entries), "unique_keys": len(_ransomwhe_index)},
    )
    return _ransomwhe_index


def ransomwhe_address_count() -> int:
    """Number of unique address entries in the bundled snapshot."""
    return len(_load_ransomwhe_index())


# ── Redis cache helpers ───────────────────────────────────────────────────

def _osint_cache_key(chain: str, address: str) -> str:
    return f"osint:{chain.upper()}:{address.strip()}"


async def _cache_get(redis_client, chain: str, address: str) -> Optional[list[dict]]:
    key = _osint_cache_key(chain, address)
    raw = await redis_client.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def _cache_set(redis_client, chain: str, address: str, hits: list[dict]) -> None:
    key = _osint_cache_key(chain, address)
    await redis_client.set(key, json.dumps(hits, separators=(",", ":")), ex=OSINT_CACHE_TTL)


# ── Bitcoin Abuse live lookup ─────────────────────────────────────────────

_BA_BASE = "https://www.bitcoinabuse.com/api"
_last_ba_call: float = 0.0


async def _bitcoinabuse_check(address: str) -> list[dict]:
    """Live Bitcoin Abuse reports/check call. Returns list of hit dicts.

    Respects 30 req/min rate limit (1 call per 2.5s minimum).
    Returns empty list on 404 (no reports) or if no API key is configured.
    """
    global _last_ba_call
    api_key = settings.bitcoinabuse_api_key
    if not api_key:
        return []

    # Rate-limit enforcement
    now = time.monotonic()
    wait = BA_RATE_LIMIT_INTERVAL - (now - _last_ba_call)
    if wait > 0:
        import asyncio
        await asyncio.sleep(wait)
    _last_ba_call = time.monotonic()

    url = f"{_BA_BASE}/reports/check?address={quote(address, safe='')}&api_token={api_key}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
    except Exception as exc:
        logger.warning("bitcoinabuse_check_failed", extra={"address": address, "error": str(exc)})
        return []

    if resp.status_code == 404:
        return []
    if resp.status_code == 401:
        logger.error("bitcoinabuse_invalid_api_key")
        return []
    if resp.status_code == 429:
        logger.warning("bitcoinabuse_rate_limited", extra={"address": address})
        return []
    if resp.status_code != 200:
        logger.warning("bitcoinabuse_unexpected_status", extra={"status": resp.status_code, "address": address})
        return []

    try:
        body = resp.json()
    except Exception:
        return []

    reports = body.get("reports", [])
    count = body.get("count", 0)
    hits = []
    for rep in reports[:10]:  # cap at 10 hits per address
        hits.append({
            "source": "bitcoinabuse",
            "category": rep.get("abuse_type", "unknown"),
            "created_at": rep.get("created_at", ""),
            "description": "",
            "reports_count": str(count),
        })
    return hits


async def _bitcoinabuse_bulk_download() -> list[dict]:
    """Download Bitcoin Abuse bulk CSV (30d window) and return parsed hits.

    Only used by the Celery sync task — not the hot path.
    Returns empty list on failure or missing API key.
    """
    api_key = settings.bitcoinabuse_api_key
    if not api_key:
        return []
    url = f"{_BA_BASE}/download/30d?api_token={api_key}"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url)
    except Exception as exc:
        logger.warning("bitcoinabuse_bulk_download_failed", extra={"error": str(exc)})
        return []
    if resp.status_code != 200:
        logger.warning("bitcoinabuse_bulk_status", extra={"status": resp.status_code})
        return []
    import csv
    import io
    hits = []
    reader = csv.DictReader(io.StringIO(resp.text))
    for row in reader:
        hits.append({
            "address": row.get("address", "").strip(),
            "abuse_type": row.get("abuse_type", "unknown"),
            "created_at": row.get("created_at", ""),
            "reports_count": row.get("reports_count", "1"),
        })
    logger.info("bitcoinabuse_bulk_downloaded", extra={"hits": len(hits)})
    return hits


# ── Public API ────────────────────────────────────────────────────────────

async def lookup_address(chain: str | Chain, address: str, redis_client=None) -> list[OsintHit]:
    """Look up OSINT hits for an address across all configured sources.

    Priority: Redis cache → in-memory snapshot → Bitcoin Abuse live call.
    Returns structured OsintHit objects (never free text).
    """
    if not address or not address.strip():
        return []

    chain_key = chain.value if isinstance(chain, Chain) else chain.upper()
    addr = address.strip().lower()

    # 1. Redis cache
    cached_hits: list[OsintHit] = []
    if redis_client is not None:
        try:
            cached_raw = await _cache_get(redis_client, chain_key, addr)
            if cached_raw is not None:
                return [OsintHit(**h) for h in cached_raw]
        except Exception:
            pass

    # 2. In-memory ransomwhe.re index
    idx = _load_ransomwhe_index()
    rw_hits_raw = idx.get(f"{chain_key}:{addr}", [])

    hits: list[OsintHit] = []
    for h in rw_hits_raw:
        hits.append(OsintHit(
            source="ransomwhe.re",
            category=h.get("family", "unknown"),
            report_date=h.get("created_at", ""),
            detail=f"Ransomware family: {h.get('family', 'unknown')}",
            reference_url=f"https://ransomwhe.re/address/{addr}",
        ))

    # 3. Bitcoin Abuse live (BTC only, only if token configured)
    if chain_key == "BTC" and settings.bitcoinabuse_api_key:
        try:
            ba_raw = await _bitcoinabuse_check(addr)
            for h in ba_raw:
                hits.append(OsintHit(
                    source="bitcoinabuse",
                    category=h.get("category", "unknown"),
                    report_date=h.get("created_at", ""),
                    detail=f"{h.get('reports_count', '?')} reports",
                    reference_url=f"https://www.bitcoinabuse.com/reports/{addr}",
                ))
        except Exception:
            pass  # never break the hot path

    # 4. Cache to Redis
    if redis_client is not None and hits:
        try:
            await _cache_set(redis_client, chain_key, addr, [
                {"source": h.source, "category": h.category,
                 "report_date": h.report_date, "detail": h.detail,
                 "reference_url": h.reference_url}
                for h in hits
            ])
        except Exception:
            pass

    return hits


def rebuild_in_memory_index() -> int:
    """Force-reload the bundled snapshot (used by Celery sync task)."""
    global _loaded, _ransomwhe_index
    _loaded = False
    _ransomwhe_index = {}
    _load_ransomwhe_index()
    return ransomwhe_address_count()


_RANSOMWHE_EXPORT_URL = "https://api.ransomwhe.re/export"


async def refresh_snapshot_on_disk() -> int:
    """Re-download the ransomwhe.re bulk export and rewrite the bundled snapshot.

    Used by the Celery sync task to keep the committed asset current. On any
    failure the previous on-disk snapshot is retained (safe fail). Returns the
    number of entries written, or raises on failure so callers can catch.
    """
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(_RANSOMWHE_EXPORT_URL)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        raise

    entries = data.get("result", [])
    compact = [{
        "address": e["address"],
        "blockchain": e.get("blockchain", "bitcoin").lower(),
        "family": e.get("family", ""),
        "created_at": e.get("createdAt", ""),
        "updated_at": e.get("updatedAt", ""),
    } for e in entries]

    _RANSOMWHE_RE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file then rename for atomic swap (no partial snapshots).
    tmp = _RANSOMWHE_RE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(compact, separators=(",", ":")), encoding="utf-8")
    tmp.replace(_RANSOMWHE_RE_PATH)
    logger.info("osint_ransomwhe_snapshot_updated", extra={"entries": len(compact)})
    return len(compact)


# ── Seed Redis (startup / sync task) ─────────────────────────────────────

async def seed_redis(redis_client=None) -> int:
    """Write OSINT hits for all bundled addresses into Redis.

    Each key: osint:{chain}:{address} → JSON list of hits (OSINT_CACHE_TTL).
    Called by the Celery sync task and at startup for hot-path cache priming.
    """
    from app.services.registry_service import get_redis_client
    client = redis_client if redis_client is not None else get_redis_client()
    idx = _load_ransomwhe_index()
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
        cache_key = _osint_cache_key(chain, addr)
        try:
            await client.set(cache_key, json.dumps(hits, separators=(",", ":")), ex=OSINT_CACHE_TTL)
            count += 1
        except Exception:
            pass
    logger.info("osint_redis_seeded", extra={"count": count})
    return count
