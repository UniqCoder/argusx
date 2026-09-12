"""
app/workers/tasks/_async_utils.py — Shared helper for running async coroutines
from synchronous Celery tasks.

Every task previously used `asyncio.get_event_loop()` + a `loop.is_running()`
check to decide how to run its async implementation. In a Celery worker there
is no event loop already running the task, so `is_running()` was always
False in practice, but the branch existed and — on the rare execution pool
where a loop *is* already running — silently dropped the work via
`asyncio.ensure_future(...)` without awaiting it, while still returning
`{"status": "queued"}` as if it had been scheduled and would complete.

A fresh `asyncio.run()` per call would fix that, but breaks a different real
thing: async clients with their own connection pools (the Neo4j driver in
app/graph/neo4j_client.py, in particular) are loop-bound — a driver created
under one event loop cannot be reused once that loop is gone ("Future
attached to a different loop"). So instead this keeps ONE event loop alive
for the lifetime of the worker process (matching what the old code
accidentally relied on via `get_event_loop()`'s implicit per-thread reuse),
and always synchronously drives the coroutine to completion — no
fire-and-forget branch, no dropped work.
"""
import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")

_worker_loop: asyncio.AbstractEventLoop | None = None


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
    return _worker_loop


def run_async(coro_factory: Callable[[], Awaitable[T]]) -> T:
    """Run an async task implementation to completion from sync Celery code,
    always on the same worker-process-lifetime event loop."""
    loop = _get_worker_loop()
    return loop.run_until_complete(coro_factory())
