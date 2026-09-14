"""
app/services/explorers/http_client.py — One shared, pooled HTTP client for every
blockchain explorer.

WHY
---
Every explorer method used to open its own client:

    async with httpx.AsyncClient(timeout=self.timeout) as client:
        resp = await client.get(url, ...)

`async with` closes the client on exit, so the connection is torn down and the
next address pays for DNS, TCP and a full TLS handshake again. Against
blockstream.info / eth.blockscout.com / apilist.tronscanapi.com that is roughly
200-400 ms of pure setup added to *every node in every trace*, before a single
byte of transaction data moves. On a 35-node trace that is 7-14 seconds spent
on handshakes alone.

A module-level client with keep-alive reuses the connection across every
address in a trace, and across traces.

CONCURRENCY
-----------
Bounded PER HOST, not globally. The frontier prefetch is deliberately
concurrent, and without a bound a wide prefetch simply converts latency into
HTTP 429s — which the engine faithfully surfaces as EXPLORER_UNAVAILABLE
terminals, i.e. as lost data dressed up as a finding. That is a worse outcome
than being slow.

The limits differ per provider because the providers differ. Measured on a live
TRON trace: a single shared bound of 12 produced 12 of 18 nodes as
EXPLORER_UNAVAILABLE, because Tronscan's free tier rate-limits far sooner than
Blockstream or Blockscout. One number cannot be right for all three.

Raise a limit only with a measurement showing the provider tolerates it.

LIFECYCLE
---------
`aclose()` is called from the FastAPI lifespan shutdown. Scripts and tests that
never call it are fine: the client holds sockets, not a background task, and the
process exiting releases them.
"""
from __future__ import annotations

import asyncio
from typing import Optional
from urllib.parse import urlsplit

import httpx

# Keep-alive pool sized for the widest frontier prefetch plus headroom. These
# are *connections*, not concurrent requests — see _HOST_LIMITS for that.
_LIMITS = httpx.Limits(max_keepalive_connections=24, max_connections=48)

# The default; individual calls still pass their own timeout.
_DEFAULT_TIMEOUT = 8.0

# host substring -> max concurrent requests to that provider
_HOST_LIMITS: dict[str, int] = {
    "apilist.tronscanapi.com": 2,
    "eth.blockscout.com": 6,
    "blockstream.info": 8,
    "mempool.space": 8,
}
_DEFAULT_HOST_LIMIT = 4

# host substring -> minimum seconds between the START of two requests.
#
# Concurrency limits alone are not enough: Tronscan's free tier limits by
# request RATE, so even 3 concurrent requests that each complete in 200ms send
# ~15/s and get 429s. Measured on a live TRON trace, that lost 12 of 18 nodes to
# EXPLORER_UNAVAILABLE — the engine reporting an outage as a dead end, which
# looks exactly like a real finding. Pacing costs seconds; not pacing costs
# data.
#
# A key (TRONSCAN_API_KEY) raises the real limit substantially; this interval is
# the keyless floor.
_HOST_MIN_INTERVAL: dict[str, float] = {
    "apilist.tronscanapi.com": 0.35,
}

_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()
_semaphores: dict[str, asyncio.Semaphore] = {}
_pacers: dict[str, "_Pacer"] = {}
# The event loop the client/semaphores/pacer were created on. asyncio
# primitives are bound to the loop that creates them, and this module is a
# process-global singleton -- fine in production (one loop, one process), but
# pytest-asyncio hands each test its own loop by default. Without this check,
# request 2 in a test run reuses a client built on a now-closed loop and every
# explorer call fails silently into ExplorerUnavailableError, which is exactly
# the "the test just started failing with no code change to the thing under
# test" symptom this fixes.
_bound_loop: Optional[asyncio.AbstractEventLoop] = None


class _Pacer:
    """Serialises request starts for one host, `interval` apart."""

    def __init__(self, interval: float):
        self.interval = interval
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def wait(self) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            if now < self._next_at:
                await asyncio.sleep(self._next_at - now)
                now = loop.time()
            self._next_at = now + self.interval

DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Argus-Forensics/1.0",
}


async def get_client() -> httpx.AsyncClient:
    """The shared client, created once per event loop."""
    global _client, _bound_loop
    current_loop = asyncio.get_running_loop()
    if _bound_loop is not current_loop:
        # A new loop (a new test, a restarted worker) must not inherit
        # primitives bound to the old one -- reset everything together so a
        # stale semaphore or pacer never survives alongside a fresh client.
        async with _client_lock:
            if _bound_loop is not current_loop:
                if _client is not None and not _client.is_closed:
                    try:
                        await _client.aclose()
                    except Exception:
                        pass  # the old loop may already be gone
                _client = None
                _semaphores.clear()
                _pacers.clear()
                _bound_loop = current_loop
    if _client is None or _client.is_closed:
        async with _client_lock:
            if _client is None or _client.is_closed:
                _client = httpx.AsyncClient(
                    timeout=_DEFAULT_TIMEOUT,
                    limits=_LIMITS,
                    follow_redirects=True,
                    headers=DEFAULT_HEADERS,
                )
    return _client


def _host_of(url: str) -> str:
    return urlsplit(url).hostname or ""


def _get_semaphore(host: str) -> asyncio.Semaphore:
    # Created lazily rather than at import: a Semaphore binds to the running
    # loop on first use, and this module is imported long before one exists.
    sem = _semaphores.get(host)
    if sem is None:
        limit = next(
            (v for k, v in _HOST_LIMITS.items() if k in host), _DEFAULT_HOST_LIMIT
        )
        sem = asyncio.Semaphore(limit)
        _semaphores[host] = sem
    return sem


def _get_pacer(host: str) -> Optional["_Pacer"]:
    if host in _pacers:
        return _pacers[host]
    interval = next((v for k, v in _HOST_MIN_INTERVAL.items() if k in host), 0.0)
    pacer = _Pacer(interval) if interval > 0 else None
    if pacer is not None:
        _pacers[host] = pacer
    return pacer


async def get(url: str, *, timeout: float = _DEFAULT_TIMEOUT, **kwargs) -> httpx.Response:
    """A GET on the shared pooled client, under that host's concurrency and rate bounds."""
    client = await get_client()
    host = _host_of(url)
    async with _get_semaphore(host):
        pacer = _get_pacer(host)
        if pacer is not None:
            await pacer.wait()
        return await client.get(url, timeout=timeout, **kwargs)


async def aclose() -> None:
    """Close the pool. Called from the app's lifespan shutdown."""
    global _client, _bound_loop
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
    _bound_loop = None
    # Semaphores/pacer are bound to the loop that created them; a new loop
    # (tests, a restarted worker) must not inherit the old ones.
    _semaphores.clear()
    _pacers.clear()
