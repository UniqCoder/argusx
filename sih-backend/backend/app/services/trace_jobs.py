"""
app/services/trace_jobs.py — Traces you can watch while they run.

WHY
---
`POST /api/v1/engine/trace` runs propagation inline and returns once. A live
wallet takes tens of seconds because every hop is a public-explorer round trip,
and for all of that time the investigator saw a spinner and no information —
not how deep it had got, not how much money it was following, not whether it had
already found a mixer. A trace that is 80% done looks exactly like one that has
hung.

Nothing about the engine changes here. The BFS stays sequential and
value-ordered, which is what makes `reproducible_hash` mean anything; this just
lets someone watch it happen. The observer never steers.

STORAGE
-------
In-process. A job's full event history lives in memory on the instance that
started it, which has one real consequence: **the SSE stream must reach the same
process that started the job.** That is true in this deployment (one uvicorn
process) and would need sticky routing behind a load balancer. It is stated here
rather than discovered later.

The durable record is unaffected — the trace, its nodes, the decision and the
ledger entries are written to Postgres exactly as the synchronous endpoint
writes them, by the same `trace_runner.persist_trace`. A job is a view of work
in progress, never the record of it.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal, Optional

import structlog

logger = structlog.get_logger(__name__)

JobStatus = Literal["running", "completed", "failed"]

# How long a finished job's events stay replayable. Long enough for a page
# refresh or a brief disconnect to recover the whole stream; short enough that
# a long-running instance does not accumulate traces in memory.
_RETENTION_SECONDS = 900
_MAX_JOBS = 200


@dataclass
class TraceJob:
    id: str
    status: JobStatus = "running"
    # The full ordered history. Kept (rather than only pushed to a queue) so a
    # subscriber that connects late, or reconnects, still receives every node
    # from the beginning instead of joining mid-graph.
    events: list[dict[str, Any]] = field(default_factory=list)
    result: Optional[dict[str, Any]] = None
    error: Optional[dict[str, str]] = None
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    # Signalled on every append; subscribers await it instead of polling.
    _tick: asyncio.Event = field(default_factory=asyncio.Event)

    def append(self, event_type: str, data: dict[str, Any]) -> None:
        self.events.append({"type": event_type, "data": data})
        self._tick.set()
        self._tick.clear()

    def finish(self, result: dict[str, Any]) -> None:
        self.result = result
        self.status = "completed"
        self.finished_at = time.time()
        self.append("done", result)

    def fail(self, code: str, message: str) -> None:
        self.error = {"code": code, "message": message}
        self.status = "failed"
        self.finished_at = time.time()
        self.append("error", self.error)


_jobs: dict[str, TraceJob] = {}


def _evict_stale() -> None:
    now = time.time()
    stale = [
        jid
        for jid, job in _jobs.items()
        if job.finished_at is not None and now - job.finished_at > _RETENTION_SECONDS
    ]
    for jid in stale:
        _jobs.pop(jid, None)
    # Hard ceiling, oldest first, in case a flood of jobs arrives inside the
    # retention window.
    if len(_jobs) > _MAX_JOBS:
        for jid, _ in sorted(_jobs.items(), key=lambda kv: kv[1].created_at)[
            : len(_jobs) - _MAX_JOBS
        ]:
            _jobs.pop(jid, None)


def create_job() -> TraceJob:
    _evict_stale()
    job = TraceJob(id=str(uuid.uuid4()))
    _jobs[job.id] = job
    return job


def get_job(job_id: str) -> Optional[TraceJob]:
    return _jobs.get(job_id)


async def subscribe(job: TraceJob) -> AsyncIterator[dict[str, Any]]:
    """
    Every event for `job`, from the beginning, until it finishes.

    Replaying from index 0 means a subscriber that connects a second after the
    job started still builds the identical graph — there is no "missed the first
    nodes" state to handle on the client.
    """
    index = 0
    while True:
        while index < len(job.events):
            yield job.events[index]
            index += 1
        if job.status != "running":
            return
        try:
            await asyncio.wait_for(job._tick.wait(), timeout=20.0)
        except asyncio.TimeoutError:
            # A keep-alive, so an idle proxy does not close a stream that is
            # legitimately waiting on a slow explorer.
            yield {"type": "heartbeat", "data": {"status": job.status}}


def snapshot(job: TraceJob) -> dict[str, Any]:
    """Polling fallback for a client that cannot hold an SSE connection open."""
    return {
        "job_id": job.id,
        "status": job.status,
        "event_count": len(job.events),
        "nodes": [e["data"] for e in job.events if e["type"] == "node"],
        "progress": next(
            (e["data"] for e in reversed(job.events) if e["type"] == "progress"),
            None,
        ),
        "result": job.result,
        "error": job.error,
    }
