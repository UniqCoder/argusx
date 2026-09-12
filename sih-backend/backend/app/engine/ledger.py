"""
app/engine/ledger.py — Layer 5: tamper-evident evidence ledger.

entry_hash = SHA256(prev_hash || canonical_json(payload) || occurred_at_iso)

Each case's chain can be independently re-walked and re-hashed; any alteration
or removal of a row breaks the chain from that point forward, which
verify_ledger() detects and reports precisely (the first broken seq).

Honest scope (ARGUS-ENGINE-V2.md §5.3): this is integrity evidence for the
investigation record. It is NOT a Section 65B(4) certificate — that requires
a signed statement from the person responsible for the computer system. This
module produces the artifact; a human signs it.
"""
import asyncio
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.engine import EvidenceLedgerEntry
from app.schemas.engine import LedgerVerifyResponse

GENESIS_HASH = "0" * 64

# append_entry does a read-then-write (fetch last entry -> compute hash off
# its entry_hash -> insert). Two concurrent appends to the SAME chain (same
# case_id, or both to the global None chain) can both read the same "last
# entry" before either commits, so the second commit's prev_hash no longer
# matches the chain's real tip — verify_chain then reports the chain broken,
# even though nothing was tampered with. One asyncio.Lock per chain key
# serializes the whole read+compute+insert critical section within this
# process (uvicorn runs this app single-process/single-event-loop, so this
# is sufficient here — it would need a DB-level lock, e.g. a Postgres
# advisory lock, to also hold across multiple server processes).
_chain_locks: dict[Optional[str], asyncio.Lock] = defaultdict(asyncio.Lock)


def _canonical_json(payload: dict[str, Any]) -> str:
    """Deterministic serialization — sorted keys, no whitespace ambiguity."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _normalize_dt(occurred_at: datetime) -> str:
    """
    Normalize to a UTC-aware ISO string before hashing. SQLite has no native
    timezone type, so a tz-aware datetime written through the generic
    DateTime/TIMESTAMP column can come back naive on read — without this
    normalization, the hash computed at append time (tz-aware) would never
    match the hash recomputed at verify time from the re-fetched row
    (naive), breaking every entry's self-check regardless of tampering.
    """
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    return occurred_at.astimezone(timezone.utc).isoformat()


def _compute_entry_hash(prev_hash: str, payload: dict[str, Any], occurred_at: datetime) -> str:
    digest_input = f"{prev_hash}|{_canonical_json(payload)}|{_normalize_dt(occurred_at)}"
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


async def append_entry(
    db: AsyncSession,
    event_type: str,
    payload: dict[str, Any],
    actor: str,
    case_id: Optional[UUID] = None,
) -> EvidenceLedgerEntry:
    """Append one event to the hash chain. Never mutates or deletes a prior row."""
    lock_key = str(case_id) if case_id is not None else None
    async with _chain_locks[lock_key]:
        last = await _last_entry(db, case_id)
        prev_hash = last.entry_hash if last else GENESIS_HASH
        occurred_at = datetime.now(timezone.utc)
        entry_hash = _compute_entry_hash(prev_hash, payload, occurred_at)

        entry = EvidenceLedgerEntry(
            case_id=case_id,
            event_type=event_type,
            payload=payload,
            actor=actor,
            occurred_at=occurred_at,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return entry


async def get_entries_for_case(db: AsyncSession, case_id: UUID) -> list[EvidenceLedgerEntry]:
    """Real forensic-engine events for a case's Evidence Trail — anchor
    registration, trace completion, decisions — in chronological order.
    Read-only; does not verify the hash chain (see verify_chain for that)."""
    stmt = (
        select(EvidenceLedgerEntry)
        .where(EvidenceLedgerEntry.case_id == case_id)
        .order_by(EvidenceLedgerEntry.seq.asc())
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def _last_entry(db: AsyncSession, case_id: Optional[UUID]) -> EvidenceLedgerEntry | None:
    stmt = select(EvidenceLedgerEntry)
    if case_id is not None:
        stmt = stmt.where(EvidenceLedgerEntry.case_id == case_id)
    stmt = stmt.order_by(EvidenceLedgerEntry.seq.desc()).limit(1)
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def verify_chain(db: AsyncSession, case_id: Optional[UUID] = None) -> LedgerVerifyResponse:
    """
    Re-walk the chain in sequence order and recompute every hash. Returns
    intact=False with the first broken seq the moment a stored entry_hash
    doesn't match what its own (prev_hash, payload, occurred_at) recomputes to
    — this catches both payload tampering and row deletion (deletion breaks
    the prev_hash link of the next surviving row).
    """
    stmt = select(EvidenceLedgerEntry).order_by(EvidenceLedgerEntry.seq.asc())
    if case_id is not None:
        stmt = stmt.where(EvidenceLedgerEntry.case_id == case_id)
    rows = (await db.execute(stmt)).scalars().all()

    expected_prev = GENESIS_HASH
    checked = 0
    for row in rows:
        checked += 1
        recomputed = _compute_entry_hash(expected_prev, row.payload, row.occurred_at)
        if row.prev_hash != expected_prev or recomputed != row.entry_hash:
            return LedgerVerifyResponse(
                case_id=case_id, entries_checked=checked, intact=False, broken_at_seq=row.seq,
            )
        expected_prev = row.entry_hash

    merkle_root = _merkle_root([r.entry_hash for r in rows]) if rows else None
    return LedgerVerifyResponse(
        case_id=case_id, entries_checked=checked, intact=True, merkle_root=merkle_root,
    )


def _merkle_root(hashes: list[str]) -> str:
    """Simple binary Merkle root over the chain's entry hashes, printed on PDF reports."""
    if not hashes:
        return GENESIS_HASH
    level = list(hashes)
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else level[i]
            nxt.append(hashlib.sha256(f"{left}{right}".encode("utf-8")).hexdigest())
        level = nxt
    return level[0]
